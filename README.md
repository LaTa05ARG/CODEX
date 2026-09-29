# CODEX
CODEX IA

## Alertas de departamentos (MercadoLibre + Zonaprop)

Cada 30 minutos, un workflow de GitHub Actions revisa las búsquedas definidas en
[`config.yaml`](config.yaml) y manda un mail por cada departamento **nuevo** que
cumpla los filtros (precio, expensas, ambientes, m², zona, palabras clave).

### Puesta en marcha

1. **Mergear a `main`.** GitHub solo ejecuta workflows programados desde la rama por defecto.
2. **Crear una contraseña de aplicación de Gmail** (requiere verificación en 2 pasos):
   <https://myaccount.google.com/apppasswords>.
3. **Cargar los secrets** en *Settings → Secrets and variables → Actions*:

   | Secret | Obligatorio | Ejemplo |
   |---|---|---|
   | `SMTP_USER` | sí | la cuenta de Gmail que envía |
   | `SMTP_PASSWORD` | sí | la contraseña de aplicación del paso 2 |
   | `MAIL_TO` | sí | destinatario(s), separados por coma |
   | `SMTP_HOST` / `SMTP_PORT` | no | default `smtp.gmail.com` / `465` (con `587` usa STARTTLS) |
   | `MAIL_FROM` | no | default `SMTP_USER` |

4. **Editar `config.yaml`** con tus búsquedas y condiciones.
5. Probar a mano: *Actions → Alertas de departamentos → Run workflow*, tildando
   "Mandar un mail de prueba" para confirmar que llegan los mails.

La primera corrida de cada URL solo registra lo que ya está publicado (no manda
mails); desde ahí avisa lo nuevo. Los avisos ya notificados se guardan en
`data/vistos.json`, que el workflow commitea solo.

### Probar localmente

```bash
pip install -r requirements.txt
python -m alertas --dry-run --ignorar-vistos -v   # muestra qué mails mandaría y por qué descarta cada aviso
python -m pytest
```

### Limitaciones

- No hay API pública de búsqueda: se leen las páginas de resultados. Si un sitio
  cambia su HTML o bloquea al runner (Zonaprop usa Cloudflare), la corrida lo
  marca con un warning; si fallan **todas** las URLs, el workflow falla y GitHub
  te avisa por mail.
- MercadoLibre no ordena inmuebles por fecha; por eso el ejemplo usa el filtro
  "Publicados hoy". Un aviso publicado minutos antes de medianoche podría no detectarse.
- En repos privados, correr cada 30 min consume ~1.500 min/mes de Actions (el plan
  gratis incluye 2.000). Para reducirlo, cambiá el `cron` en
  `.github/workflows/alertas-deptos.yml`.
