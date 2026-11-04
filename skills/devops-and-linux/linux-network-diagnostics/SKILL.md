---
name: linux-network-diagnostics
description: Diagnose Linux networking faults layer by layer—interface, address, route, DNS, firewall, TCP state, and TLS—with packet evidence instead of guesswork.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Linux Network Diagnostics

## 1. Purpose

Find out why traffic is not flowing, is slow, or is going somewhere unexpected. This skill follows the layer-by-layer method: link → address → route → name resolution → firewall/NAT → socket state → application → TLS, each with the exact commands and expected outputs. It emphasizes packet-level evidence (`tcpdump`) over speculation, and modern `ip`/`ss` tooling over deprecated `ifconfig`/`netstat`.

**Scope:** your own hosts and networks. Packet capture may expose other users' traffic; confine filters and delete captures per policy.

## 2. Activation Conditions

- "Connection refused/timed out", high latency, intermittent packet loss.
- DNS failures or resolution to the wrong address.
- Asymmetric routing, MTU black holes, VPN or container networking issues.
- Need to verify firewall/NAT behavior.
- Keywords: network troubleshooting, `ip addr`, `ss`, `tcpdump`, DNS, MTU, packet loss, latency, `ping`, `traceroute`, iptables, NAT, VPN.

## 3. When Not to Use

- Active port scanning of remote networks (use network-security-analysis with authorization).
- Application-level HTTP errors with healthy transport (use application logs and API tooling).
- WiFi RF issues (use wireless-specific tooling).

## 4. Required Context

1. Topology: source host, destination, intermediate hops, NAT/firewalls, VPNs.
2. Expected path and ports; whether ICMP is filtered (affects ping/traceroute interpretation).
3. Recent changes: DNS records, firewall rules, routing, MTU, certificate renewal.
4. Container/network namespace setup (which namespace the process actually uses).
5. Whether you can capture on both ends (source and destination) for comparison.

## 5. Operating Procedure

1. **Link layer**: `ip -brief link`, `ethtool eth0` — carrier up, speed/duplex, errors, drops.
2. **Address layer**: `ip -brief addr`, `ip -6 addr` — expected IPs, duplicate addresses.
3. **Route**: `ip route get <dest>`, `ip route show table all`, `ip rule show` — correct egress interface and gateway.
4. **Name resolution**: `getent hosts name`, `resolvectl query name`, `dig +short name A`, `dig @1.1.1.1 name` — compare system resolver vs. public to isolate DNS.
5. **Reachability**: `ping -c3 host` (if ICMP allowed), `tracepath host` / `traceroute -T -p 443 host` for TCP path, watch for the hop where it stops.
6. **Firewall/NAT**: `nft list ruleset` or `iptables -S`; `conntrack -L | grep <ip>`; test the specific port with `nc -vz host port`.
7. **Socket state**: `ss -tunap`, `ss -s` — SYN-SENT (no reply), SYN-RECV (server side not answering), TIME-WAIT flood, receive-queue growth.
8. **Packet evidence**: capture on both ends with identical filters; compare SYN/SYN-ACK/RST.
9. **Application**: `curl -v --connect-timeout 5 --max-time 10 https://host/`, `openssl s_client -connect host:443 -servername host`.
10. **MTU**: test with `ping -M do -s 1472 host` (1500 - 28) for IPv4; adjust down to find the black hole; check `ip link show` mtu.
11. **Record findings and fix at the correct layer**; do not add blanket `iptables -A ... -j ACCEPT` rules.

## 6. Tools and Technologies

| Layer | Tools |
|---|---|
| Link/address | `ip`, `ethtool`, `nmcli`, `networkctl` |
| Route | `ip route`, `ip rule`, `tracepath`, `traceroute`, `mtr` |
| DNS | `dig`, `resolvectl`, `getent`, `nslookup`, `/etc/resolv.conf`, `/etc/nsswitch.conf` |
| Sockets | `ss`, `conntrack`, `lsof -i` |
| Capture | `tcpdump`, `tshark`, `wireshark` |
| Firewall | `nft`, `iptables`, `ufw`, `firewalld` |
| App/TLS | `curl`, `openssl s_client`, `httpie`, `grpcurl` |
| Performance | `iperf3`, `mtr`, `tc qdisc` |

## 7. Practical Implementation

**Layer-by-layer script (destination + port):**

```bash
#!/usr/bin/env bash
set -uo pipefail
dest="${1:?usage: netdiag <host> [port]}"; port="${2:-443}"

echo "== link";      ip -brief link
echo "== addr";      ip -brief addr
echo "== route";     ip route get "$dest"
echo "== dns";       getent hosts "$dest" || echo "system resolver failed"
echo "== tcp connect"; timeout 5 nc -vz "$dest" "$port" 2>&1 || echo "connect failed"
echo "== trace";     timeout 20 tracepath -n "$dest" 2>&1 | head -15
echo "== sockets";   ss -tunap | head -20
echo "== curl";      curl -sS -o /dev/null -w 'code=%{http_code} dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s total=%{time_total}s\n' \
                       --connect-timeout 5 --max-time 15 "https://$dest/" || echo "curl failed"
```

**Interpreting `ss` states:**

```bash
ss -s
ss -tunap state syn-sent          # outbound connection attempts with no reply -> firewall/drop
ss -tunap state syn-recv          # server SYN queue backing up -> app not accepting
ss -lnt                           # Send-Q on listeners shows backlog overflow when it grows
ss -tunap | awk '{print $1}' | sort | uniq -c
```

