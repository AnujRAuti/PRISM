---
name: cloud-networking
description: Design cloud networks that isolate correctly—VPC and subnet layout, routing, security groups, private endpoints, DNS, and egress control.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# Cloud Networking

## 1. Purpose

Build network topology that keeps data private, makes connectivity explicit, and fails predictably. Most cloud breaches and outages involve networking: an over-broad security group, a route to the internet nobody knew about, overlapping CIDRs preventing peering, DNS that resolves to a stale IP, or a missing egress path that breaks a service at 2 a.m. This skill covers address planning, subnet tiers, routing, security groups, private connectivity, DNS, and egress control.

**Scope:** networks you administer. Routing and firewall changes can sever access to production systems (including your own administrative path): always have console/out-of-band access verified before changing routes, and require authorization for changes to shared or production networks.

## 2. Activation Conditions

- New VPC/network or a second environment/region.
- Connectivity between VPCs, accounts, on-premises, or partners.
- Services unable to reach dependencies; egress costs or unintended internet paths.
- Security review found exposed management interfaces.
- Keywords: VPC, subnet, CIDR, route table, NAT gateway, security group, NACL, VPC peering, Transit Gateway, PrivateLink, VPC endpoint, DNS, Route 53, egress, firewall, overlapping CIDR.

## 3. When Not to Use

- Application-level authorization (use authorization-and-permissions).
- Kubernetes-internal network policy (use kubernetes-administration).
- Provider-specific resource provisioning details (use aws-engineering).

## 4. Required Context

1. Cloud provider(s) and regions.
2. Account and environment topology.
3. Address space already in use (on-premises, other VPCs, partners) to avoid overlaps.
4. Traffic flows: user → edge → app → data → third parties; plus management access.
5. Compliance constraints on data residency and egress.

## 5. Operating Procedure

1. **Plan the address space globally before creating anything**: allocate non-overlapping /16s per environment/region from a documented IP plan, with room to grow. Overlaps block peering and merging forever.
2. **Create tiered subnets across at least three AZs**: public (load balancers only), private-app, private-data, and optionally isolated (no route to NAT). Size for burst IP consumption (pods/node groups consume many addresses).
3. **Route explicitly**: one route table per tier; the default route to an internet gateway exists only in public subnets. Data subnets have no NAT route if they never need egress.
4. **Prefer security-group references over CIDRs** so rules follow workloads, not address ranges; keep NACLs coarse (they are stateless and subnet-wide).
5. **Deny by default everywhere**: no `0.0.0.0/0` ingress except 443 on public load balancers; never expose SSH/RDP/DB ports to the internet.
6. **Use private connectivity for AWS/cloud APIs**: gateway endpoints for object storage, interface endpoints (PrivateLink) for everything else, with endpoint policies scoped to your organization.
7. **Use Transit Gateway (or equivalent hub) for many-VPC connectivity** rather than a mesh of peerings; segment route tables by environment so prod and dev cannot route to each other by default.
8. **Control egress deliberately**: NAT gateways for required internet egress (cost-aware: they are per-AZ and data-charged), a forward proxy or firewall for outbound inspection, and DNS firewalling for exfiltration control.
9. **Own DNS explicitly**: private hosted zones for internal names, low TTLs during migrations, health checks for failover, and DNSSEC where the provider supports it.
10. **Log and observe the network**: VPC flow logs to a central account, reachability analysis, and alarms on rejected traffic spikes.
11. **Test connectivity as part of the change**: prove allow and deny paths before and after a change.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| VPC design | Terraform `aws_vpc` modules, `vpc-cni` sizing, IPAM |
| Connectivity | VPC peering, Transit Gateway, PrivateLink, Cloud Interconnect/VPN |
| Egress | NAT gateway, NAT instances, AWS Network Firewall, egress VPC |
| DNS | Route 53 private zones, Resolver rules, `dig`, `nslookup` |
| Security groups | SG referencing, `aws ec2 describe-security-groups`, `checkov` |
| Verification | VPC Reachability Analyzer, `tcpdump`, `mtr`, `nc`/`curl -v` |
| Logging | VPC flow logs, Network Firewall logs, DNS query logs |

## 7. Practical Implementation

**Documented IP plan (before provisioning):**

