# Informe de bots y de clics de anuncios

[← Documentación](README.md) · [🇬🇧 English](../en/ads-report.md)

> ✅ **Probado de punta a punta** con los registros que escriben un Caddy, un nginx y un Apache reales: se lanzan
> visitas con y sin `gclid`, de navegadores y de robots, y el informe las cuenta bien en los tres formatos.

`n-antibot report` lee los registros de acceso de tu servidor y responde a dos preguntas:

1. **¿Cuántas visitas son de bots**, de qué redes y robots, y cuántas se han cortado?
2. **¿Cuántos clics de anuncios de pago los hizo un bot?** Con su fecha, IP, navegador y `gclid`, en un CSV listo
   para pedir a Google que los investigue.

No envía nada a ningún sitio: lee tus archivos en tu máquina. Lo único que descarga son los rangos de las redes,
igual que `generate`.

## Uso

```bash
n-antibot report /var/log/caddy/access.log
n-antibot report /var/log/nginx/access.log /var/log/nginx/access.log.1 /var/log/nginx/access.log.*.gz
n-antibot report -c n-antibot.toml access.log --since 2026-10-01 --until 2026-10-31 --csv clics-bots.csv
```

```text
N-antibot traffic report
  Period:    2026-11-12 09:00 to 2026-11-12 09:03 UTC
  Requests:  6 from 4 IP addresses (1 unreadable lines)

Bots
  Requests from bots: 3 (50.0%) from 2 IPs
    cut off:  2
    served:   1   <- N-antibot is not stopping these yet
          2  AS132203 (tencent-cloud)
          1  python-requests

Paid ad clicks
  google: 4 clicks
    bots:        3 (75.0%)  [network 2, robot 1]
    suspicious:  0 (0.0%)  [repeated IP 0, no resources 0]
    clean:       1
  microsoft: 1 clicks
    bots:        0 (0.0%)  [network 0, robot 0]
    suspicious:  1 (100.0%)  [repeated IP 0, no resources 1]
    clean:       0

IP addresses behind bot and suspicious ad clicks (clicks, IP, why)
      2  43.173.132.9                             AS132203 (tencent-cloud) 43.173.0.0/16
      1  8.8.8.8                                  python-requests
      1  81.40.1.2                                loaded no page resources (hint)
```

## Opciones

| Opción | Descripción |
|---|---|
| `ARCHIVO…` | Uno o varios registros. Admite `.gz` y `-` para leer de la entrada estándar. |
| `-c CONFIG` | Tu configuración: decide qué redes y robots cuentan como bot. Sin ella, los valores por defecto. |
| `--since AAAA-MM-DD` | Primer día que se incluye (UTC). |
| `--until AAAA-MM-DD` | Último día que se incluye (UTC). |
| `--csv ARCHIVO` | Escribe los clics de anuncios de bots y sospechosos en un CSV. |
| `--all-clicks` | Con `--csv`: incluye también los clics limpios. |
| `--json` | Imprime el resumen en JSON, para tu panel o tus alertas. |
| `--min-repeat N` | Clics de anuncios desde una misma IP para marcarla como repetida (por defecto 3). |

## Qué registros entiende

| Servidor | Formato | Cómo activarlo |
|---|---|---|
| **Caddy** | JSON (el suyo por defecto) | Caddy **no** guarda accesos si no se lo pides. Añade al bloque de tu web: `log { output file /var/log/caddy/access.log }` |
| **nginx** | `combined` (el suyo por defecto) | Viene activado: `/var/log/nginx/access.log` |
| **Apache** | `combined` | Viene activado en la mayoría de instalaciones: `/var/log/apache2/access.log` |

Las peticiones cortadas también quedan registradas, y el informe las reconoce por su código: `0` en Caddy
(`abort`), `444` en nginx y `403` en Apache.

