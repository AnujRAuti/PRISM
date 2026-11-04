---
name: network-security-analysis
description: Analyze network exposure and traffic—port/service inventory, segmentation, firewall rules, TLS posture, and packet-level investigation—on networks you are authorized to assess.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: high
---

# Network Security Analysis

## 1. Purpose

Determine what is reachable, from where, with what protections, and whether that matches intent. This skill covers internal and authorized external exposure analysis: host discovery, port/service identification, firewall and segmentation review, TLS configuration, and packet capture analysis for investigation.

**Authorization boundary (mandatory):** scanning networks or hosts you do not own or lack written permission for is unlawful in many jurisdictions and is never permitted by this skill. Typically permitted: your own machines, your own LAN, lab environments, and client networks under a signed scope. Get approval before any active scanning, even internal.

## 2. Activation Conditions

- Pre-launch exposure review of new infrastructure.
- Investigating suspected compromise or anomalous traffic.
- Validating segmentation between VLANs/namespaces/accounts.
- Auditing firewall rules that have accumulated over years.
- Keywords: nmap, port scan, segmentation, firewall audit, TLS scan, packet capture, tcpdump, exposure, attack surface, network baseline.

## 3. When Not to Use

- Application-layer vulnerabilities (use api-security-testing).
- Cloud IAM or control-plane posture (use cloud-security-engineering).
- Active exploitation, credential attacks, or lateral movement—out of scope for this skill.
- Scanning shared/cloud networks where your traffic may cross other tenants' infrastructure without provider rules review.

## 4. Required Context

1. Written authorization and scope: CIDR ranges, hosts, ports, and time window.
2. Network diagram: subnets, VLANs, routing, NAT boundaries, VPN.
3. Intended exposure: which services must be reachable from which zones.
4. Firewall/security-group exports for review.
5. Monitoring and IDS/IPS in place—scans will generate alerts; notify the SOC.

## 5. Operating Procedure

1. **Confirm scope and notify monitoring.** Record authorization reference, window, and source IPs to be allowlisted.
2. **Passive first**: review configuration files, cloud security groups, firewall rules, and routing tables. No traffic sent.
3. **Host discovery** within scope only: `nmap -sn` on the approved range; verify the range twice before running.
4. **Port inventory**: `nmap -sS -p- --min-rate` (or TCP connect if not root) against approved hosts; record open ports.
5. **Service/version detection**: `-sV` with a reasonable intensity; flag unexpected services (databases, admin UIs, IPMI, RDP) exposed beyond intended zones.
6. **TLS posture**: protocol versions, cipher suites, certificate validity/chain, HSTS. Use `testssl.sh`/`sslyze` against approved endpoints.
7. **Segmentation tests**: from each zone, attempt to reach services that should be blocked; document allow/deny outcomes. This is the highest-value check.
8. **Rule analysis**: reduce firewall rules to an effective matrix (source zone × destination × port) and find shadowed/duplicate/any-any rules.
9. **Traffic analysis** (for investigation): capture with `tcpdump` using filters, analyze in Wireshark/`tshark`; look for beaconing, cleartext credentials, unexpected egress.
10. **Report**: exposure matrix with severity, intended-vs-actual gaps, and remediation (close, restrict, segment, monitor).
11. **Retest** after remediation and record evidence.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Discovery/ports | `nmap`, `masscan` (careful: aggressive), `naabu` |
| Service detection | nmap NSE `-sV -sC`, `nuclei` (authorized) |
| TLS | `testssl.sh`, `sslyze`, `openssl s_client` |
| Packet capture | `tcpdump`, `tshark`, Wireshark |
| Flow analysis | NetFlow/sFlow collectors, `nfdump` |
| Firewall review | `iptables-save`, `nft list ruleset`, cloud SG exports |
| Segmentation test | `curl`/`nc` from each zone, `hping3` (controlled) |
| DNS | `dig`, `dnsrecon` (authorized) |

## 7. Practical Implementation

**Scope-safe host discovery and port inventory:**

```bash
# Dry run: print targets only, verify the CIDR before scanning
nmap -sL 10.20.30.0/28

# Discovery (approved range)
sudo nmap -sn 10.20.30.0/28 -oG - | awk '/Up$/{print $2}'

# Full TCP port inventory with sane rate
sudo nmap -sS -p- --min-rate 1000 --max-retries 2 -T3 \
  -iL targets.txt -oA scan-tcp

# Service versions on discovered ports only
nmap -sV --version-light -p 22,80,443,5432,6379,9200 -iL targets.txt -oA scan-sv
```

**TLS posture:**

