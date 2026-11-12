# Informe de bots y de clics de anuncios

[← Documentación](README.md) · [🇬🇧 English](../en/ads-report.md)

> ✅ **Probado de punta a punta** con los registros que escriben un Caddy, un nginx y un Apache reales: se lanzan
> visitas con y sin `gclid`, de navegadores y de robots, y el informe las cuenta bien en los tres formatos.

`n-antibot report` lee los registros de acceso de tu servidor y responde a dos preguntas:

1. **¿Cuántas visitas son de bots**, de qué redes y robots, y cuántas se han cortado?
2. **¿Cuántos clics de anuncios de pago los hizo un bot?** Con su fecha, IP, navegador y `gclid`, en un CSV listo
   para reclamarlos, y un expediente por plataforma con lo que pide cada una.

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
| `--claim-dir CARPETA` | Escribe un expediente por plataforma de anuncios con lo que pide cada una. Ver [Reclamar](#reclamar-los-clics-de-bots). |
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
| Meta y cualquier otra | `utm_medium` = `cpc`, `ppc`, `paid`, `paid-social`, `display`… La plataforma sale de `utm_source` (`facebook`, `instagram`, `fb`, `ig` y `meta` cuentan como Meta) |

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

## Reclamar los clics de bots

Lo que dice la documentación oficial de cada plataforma, leída el 12-nov-2026. Abre la fuente antes de reclamar:
las normas cambian.

| Plataforma | Dónde se reclama | Plazo | Qué pide | Qué puedes esperar |
|---|---|---|---|---|
| **Google Ads** | [Formulario de calidad de clics](https://support.google.com/google-ads/contact/click_quality) | Últimos 60 días | Fechas; campañas y grupos de anuncios; palabras clave; registros del servidor con IP, navegador y GCLID; por qué es sospechoso | Lo revisan especialistas y avisan por correo. Si encuentran más tráfico no válido, avisan del abono. No confirman clic a clic. [Fuente](https://support.google.com/google-ads/answer/11182074) |
| **Microsoft Advertising** (Bing) | [Soporte](https://go.microsoft.com/fwlink?LinkId=398371), diciendo que es un problema de «invalid clicks» | Mejor en 30 días; pasados 60 no investigan | Grupo de anuncios y su número; ID del anuncio y palabras clave; fechas; qué ves en tus informes o registros; una muestra del registro si la piden | Intentan resolver en 9 días y recomiendan el reembolso si el tráfico es no válido. [Fuente](https://help.ads.microsoft.com/#apex/ads/en/60220/0) |
| **LinkedIn Ads** | [Soporte de Marketing Solutions](https://www.linkedin.com/help/lms/ask), por escrito | 90 días | Los cargos que disputas y el motivo | Solo crédito publicitario, a criterio de LinkedIn; no devuelven dinero. [Fuente](https://www.linkedin.com/legal/sas-terms) |
| **X Ads** | [Ticket de soporte](https://ads.x.com/en/help), por escrito | 60 días desde el cargo (acuerdo de EE. UU.) | Los cargos que disputas | Solo devuelven si encuentran un error técnico o de facturación. [Fuente](https://help.x.com/en/business-and-advertising/billing-basics) |
| **Meta Ads** (Facebook, Instagram) | [Formulario de pagos de anuncios](https://www.facebook.com/help/contact/649167531904667). **No documenta una vía para clics no válidos** | No indica | No lo dice | Deciden caso por caso, a su criterio, y la decisión es definitiva. Tarda al menos un mes. No devuelven por mal rendimiento. [Fuente](https://www.facebook.com/business/help/211313200321572) |
| **Pinterest Ads** | Soporte. **No documenta una vía para clics no válidos** | No indica | No lo dice | Dice que los cargos normales no suelen devolverse. [Fuente](https://help.pinterest.com/en/business/article/refunds-and-chargebacks) |
| **TikTok Ads, Amazon Ads** | Sin vía encontrada en su ayuda (solo se buscó; sus páginas no se abrieron una a una) | | | |

### El expediente por plataforma

`--claim-dir` escribe, por cada plataforma con clics de bots o sospechosos, tres archivos con lo que pide cada una:

```bash
n-antibot report /var/log/nginx/access.log* --since 2026-10-01 --claim-dir reclamacion/
```

| Archivo | Contenido |
|---|---|
| `<plataforma>-claim.txt` | Dónde reclamar, plazo, lo que pide la plataforma, cuántos clics siguen dentro de plazo, resumen, las IP con su motivo y un texto listo para pegar |
| `<plataforma>-clicks.csv` | Un clic por fila, con todas las columnas de abajo |
| `<plataforma>-log-sample.log` | Las líneas exactas del registro del servidor de esos clics (hasta 500) |

| Lo que piden | Columna del CSV | De dónde sale |
|---|---|---|
| Fechas | `date_utc`, `time_utc` | El registro |
| GCLID u otro identificador del clic | `click_id` | La dirección (`gclid`, `msclkid`…) |
| Dirección IP | `ip` | El registro |
| Navegador o dispositivo | `user_agent` | El registro |
| Por qué es sospechoso | `verdict`, `reason`, `detail` | N-antibot: red con su ASN, robot o indicio |
| Campaña | `campaign` | `utm_campaign`, `gad_campaignid`, `campaignid` |
| Grupo de anuncios | `ad_group` | `utm_adgroup`, `adgroupid`, `adset_id` |
| Anuncio | `ad_id` | `adid`, `ad_id`, `creative`, `utm_content` |
| Palabra clave | `keyword` | `utm_term`, `keyword` |
| Si aún se puede reclamar | `within_deadline` | El plazo de la plataforma (60 o 90 días) |
| Si la visita se cortó | `cut_off`, `status` | El registro |

Campaña, grupo, anuncio y palabra clave solo salen si la dirección de destino los lleva. Para que los lleve, añádelos
a la plantilla de seguimiento de la campaña; por ejemplo, en Google Ads:
`{lpurl}?utm_campaign={campaignid}&utm_adgroup={adgroupid}&utm_content={creative}&utm_term={keyword}`.

> [!WARNING]
> **Cortar al bot no evita el cobro.** El clic se produce en la plataforma antes de que la visita llegue a tu web.
> N-antibot evita que el bot use tu servidor y ensucie tus estadísticas; el dinero se recupera reclamando, y ninguna
> plataforma lo garantiza.

Tres cosas que conviene saber antes de reclamar:

- **Puede que no te lo hayan cobrado.** Las plataformas filtran por su cuenta parte del tráfico no válido. En Google
  Ads, mira antes la tarjeta de tráfico no válido («Invalid traffic») de la página de resumen de tu cuenta.
- **Google no confirma clic a clic.** Su ayuda dice que la investigación no indica qué clics concretos dio por
  válidos o no válidos; si encuentra tráfico no válido adicional, avisa del abono.
- **Las horas del CSV van en UTC.** Tenlo en cuenta al compararlas con los informes de la plataforma.

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
