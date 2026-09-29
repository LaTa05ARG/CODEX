"""Parseo de páginas de resultados de Zonaprop.

Las tarjetas se identifican por atributos data-qa (POSTING_CARD_*), que
Zonaprop usa para sus propios tests y son más estables que las clases CSS.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .modelo import Aviso, detectar_moneda, parsear_caracteristicas, parsear_numero, texto_de

FUENTE = "Zonaprop"
BASE = "https://www.zonaprop.com.ar"


def _qa(card, valor: str) -> str:
    return texto_de(card.select_one(f'[data-qa="{valor}"]'))


def parsear_listado(html: str) -> list[Aviso]:
    soup = BeautifulSoup(html, "html.parser")
    avisos: list[Aviso] = []
    for card in soup.select('[data-qa="posting PROPERTY"]'):
        pid = card.get("data-id")
        if not pid:
            continue
        href = card.get("data-to-posting") or ""
        if not href:
            a = card.select_one("a[href]")
            href = a["href"] if a else ""
        url = urljoin(BASE, urlsplit(href)._replace(query="", fragment="").geturl())

        precio_txt = _qa(card, "POSTING_CARD_PRICE")
        img = card.select_one('[data-qa="POSTING_CARD_GALLERY"] img')
        # El alt de la primera foto trae el título: "Departamento · 46m² · 2 Ambientes · <título>".
        titulo = (img.get("alt") or "").split(" · ")[-1].strip() if img else ""
        descripcion = _qa(card, "POSTING_CARD_DESCRIPTION")

        avisos.append(
            Aviso(
                fuente=FUENTE,
                id=pid,
                url=url,
                titulo=titulo or descripcion[:80],
                precio=parsear_numero(precio_txt),
                moneda=detectar_moneda(precio_txt),
                expensas=parsear_numero(_qa(card, "expensas")),
                ubicacion=_qa(card, "POSTING_CARD_LOCATION"),
                direccion=texto_de(card.select_one('[class*="location-address"]')),
                descripcion=descripcion,
                imagen=(img.get("src") or img.get("data-src") or "") if img else "",
                **parsear_caracteristicas(_qa(card, "POSTING_CARD_FEATURES")),
            )
        )
    return avisos


def url_listado(url: str) -> str:
    """La vista de mapa (...-map.html) no trae las tarjetas en el HTML: se pasa a vista de lista."""
    partes = urlsplit(url)
    return partes._replace(path=re.sub(r"-map\.html$", ".html", partes.path)).geturl()


def url_pagina(url: str, pagina: int) -> str:
    """.../departamentos-alquiler-palermo.html -> ...-pagina-2.html"""
    if pagina <= 1:
        return url
    partes = urlsplit(url)
    ruta = re.sub(r"-pagina-\d+(?=\.html$)", "", partes.path)
    ruta = re.sub(r"\.html$", f"-pagina-{pagina}.html", ruta)
    return partes._replace(path=ruta).geturl()