```bash
./testssl.sh --severity HIGH --quiet https://app.example.com | tee tls-app.txt
sslyze --regular app.example.com:443
openssl s_client -connect app.example.com:443 -servername app.example.com -tls1_1 </dev/null 2>&1 | head -5
# Expect: TLS 1.0/1.1 rejected; only 1.2/1.3 accepted.
```

**Segmentation verification (from a DMZ host):**

```bash
# These must FAIL from the DMZ; a success is a finding
for target in 10.20.40.10:5432 10.20.40.11:6379 10.20.50.5:22; do
  timeout 3 bash -c "echo > /dev/tcp/${target/:/\/}" 2>/dev/null \
    && echo "REACHABLE (finding): $target" || echo "blocked: $target"
done
```

**Packet capture with filters (investigation):**

```bash
# Capture DNS and TLS SNI for a suspicious host, bounded size and time
sudo timeout 120 tcpdump -i any -nn -s 0 -w /var/tmp/cap.pcap \
  'host 203.0.113.45 and (port 53 or port 443)' -c 20000
sudo chmod 600 /var/tmp/cap.pcap

# Analyze
tshark -r /var/tmp/cap.pcap -q -z conv,tcp
tshark -r /var/tmp/cap.pcap -Y 'tls.handshake.extensions_server_name' \
  -T fields -e ip.dst -e tls.handshake.extensions_server_name | sort | uniq -c | sort -rn | head
```

**Firewall effective-matrix from nftables:**

```bash
sudo nft list ruleset | tee /var/tmp/nft-rules.txt
# Look for: policy accept, any-any rules, rules without counters (never hit in years)
sudo nft list ruleset -a | grep -E 'accept|drop|policy' | head -40
```

**Egress baseline check:**

```bash
ss -tunp state established | awk '{print $5}' | sort | uniq -c | sort -rn | head -20
```

## 8. Quality Standards

- Scope is written down and re-verified before each command.
- Scans use rate limits that avoid disrupting services and are coordinated with monitoring.
- Every open port is attributed to a known service and owner, or flagged.
- Intended exposure is documented per zone and compared against observed exposure.
- Firewall rules have owners and last-hit data; unused allow rules are candidates for removal.
- Captures are encrypted at rest, access-controlled, and deleted after analysis per retention policy.

## 9. Verification and Testing

- Re-run the segmentation tests post-change and record allow/deny matrices.
- Confirm TLS with `testssl.sh --severity HIGH` returning no high findings.
- Compare nmap output before/after to show ports closed.
- Verify firewall counters increment after legitimate traffic (rules actually used).
- Evidence files: scan XML/GNMAP, tls report, rule diffs, capture summary.

## 10. Security Considerations

- Unauthorized scanning is illegal in many jurisdictions: always have written scope.
- Prefer read-only techniques; avoid `-sU` full UDP scans (slow, noisy, service impact) unless required.
- Do not run intrusive NSE scripts (`--script vuln`, `exploits`) without explicit approval.
- Packet captures contain credentials and PII: restrict to the minimum filter, encrypt, and delete.
- Never capture on interfaces carrying other tenants' traffic (cloud shared) without provider approval.
- Use root only where required (`-sS`), drop privileges afterward, and avoid running scanners from production hosts.
- Notify the SOC before scanning to prevent false incidents and to validate detection.

## 11. Failure Handling

- **Scan causes alarms/rate-limits:** pause, notify, and resume at a lower rate; document the disruption.
- **Unexpected hosts in scope:** stop and verify they are yours (cloud provider shared ranges, NAT overlap).
- **Inconclusive segmentation results:** a timeout is not proof of a block—check with a known-open control port to validate the test method.
- **Huge rule sets:** convert to a matrix programmatically (`iptables-save` parsing) rather than reading linearly.
- **Capture drops packets:** increase buffer (`-B`), narrow the filter, or capture on the specific interface.

## 12. Expected Deliverables

1. Scope and authorization record.
2. Host/port/service inventory with owners.
3. Intended-vs-observed exposure matrix by zone.
4. TLS configuration report.
5. Segmentation test results.
6. Firewall rule analysis with removal candidates.
7. Remediation plan and retest evidence.

## 13. References

- Nmap reference guide — https://nmap.org/book/man.html
- testssl.sh — https://testssl.sh/
- `tcpdump` man page — https://www.tcpdump.org/manpages/tcpdump.1.html
- Wireshark user guide — https://www.wireshark.org/docs/wsug_html_chunked/
- NIST SP 800-115 — https://csrc.nist.gov/pubs/sp/800/115/final
- CIS Benchmarks (network devices) — https://www.cisecurity.org/cis-benchmarks
- PTES (Penetration Testing Execution Standard) — http://www.pentest-standard.org/