```markdown
| Scope | CIDR | Notes |
|---|---|---|
| Global supernet | 10.0.0.0/8 | reserved, never allocated as a VPC |
| prod / ap-south-1 | 10.20.0.0/16 | |
|  ├ public    | 10.20.0.0/20 → /22 per AZ | LBs only |
|  ├ app       | 10.20.16.0/20 → /22 per AZ | workloads, pods |
|  ├ data      | 10.20.32.0/20 → /24 per AZ | DBs, caches |
|  └ isolated  | 10.20.48.0/20 → /24 per AZ | no NAT route |
| staging / ap-south-1 | 10.30.0.0/16 | |
| on-premises | 172.16.0.0/12 | joined via VPN/TGW, must not overlap |
```

**VPC with tiered subnets across three AZs (Terraform):**

```hcl
locals {
  azs = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
}

resource "aws_vpc" "main" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = {Name = "prod-ap-south-1"}
}

resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet("10.20.0.0/20", 2, count.index)   # /22 each
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false          # public IPs only via the load balancer
  tags = {Name = "prod-public-${local.azs[count.index]}", tier = "public"}
}

resource "aws_subnet" "app" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet("10.20.16.0/20", 2, count.index)
  availability_zone = local.azs[count.index]
  tags = {Name = "prod-app-${local.azs[count.index]}", tier = "app"}
}

resource "aws_subnet" "data" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet("10.20.32.0/20", 2, count.index)
  availability_zone = local.azs[count.index]
  tags = {Name = "prod-data-${local.azs[count.index]}", tier = "data"}
}

# Public tier: default route to the internet gateway
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

# App tier: egress via NAT, one per AZ (a single NAT is an AZ failure domain)
resource "aws_nat_gateway" "per_az" {
  count         = 3
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
}

resource "aws_route_table" "app" {
  count  = 3
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.per_az[count.index].id
  }
}

# Data tier: no default route at all — no internet path, by construction
resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id
}
```

**Workload-referencing security groups (no CIDR ranges for internal traffic):**

```hcl
resource "aws_security_group" "alb" {
  name        = "prod-alb"
  description = "Public ingress on 443 only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]         # the only public ingress in the VPC
  }
  egress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "aws_security_group" "app" {
  name        = "prod-app"
  description = "Application tier; accepts only ALB traffic"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]      # follows the SG, not an IP
  }
  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.db.id]
  }
  egress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    cidr_blocks     = ["0.0.0.0/0"]      # via NAT; restrict further with a proxy if needed
  }
}
```

**Interface endpoint for a third-party/SaaS service (PrivateLink), scoped by policy:**

```hcl
resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.ap-south-1.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.app[*].id
  security_group_ids  = [aws_security_group.vpce.id]
  private_dns_enabled = true
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = ["secretsmanager:GetSecretValue"]
      Resource  = "arn:aws:secretsmanager:ap-south-1:111122223333:secret:orders/*"
      Condition = {"StringEquals" : {"aws:PrincipalOrgID" : "o-example123"}}
    }]
  })
}
```

**Hub-and-spoke with Transit Gateway and route-table segmentation:**

```hcl
resource "aws_ec2_transit_gateway" "hub" {
  description = "org hub"
  default_route_table_association = "disable"     # explicit associations only
  default_route_table_propagation = "disable"
}

# Separate route tables per environment; prod and dev do not route to each other
resource "aws_ec2_transit_gateway_route_table" "prod" { transit_gateway_id = aws_ec2_transit_gateway.hub.id }
resource "aws_ec2_transit_gateway_route_table" "dev"  { transit_gateway_id = aws_ec2_transit_gateway.hub.id }

resource "aws_ec2_transit_gateway_vpc_attachment" "prod" {
  transit_gateway_id                              = aws_ec2_transit_gateway.hub.id
  vpc_id                                          = aws_vpc.main.id
  subnet_ids                                      = aws_subnet.app[*].id
  transit_gateway_default_route_table_association = false
  transit_gateway_default_route_table_propagation = false
}
```

**DNS: private zone for internal service names:**

```hcl
resource "aws_route53_zone" "internal" {
  name          = "internal.acme.example"
  vpc { vpc_id = aws_vpc.main.id }
  comment       = "Service discovery for prod VPC"
}

resource "aws_route53_record" "orders_db" {
  zone_id = aws_route53_zone.internal.zone_id
  name    = "orders-db.internal.acme.example"
  type    = "CNAME"
  ttl     = 60                       # low TTL keeps failover fast
  records = [aws_db_instance.orders.address]
}
```

**Connectivity verification (before and after any change):**

