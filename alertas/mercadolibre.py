"""Parseo de páginas de resultados de MercadoLibre Inmuebles.

Soporta el layout actual ("poly-card") y el anterior ("ui-search-result").
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from .modelo import Aviso, detectar_moneda, parsear_caracteristicas, parsear_numero, texto_de

FUENTE = "MercadoLibre"

_ID = re.compile(r"(ML[A-Z])-?(\d{6,})")
_CARDS = "li.ui-search-layout__item, div.poly-card, div.ui-search-result__wrapper"
_ATRIBUTOS = (
    ".poly-attributes_list__item, .poly-attributes-list__item, "
    ".ui-search-card-attributes__attribute"
)
_UBICACION = ".poly-component__location, .ui-search-item__location, .ui-search-item__location-label"


def _precio(card) -> tuple[float | None, str | None]:
    # Si hay precio tachado (anterior), el vigente está en poly-price__current.
    monto = card.select_one(".poly-price__current .andes-money-amount") or next(
        (m for m in card.select(".andes-money-amount") if not m.find_parent("s")), None
    )
    if not monto:
        return None, None
    simbolo = texto_de(monto.select_one(".andes-money-amount__currency-symbol"))
    fraccion = texto_de(monto.select_one(".andes-money-amount__fraction"))
    return parsear_numero(fraccion), detectar_moneda(simbolo) or "ARS"


def _url_limpia(href: str) -> str:
    # Los avisos promocionados pasan por un tracker de clics con la URL real en ?url=
    partes = urlsplit(href)
    destino = parse_qs(partes.query).get("url")
    if destino and _ID.search(destino[0]):
        partes = urlsplit(destino[0])
    return partes._replace(query="", fragment="").geturl()


def parsear_listado(html: str) -> list[Aviso]:
    soup = BeautifulSoup(html, "html.parser")
    avisos: list[Aviso] = []
    vistos: set[str] = set()
    for card in soup.select(_CARDS):
        link = next((a for a in card.select("a[href]") if _ID.search(a["href"])), None)
        if not link:
            continue
        m = _ID.search(link["href"])
        pid = f"{m.group(1)}{m.group(2)}"
        # Un mismo aviso puede matchear varios selectores anidados (li > div.poly-card).
        if pid in vistos:
            continue
        vistos.add(pid)

        titulo_el = card.select_one(".poly-component__title, .ui-search-item__title, h2, h3")
        precio, moneda = _precio(card)
        atributos = " | ".join(texto_de(li) for li in card.select(_ATRIBUTOS))
        img = card.select_one("img")

        avisos.append(
            Aviso(
                fuente=FUENTE,
                id=pid,
                url=_url_limpia(link["href"]),
                titulo=texto_de(titulo_el) or texto_de(link),
                precio=precio,
                moneda=moneda,
                ubicacion=texto_de(card.select_one(_UBICACION)),
                imagen=(img.get("data-src") or img.get("src") or "") if img else "",
                **parsear_caracteristicas(atributos),
            )
        )
    return avisos


def url_listado(url: str) -> str:
    """La vista de mapa (_DisplayType_M) no trae las tarjetas en el HTML: se pasa a vista de lista."""
    return re.sub(r"_DisplayType_[A-Z]+", "", url)


def url_siguiente(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one(
        "li.andes-pagination__button--next a[href], a.andes-pagination__link[title='Siguiente']"
    )
    return a["href"] if a else None
