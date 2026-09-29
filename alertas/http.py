"""Descarga de páginas. Usa curl_cffi (imita un Chrome real, necesario para
pasar el Cloudflare de Zonaprop) y cae a requests si no está instalado."""

from __future__ import annotations

import logging
import time

try:
    from curl_cffi import requests as _http

    _KW = {"impersonate": "chrome"}
except ImportError:  # pragma: no cover
    import requests as _http

    _KW = {}

log = logging.getLogger(__name__)

_HEADERS = {
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
if not _KW:
    _HEADERS["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )

# Marcas de páginas de desafío anti-bot (Cloudflare, DataDome, verificación de ML).
_MARCAS_BLOQUEO = (
    "challenges.cloudflare.com",
    "/cdn-cgi/challenge-platform/",
    "cf_chl_opt",
    "cf-turnstile",
    "captcha-delivery.com",
    "<title>just a moment",
    "<title>un momento",
    "account-verification",
)
# Si la página trae tarjetas de avisos, no es un desafío aunque cargue algún script de Cloudflare.
_MARCAS_LISTADO = ('data-qa="posting PROPERTY"', "ui-search-layout", "poly-card")


def es_desafio(html: str) -> bool:
    if any(m in html for m in _MARCAS_LISTADO):
        return False
    bajo = html.lower()
    return any(m in bajo for m in _MARCAS_BLOQUEO)


class PaginaBloqueada(Exception):
    pass


def descargar(url: str, intentos: int = 3, timeout: int = 30) -> str:
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            r = _http.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True, **_KW)
            html = r.text
            if r.status_code in (403, 429, 503) or es_desafio(html):
                raise PaginaBloqueada(f"HTTP {r.status_code}: el sitio devolvió un desafío anti-bot")
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            return html
        except Exception as e:  # noqa: BLE001 - reintentamos ante cualquier falla de red
            ultimo_error = e
            log.warning("Intento %d/%d falló para %s: %s", intento, intentos, url, e)
            if intento < intentos:
                time.sleep(5 * intento)
    raise ultimo_error  # type: ignore[misc]
