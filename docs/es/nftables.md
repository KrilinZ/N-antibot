# N-antibot en el cortafuegos de Linux (nftables)

[← Documentación](README.md) · [🇬🇧 English](../en/nftables.md)

> ✅ **Probado de punta a punta** en Linux (integración continua): se carga el archivo, la red bloqueada deja de
> poder conectar, cargarlo dos veces no duplica nada y al borrar la tabla vuelve la conexión.

## Cuándo usar esta guía

- Quieres cortar las redes **antes** de que lleguen a ningún servidor web: vale para cualquiera (Caddy, nginx,
  Apache, Node, contenedores Docker…).
- El servidor es tuyo (VPS o dedicado) con Linux y `nftables`.

> [!IMPORTANT]
> Un cortafuegos solo ve direcciones IP. **Corta redes, no robots**: no conoce el `User-Agent` ni la ruta, así que
> `[robots]` y `[paths] exclude` no se aplican aquí. Para los robots, combínalo con la guía de tu servidor web.

> [!WARNING]
> No sirve detrás de un CDN o un balanceador: al cortafuegos le llega la IP del proxy, no la del visitante.

## Pasos

**1. Genera el archivo.** Parte de [`examples/cases/firewall.toml`](../../examples/cases/firewall.toml).

```bash
n-antibot generate -c firewall.toml -o n-antibot.nft
```

**2. Compruébalo sin aplicarlo.**

```bash
sudo nft -c -f n-antibot.nft
```

**3. Cárgalo.**

```bash
sudo nft -f n-antibot.nft
sudo nft list table inet n_antibot | head -20
```

**4. Haz que sobreviva a un reinicio.** En Debian y Ubuntu:

```bash
sudo mkdir -p /etc/nftables.d
sudo cp n-antibot.nft /etc/nftables.d/n-antibot.nft
echo 'include "/etc/nftables.d/*.nft"' | sudo tee -a /etc/nftables.conf
sudo systemctl enable nftables
```

## Qué contiene el archivo

```nft
add table inet n_antibot
delete table inet n_antibot          # cargarlo otra vez sustituye la tabla entera, de forma atómica
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

| Detalle | Por qué |
|---|---|
| Tabla propia (`inet n_antibot`) | No toca tus reglas ni las de Docker, ufw o firewalld. Se quita borrando la tabla. |
| Gancho `prerouting` | También cubre los puertos publicados por Docker, que no pasan por `input`. |
| Solo los puertos web | El resto del servidor (SSH, correo) no se toca. Cámbialos con `ports` en `[nftables]`. |
| UDP además de TCP | HTTP/3 viaja por UDP 443. |
| `drop` | El bot no recibe nada: su conexión se queda esperando hasta agotar el tiempo. |

## Opciones

```toml
[output]
format = "nftables"

[nftables]
table = "n_antibot"     # nombre de la tabla
ports = [80, 443]       # puertos protegidos (TCP y UDP)
```

`networks.allow` sí se aplica: los rangos permitidos se restan antes de generar los conjuntos.

## Quitarlo

```bash
sudo nft delete table inet n_antibot
sudo rm -f /etc/nftables.d/n-antibot.nft
```
