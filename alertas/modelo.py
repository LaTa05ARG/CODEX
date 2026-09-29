"""Modelo común de aviso y utilidades de parseo compartidas por ambos sitios."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Aviso:
    fuente: str  # "MercadoLibre" | "Zonaprop"
    id: str
    url: str
    titulo: str = ""
    precio: float | None = None
    moneda: str | None = None  # "ARS" | "USD"
    expensas: float | None = None
    ambientes: int | None = None
    dormitorios: int | None = None
    banos: int | None = None
    m2_total: float | None = None
    m2_cubierto: float | None = None
    ubicacion: str = ""
    direccion: str = ""
    descripcion: str = ""
    imagen: str = ""

    @property
    def clave(self) -> str:
        return f"{self.fuente}:{self.id}"

    @property
    def m2(self) -> float | None:
        return self.m2_total or self.m2_cubierto


_NUMERO = re.compile(r"\d[\d.,]*")


def parsear_numero(texto: str | None) -> float | None:
    """'$ 890.000' -> 890000.0 ; '45,5 m²' -> 45.5 ; 'Consultar precio' -> None."""
    if not texto:
        return None
    m = _NUMERO.search(texto)
    if not m:
        return None
    crudo = m.group(0).rstrip(".,")
    # En es-AR el punto separa miles y la coma decimales. Un bloque final de
    # 3 dígitos tras el punto indica separador de miles ("1.100" = 1100).
    if "." in crudo and len(crudo.split(".")[-1]) == 3:
        crudo = crudo.replace(".", "")
    crudo = crudo.replace(",", ".")
    try:
        return float(crudo)
    except ValueError:
        return None


def detectar_moneda(texto: str | None) -> str | None:
    if not texto:
        return None
    t = texto.upper()
    if "USD" in t or "US$" in t or "U$S" in t or "U$D" in t:
        return "USD"
    if "$" in t or "ARS" in t:
        return "ARS"
    return None


def _entero(patron: str, texto: str) -> int | None:
    m = re.search(patron, texto, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _decimal(patron: str, texto: str) -> float | None:
    m = re.search(patron, texto, re.IGNORECASE)
    return parsear_numero(m.group(1)) if m else None


def parsear_caracteristicas(texto: str) -> dict:
    """Extrae ambientes, dormitorios, baños y m² de textos tipo
    '50 m² tot. | 45 m² cub. | 2 amb. | 1 dorm. | 1 baño' o
    '2 dormitorios, 1 baño, 55 m² cubiertos'."""
    ambientes = _entero(r"(\d+)\s*amb", texto)
    if ambientes is None and re.search(r"monoambiente", texto, re.IGNORECASE):
        ambientes = 1
    m2_total = _decimal(r"([\d.,]+)\s*m(?:²|2)\s*(?:tot|totales)", texto)
    m2_cubierto = _decimal(r"([\d.,]+)\s*m(?:²|2)\s*cub", texto)
    if m2_total is None and m2_cubierto is None:
        m2_total = _decimal(r"([\d.,]+)\s*m(?:²|2)\b", texto)
    return {
        "ambientes": ambientes,
        "dormitorios": _entero(r"(\d+)\s*dorm", texto),
        "banos": _entero(r"(\d+)\s*baño", texto),
        "m2_total": m2_total,
        "m2_cubierto": m2_cubierto,
    }


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar palabras clave."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def texto_de(nodo) -> str:
    return nodo.get_text(" ", strip=True) if nodo else ""
