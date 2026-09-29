"""Condiciones que debe cumplir un aviso para disparar el mail.

Si al aviso le falta un dato (p. ej. no informa m²), el filtro correspondiente
no lo descarta: es preferible un mail de más que perder un departamento.
La excepción es el precio, controlada por `aceptar_sin_precio`.
"""

from __future__ import annotations

import re

from .modelo import Aviso, normalizar

_NUMERICOS = {
    "ambientes_min": ("ambientes", min),
    "ambientes_max": ("ambientes", max),
    "dormitorios_min": ("dormitorios", min),
    "dormitorios_max": ("dormitorios", max),
    "banos_min": ("banos", min),
    "m2_min": ("m2", min),
    "m2_max": ("m2", max),
    "expensas_max": ("expensas", max),
}
_LISTAS = ("ubicacion_incluye", "palabras_requeridas", "palabras_excluidas")
_PRECIOS = ("precio_min", "precio_max")
CLAVES = set(_NUMERICOS) | set(_LISTAS) | set(_PRECIOS) | {"aceptar_sin_precio"}


def validar(filtros: dict, contexto: str) -> None:
    desconocidas = set(filtros) - CLAVES
    if desconocidas:
        raise ValueError(f"{contexto}: filtros desconocidos {sorted(desconocidas)}. Válidos: {sorted(CLAVES)}")
    for clave in _NUMERICOS:
        v = filtros.get(clave)
        if v is not None and not isinstance(v, (int, float)):
            raise ValueError(f"{contexto}: '{clave}' debe ser un número")
    for clave in _PRECIOS:
        v = filtros.get(clave)
        if v is not None and not (isinstance(v, dict) and set(v) <= {"ARS", "USD"}):
            raise ValueError(f"{contexto}: '{clave}' debe ser un mapa por moneda, p. ej. {{ARS: 900000, USD: 800}}")
    for clave in _LISTAS:
        v = filtros.get(clave)
        if v is not None and not isinstance(v, list):
            raise ValueError(f"{contexto}: '{clave}' debe ser una lista")


def _barrio(aviso: Aviso) -> str:
    """La ubicación sin la calle: 'Av. Belgrano 1500, Monserrat, Capital Federal' -> 'monserrat, capital federal'.

    Evita que el nombre de una calle (Av. Belgrano, Av. Pueyrredón) cuente como barrio.
    MercadoLibre pone la dirección como primera parte; Zonaprop la tiene aparte en `direccion`.
    """
    partes = [p.strip() for p in aviso.ubicacion.split(",") if p.strip()]
    if len(partes) >= 3:
        partes = partes[1:]
    return normalizar(", ".join(p for p in partes if not re.search(r"\d", p)))


def motivo_rechazo(aviso: Aviso, filtros: dict) -> str | None:
    """Devuelve None si el aviso cumple todas las condiciones, o el motivo por el que no."""
    precio_min = filtros.get("precio_min")
    precio_max = filtros.get("precio_max")
    if precio_min or precio_max:
        if aviso.precio is None or aviso.moneda is None:
            if not filtros.get("aceptar_sin_precio", False):
                return "sin precio publicado"
        else:
            topes = [t for t in (precio_min, precio_max) if t]
            if not any(aviso.moneda in t for t in topes):
                return f"precio en {aviso.moneda}, moneda no incluida en los filtros"
            if precio_min and aviso.moneda in precio_min and aviso.precio < precio_min[aviso.moneda]:
                return f"precio {aviso.precio:.0f} < mínimo"
            if precio_max and aviso.moneda in precio_max and aviso.precio > precio_max[aviso.moneda]:
                return f"precio {aviso.precio:.0f} > máximo"

    for clave, (atributo, tipo) in _NUMERICOS.items():
        limite = filtros.get(clave)
        valor = getattr(aviso, atributo)
        if limite is None or valor is None:
            continue
        if tipo is min and valor < limite:
            return f"{atributo} {valor:g} < {limite:g}"
        if tipo is max and valor > limite:
            return f"{atributo} {valor:g} > {limite:g}"

    texto = normalizar(f"{aviso.titulo} {aviso.descripcion}")
    lugar = normalizar(f"{aviso.ubicacion} {aviso.direccion}")

    zonas = filtros.get("ubicacion_incluye")
    barrio = _barrio(aviso)
    if zonas and barrio and not any(normalizar(z) in barrio for z in zonas):
        return f"ubicación '{aviso.ubicacion}' fuera de las zonas buscadas"

    requeridas = filtros.get("palabras_requeridas")
    if requeridas and not any(normalizar(p) in texto for p in requeridas):
        return "no menciona ninguna palabra requerida"

    for palabra in filtros.get("palabras_excluidas") or []:
        if normalizar(palabra) in f"{texto} {lugar}":
            return f"contiene palabra excluida '{palabra}'"

    return None