**DNS isolation:**

```bash
dig +short example.com A
dig +short @10.0.0.53 example.com A     # internal resolver
dig +short @1.1.1.1 example.com A       # external resolver
resolvectl status | sed -n '1,25p'
cat /etc/nsswitch.conf | grep hosts
getent hosts example.com                # exercises the full NSS path
```

**Packet capture comparison (run on both hosts):**

```bash
# source
sudo timeout 15 tcpdump -i any -nn -s0 -w /tmp/src.pcap "host 203.0.113.10 and port 443"
# destination
sudo timeout 15 tcpdump -i any -nn -s0 -w /tmp/dst.pcap "host 198.51.100.7 and port 443"

tshark -r /tmp/src.pcap -Y 'tcp.flags.syn==1' -T fields -e ip.src -e tcp.flags.syn -e tcp.flags.ack | head
tshark -r /tmp/dst.pcap -Y 'tcp.flags.reset==1' -T fields -e ip.src -e ip.dst | head
```

**MTU black hole test:**

```bash
ping -c2 -M do -s 1472 203.0.113.10      # 1500-byte payload works?
ping -c2 -M do -s 1400 203.0.113.10      # smaller works => MTU issue upstream
ip link show dev eth0 | grep -o 'mtu [0-9]*'
# Fix on the tunnel interface, not by lowering MTU on every host:
sudo ip link set dev wg0 mtu 1380
```

**Conntrack and NAT verification:**

```bash
sudo conntrack -L -p tcp --dport 443 | head
sudo nft list table ip nat 2>/dev/null | head -40
# Verify the rule is actually hit (counters):
sudo nft -a list ruleset | grep -B2 -A2 'counter'
```

**TLS handshake diagnostics:**

```bash
openssl s_client -connect example.com:443 -servername example.com -brief </dev/null
# Verify certificate chain and expiry
echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

**Latency and loss measurement:**

```bash
mtr -rwzc 20 example.com          # per-hop loss and jitter, report mode
iperf3 -c 203.0.113.20 -t 10 -P 4 # throughput test between controlled hosts
tc qdisc show dev eth0            # check for netem impairments left behind
```

## 8. Quality Standards

- Diagnosis follows layers and stops at the first failing layer with evidence.
- Firewall changes are specific (source, destination, port, protocol) and documented.
- Packet captures are compared on both ends when possible.
- ICMP filtering is accounted for before declaring a host unreachable.
- No `iptables -F`, no disabling the firewall, no `setenforce 0` as a fix.
- Temporary `tc`/`sysctl` changes are reverted and recorded.
- Root causes reference a concrete artifact (pcap, rule, config, DNS answer).

## 9. Verification and Testing

```bash
curl -sS -o /dev/null -w '%{http_code} %{time_total}\n' https://example.com/
nc -vz example.com 443
mtr -rwzc 30 example.com | tail -5
ss -tunap state established | grep :443 | head
getent hosts example.com
```

Expected evidence: consistent success across repeated attempts, no retransmissions in a spot capture, matching pcap on both ends, and stable latency distribution.

## 10. Security Considerations

- Captures can contain credentials and PII; use narrow filters, `umask 077`, and delete promptly.
- Never run `tcpdump` on interfaces carrying other tenants' traffic without provider approval.
- Do not disable firewall or SELinux to "test"; add a temporary scoped rule with an expiry and remove it.
- Changing DNS resolvers can route traffic to an attacker resolver—verify resolver authenticity (DoT/DoH, DNSSEC).
- `curl -k`/`--insecure` masks MITM: use it only in a lab, never in a diagnostic that informs a production decision.
- Validate that any tunnel/VPN MTU change does not break fragmentation-based security controls.

## 11. Failure Handling

- **Ping fails but TCP works:** ICMP is filtered; use TCP-based tests (`nc`, `curl`, `tracepath -T`).
- **SYN sent, no reply:** firewall drop or routing; capture on the destination to see whether the packet arrives.
- **SYN-ACK sent, client resets:** often asymmetric routing or a middlebox rewriting; check both paths and `rp_filter`.
- **Works by IP but not by name:** DNS. Works by name on one host but not another: `/etc/hosts`, `nsswitch.conf`, or split-horizon DNS.
- **Only large transfers fail:** MTU/MSS clamping—fix on tunnel/edge, not by shrinking everywhere.
- **Intermittent loss:** use `mtr -rwzc 100`, check interface errors (`ip -s link`), and look for buffer drops in `tc -s qdisc`.

## 12. Expected Deliverables

1. Layer-by-layer diagnostic transcript.
2. Identified failing layer with evidence.
3. Configuration change or rule added, with scope and expiry.
4. Verification results (post-change).
5. Capture summary (if taken) and deletion record.
6. Follow-up monitoring recommendation.

## 13. References

- `ip(8)` — https://man7.org/linux/man-pages/man8/ip.8.html
- `ss(8)` — https://man7.org/linux/man-pages/man8/ss.8.html
- `tcpdump(8)` — https://www.tcpdump.org/manpages/tcpdump.1.html
- nftables wiki — https://wiki.nftables.org/
- `resolvectl` — https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html
- `tracepath(8)` — https://man7.org/linux/man-pages/man8/tracepath.8.html
- RFC 8899 (DPLPMTUD) background on path MTU — https://www.rfc-editor.org/rfc/rfc8899
