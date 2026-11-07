# Task 5: Subnetting and Network Access Control (NACL)

## 1. Subnet Allocation Table

Base Network Block: `10.20.0.0/16`

Allocation strategy: Largest host requirement to smallest, starting at `10.20.0.0`, contiguous placement, smallest prefix fitting the usable host formula ($2^{32 - \text{prefix}} - 2$).

| Subnet | Hosts Needed | Prefix | Network Address | Usable Host Range | Broadcast Address | Usable Hosts |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **app** | 1,000 | `/22` | `10.20.0.0` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1,022 |
| **public** | 250 | `/24` | `10.20.4.0` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **data** | 100 | `/25` | `10.20.5.0` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **management** | 20 | `/27` | `10.20.5.128` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

---

## 2. Derivation and Working

### General Formula
- Total addresses in block: $2^{32 - \text{prefix}}$
- Usable host addresses: $2^{32 - \text{prefix}} - 2$ (excluding the network identifier and the broadcast address).

### Subnet 1: `app` (1,000 hosts required)
- Host bits needed: $2^h - 2 \ge 1,000 \implies h = 10 \implies 2^{10} - 2 = 1,022$ usable hosts.
- Prefix length: $32 - 10 = /22$.
- Block size: $2^{10} = 1,024$ addresses ($4 \times /24$ blocks).
- Starting address: `10.20.0.0`.
- Address span: `10.20.0.0` to `10.20.3.255`.
- Usable range: `10.20.0.1` through `10.20.3.254`.
- Broadcast address: `10.20.3.255`.

### Subnet 2: `public` (250 hosts required)
- Host bits needed: $2^h - 2 \ge 250 \implies h = 8 \implies 2^8 - 2 = 254$ usable hosts.
- Prefix length: $32 - 8 = /24$.
- Block size: $2^8 = 256$ addresses.
- Starting address: Immediately following `app`, which is `10.20.3.255 + 1` = `10.20.4.0`.
- Address span: `10.20.4.0` to `10.20.4.255`.
- Usable range: `10.20.4.1` through `10.20.4.254`.
- Broadcast address: `10.20.4.255`.

### Subnet 3: `data` (100 hosts required)
- Host bits needed: $2^h - 2 \ge 100 \implies h = 7 \implies 2^7 - 2 = 126$ usable hosts.
- Prefix length: $32 - 7 = /25$.
- Block size: $2^7 = 128$ addresses.
- Starting address: Immediately following `public`, which is `10.20.4.255 + 1` = `10.20.5.0`.
- Address span: `10.20.5.0` to `10.20.5.127`.
- Usable range: `10.20.5.1` through `10.20.5.126`.
- Broadcast address: `10.20.5.127`.

### Subnet 4: `management` (20 hosts required)
- Host bits needed: $2^h - 2 \ge 20 \implies h = 5 \implies 2^5 - 2 = 30$ usable hosts ($/26$ would give 62, but $/27$ is the smallest prefix providing 30 hosts $\ge 20$).
- Prefix length: $32 - 5 = /27$.
- Block size: $2^5 = 32$ addresses.
- Starting address: Immediately following `data`, which is `10.20.5.127 + 1` = `10.20.5.128`.
- Address span: `10.20.5.128` to `10.20.5.159`.
- Usable range: `10.20.5.129` through `10.20.5.158`.
- Broadcast address: `10.20.5.159`.

---

## 3. Stateless NACL Reasoning & Rule Ordering Explanation

### Why a Stateless NACL Requires Explicit Reply Rules
Unlike stateful firewalls (such as AWS Security Groups or `iptables` with `conntrack`), a Network Access Control List (NACL) is completely **stateless**. This means it evaluates every individual network packet in isolation without tracking established connections, TCP session state (`SYN`, `ESTABLISHED`), or request-response pairings.

When an external client initiates an inbound HTTP/HTTPS request to the public load balancer on port 80 or 443, the inbound packet is allowed by the inbound allow rules. However, when the load balancer sends the response back to the client, the outbound packet is destined for the client's temporary ephemeral port (typically in the range 1024–65535). Because the NACL cannot remember that this outbound packet is part of an existing, pre-approved session, the response will be dropped by default unless an explicit outbound rule allows traffic to ephemeral ports.

Similarly, when the load balancer forwards requests to the internal application tier on port 8000 (outbound rule 100), the replies returned by the application pods (destined for the load balancer's ephemeral ports) must be explicitly permitted by an inbound rule (inbound rule 140 allowing source `10.20.0.0/22` to destination ports 1024–65535).

### Why Rule Order Matters for the `198.51.100.0/24` Abusive Block
NACL rules are evaluated sequentially in strictly ascending numerical order (lowest rule number first), and processing stops at the **first matching rule** ("first match wins"):
1. The abusive subnet `198.51.100.0/24` is placed at **Rule 100** with action `DENY`.
2. General web traffic is permitted at **Rule 110** (port 80) and **Rule 120** (port 443) from `0.0.0.0/0` with action `ALLOW`.

Because `198.51.100.0/24` is a subset of the global CIDR `0.0.0.0/0`, any incoming packet from an abusive IP (e.g., `198.51.100.9` requesting port 443) matches Rule 100 first and is immediately denied. If Rule 100 were numbered higher than Rule 110/120 (e.g., Rule 200), the broad `ALLOW` rule for `0.0.0.0/0` on port 443 would match first, and the abusive traffic would be incorrectly permitted. Placing the specific `DENY` rule ahead of broader `ALLOW` rules is essential for enforcing access controls in a first-match-wins model.