> [!NOTE]
> Detrás de un proxy o CDN, el registro debe guardar la IP real del visitante (ver «Detrás de un CDN» en los
> [casos de uso](casos.md#-detrás-de-un-cdn-o-balanceador)). Si guarda la del proxy, el informe no puede saber de qué
> red viene cada visita.

## Cómo reconoce un clic de anuncio

Por el identificador que la plataforma añade a la dirección de destino:

| Plataforma | Parámetros |
|---|---|
| Google Ads | `gclid`, `gbraid`, `wbraid` |
| Microsoft Ads | `msclkid` |
| TikTok, X, LinkedIn | `ttclid`, `twclid`, `li_fat_id` |
| Cualquier otra | `utm_medium` = `cpc`, `ppc`, `paid`, `paid-social`, `display`… (la plataforma sale de `utm_source`) |

Cada identificador cuenta **una sola vez**, aunque el visitante recargue la página. `fbclid` no cuenta: Meta lo
añade a todos los enlaces, de pago o no.

> [!IMPORTANT]
> En Google Ads, el etiquetado automático tiene que estar activado para que las direcciones lleven `gclid`. Sin él,
> el informe solo ve los clics que traigan `utm_medium=cpc`.

## Cómo clasifica cada clic

| Veredicto | Motivo | Qué significa | Fiabilidad |
|---|---|---|---|
| **bot** | `from a blocked network` | La IP pertenece a una red de servidores que tienes bloqueada (con su ASN y su rango). | Alta: una persona no navega desde un centro de datos |
| **bot** | `blocked robot or scraper` | El navegador se identifica como un robot o una librería de raspado. | Alta |
| **suspicious** | `same IP clicked several ads` | La misma IP hizo 3 o más clics de anuncio distintos en el periodo. | Indicio |
| **suspicious** | `loaded no page resources` | Esa IP solo pidió la página: ni imágenes, ni estilos, ni scripts. Un navegador real los pide. | Indicio |
| **clean** | | Nada de lo anterior. | |

Los «indicios» no son pruebas: una oficina entera puede salir por la misma IP, y un navegador puede tener la página
en caché. Sirven para decidir qué mirar, no para afirmar que es fraude.

## Reclamar a Google los clics de bots

Google explica el proceso en [Acerca del tráfico no válido](https://support.google.com/google-ads/answer/11182074):
filtra por su cuenta el tráfico no válido que detecta y, si le pides una investigación y encuentra más, **te avisa
del abono**. La investigación cubre **los últimos 60 días** y se pide con el
[formulario de calidad de clics](https://support.google.com/google-ads/contact/click_quality).

Esto es lo que pide Google y de dónde sale:

| Google pide | De dónde sale |
|---|---|
| Intervalo de fechas (últimos 60 días) | `--since` y `--until`; el informe imprime el periodo |
| Direcciones IP con clics repetidos o sin conversión | Columna `ip` del CSV y la lista «IP addresses behind…» |
| Navegador o dispositivo | Columna `user_agent` |
| **GCLID** de los clics sospechosos | Columna `click_id` |
| Registros del servidor | El propio archivo de accesos |
| Por qué es sospechoso | Columnas `reason` y `detail` (red, ASN, robot) |
| Campañas, grupos de anuncios y palabras clave | De tu cuenta de Google Ads: el registro no lo sabe |

```bash
n-antibot report /var/log/nginx/access.log* --since 2026-10-01 --until 2026-11-12 --csv clics-bots.csv
```

```csv
date_utc,time_utc,platform,click_id,ip,verdict,reason,detail,cut_off,status,user_agent,url
2026-11-12,09:00:01,google,AAA111,43.173.132.9,bot,from a blocked network,AS132203 (tencent-cloud) 43.173.0.0/16,yes,444,Mozilla/5.0 (Windows NT 10.0…,/producto/a/?gclid=AAA111
```

> [!WARNING]
> **Cortar al bot no evita el cobro.** El clic se produce en Google antes de que la visita llegue a tu web. N-antibot
> evita que el bot use tu servidor y ensucie tus estadísticas; el dinero se recupera reclamando.

Tres cosas que conviene saber antes de reclamar:

- **Puede que Google ya no te lo haya cobrado.** Mira antes la tarjeta de tráfico no válido («Invalid traffic») de la página de resumen de tu cuenta y las
  columnas de clics no válidos: parte de estos clics puede estar ya descontada.
- **Google no confirma clic a clic.** Su ayuda dice que la investigación no indica qué clics concretos dio por
  válidos o no válidos; si encuentra tráfico no válido adicional, avisa del abono.
- **Las horas del CSV van en UTC.** Tenlo en cuenta al compararlas con los informes de Google Ads.

## Privacidad

Las direcciones IP son datos personales. El informe se queda en tu máquina; compártelo solo con la plataforma a la
que reclamas y guárdalo el tiempo que dure la reclamación.

## Usarlo cada semana

```cron
# /etc/cron.d/n-antibot-report — lunes a las 7:00, resumen de la semana en JSON
0 7 * * 1  root  n-antibot report /var/log/nginx/access.log /var/log/nginx/access.log.1 --json > /var/log/n-antibot-report.json
```

En el JSON, `bots.served` distinto de cero quiere decir que hay bots que todavía reciben respuesta: revisa que el
archivo de N-antibot esté instalado y al día.