```bash
# DNS resolution from inside a pod/host
dig +short orders-db.internal.acme.example

# TCP reachability on the expected port
nc -zv orders-db.internal.acme.example 5432

# Path and latency to an endpoint
mtr -rw -c 20 10.20.32.15

# Confirm the egress source IP (is it the NAT gateway you expect?)
curl -s https://checkip.amazonaws.com

# Prove a deny path: this must fail
timeout 3 bash -c 'cat < /dev/null > /dev/tcp/1.2.3.4/22' && echo "UNEXPECTED: reachable"
```

```bash
# Cloud-native reachability analysis before deploying the change
aws ec2 create-network-insights-path \
  --source <app-eni-id> --destination <db-eni-id> --protocol tcp --destination-port 5432
aws ec2 start-network-insights-analysis --network-insights-path-id <path-id>
```

## 8. Quality Standards

- IP plan documented and non-overlapping with on-premises, partners, and other environments.
- Three AZs minimum for every tier; no single-NAT or single-AZ dependency in production.
- Public subnets host only load balancers; workloads and data are private.
- Data subnets have no internet route; AWS API access uses endpoints.
- Security groups reference other security groups for internal traffic; no `0.0.0.0/0` on 22/3389/5432.
- Management access goes through a bastion/SSM session manager, not public SSH.
- Flow logs enabled to a central, tamper-evident account with retention.
- DNS changes use low TTLs during migrations and are reverted after.
- Every connectivity change includes a documented before/after reachability test.

## 9. Verification and Testing

- Reachability Analyzer (or equivalent) for each critical path, plus a negative test for a path that must fail.
- Scan for security groups with world-open ingress (`0.0.0.0/0`/`::/0`) on non-443 ports; fail CI.
- Confirm data-subnet route tables have no `0.0.0.0/0` route.
- Verify private DNS resolves to private IPs from inside the VPC and does not resolve publicly.
- Test AZ failure: remove one AZ's NAT/subnet in staging and confirm the service stays healthy.
- Check flow-log delivery and that rejected traffic is visible during a deliberate probe.

## 10. Security Considerations

- Network segmentation is containment, not authorization: workloads still need authentication and per-object authorization.
- Overlapping CIDRs are a security risk as well as an operational one—merging later forces route sprawl and bypass paths.
- Avoid `0.0.0.0/0` egress where possible; unrestricted egress enables exfiltration and C2 traffic.
- Block access to the instance metadata service from workloads that do not need it (or enforce IMDSv2 with hop limit 1).
- Shared VPCs and Transit Gateway attachments widen blast radius: segment route tables per environment and require explicit approval to attach.
- Endpoint policies are a second layer: scope them to your organization/account and specific resources.
- DNS is an attack surface (tunneling, rebinding): enable DNS query logging and consider DNS firewalling.
- On-premises VPN/interconnect terminates in a security boundary: apply firewalls on both sides, never trust the tunnel alone.

## 11. Failure Handling

- **Cannot reach a database after a change:** check security group references first (a replaced SG breaks rules), then route tables, then NACLs (stateless — remember return traffic).
- **Intermittent failures across one AZ:** asymmetric routing or a NAT/subnet issue in that AZ; verify per-AZ routes and NAT health.
- **Peering/TGW connection established but no traffic:** missing routes on both sides, overlapping CIDRs, or a firewall dropping it — check both route tables and logs.
- **DNS resolves publicly when it should not:** a public hosted zone overlaps the private name; fix with a split-horizon design.
- **Lost administrative access after a route change:** use the provider console/serial access; this is why out-of-band access must be verified before changes.

## 12. Expected Deliverables

1. IP address plan and VPC topology diagram.
2. Subnet, route table, and NAT/endpoint configuration as code.
3. Security group matrix (source → destination → port → purpose).
4. Connectivity matrix for cross-VPC/on-prem/partner traffic.
5. DNS zone design and record inventory.
6. Flow-log and firewall-log configuration.
7. Reachability test results for allow and deny paths.

## 13. References

- AWS VPC documentation — https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html
- AWS VPC endpoints and PrivateLink — https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html
- AWS Transit Gateway — https://docs.aws.amazon.com/vpc/latest/tgw/what-is-transit-gateway.html
- VPC Reachability Analyzer — https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html
- Route 53 private hosted zones — https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zones-private.html
- Security group rules reference — https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html
- AWS Network Firewall — https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html
- EC2 IMDS security — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
