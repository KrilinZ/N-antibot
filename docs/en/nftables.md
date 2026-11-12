# N-antibot on the Linux firewall (nftables)

[← Documentation](README.md) · [🇪🇸 Español](../es/nftables.md)

> ✅ **Tested end to end** on Linux (continuous integration): the file is loaded, the blocked network can no longer
> connect, loading it twice duplicates nothing, and deleting the table brings the connection back.

## When to use this guide

- You want to cut the networks **before** they reach any web server: it works for all of them (Caddy, nginx,
  Apache, Node, Docker containers…).
- The server is yours (VPS or dedicated), running Linux with `nftables`.

> [!IMPORTANT]
> A firewall only sees IP addresses. **It cuts networks, not robots**: it knows neither the `User-Agent` nor the
> path, so `[robots]` and `[paths] exclude` do not apply here. For robots, combine it with your web server's guide.

> [!WARNING]
> It is no use behind a CDN or a load balancer: the firewall sees the proxy's IP, not the visitor's.

## Steps

**1. Generate the file.** Start from [`examples/cases/firewall.toml`](../../examples/cases/firewall.toml).

```bash
n-antibot generate -c firewall.toml -o n-antibot.nft
```

**2. Check it without applying it.**

```bash
sudo nft -c -f n-antibot.nft
```

**3. Load it.**

```bash
sudo nft -f n-antibot.nft
sudo nft list table inet n_antibot | head -20
```

**4. Make it survive a reboot.** On Debian and Ubuntu:

```bash
sudo mkdir -p /etc/nftables.d
sudo cp n-antibot.nft /etc/nftables.d/n-antibot.nft
echo 'include "/etc/nftables.d/*.nft"' | sudo tee -a /etc/nftables.conf
sudo systemctl enable nftables
```

## What the file contains

```nft
add table inet n_antibot
delete table inet n_antibot          # loading it again replaces the whole table, atomically
table inet n_antibot {
	set v4 { type ipv4_addr; flags interval; elements = { 1.12.0.0/14, … } }
	set v6 { type ipv6_addr; flags interval; elements = { 2402:4e00::/32, … } }
	chain prerouting {
		type filter hook prerouting priority -150; policy accept;
		tcp dport { 80, 443 } ip saddr @v4 drop
		udp dport { 80, 443 } ip saddr @v4 drop
		tcp dport { 80, 443 } ip6 saddr @v6 drop
		udp dport { 80, 443 } ip6 saddr @v6 drop
	}
}
```

| Detail | Why |
|---|---|
| Its own table (`inet n_antibot`) | It does not touch your rules or those of Docker, ufw or firewalld. Remove it by deleting the table. |
| `prerouting` hook | It also covers ports published by Docker, which do not go through `input`. |
| Web ports only | The rest of the server (SSH, mail) is untouched. Change them with `ports` under `[nftables]`. |
| UDP as well as TCP | HTTP/3 travels over UDP 443. |
| `drop` | The bot gets nothing: its connection waits until it times out. |

## Options

```toml
[output]
format = "nftables"

[nftables]
table = "n_antibot"     # table name
ports = [80, 443]       # protected ports (TCP and UDP)
```

`networks.allow` does apply: allowed ranges are subtracted before the sets are generated.

## Remove it

```bash
sudo nft delete table inet n_antibot
sudo rm -f /etc/nftables.d/n-antibot.nft
```
