"""Revisa las búsquedas de config.yaml y manda un mail por cada departamento nuevo
que cumpla los filtros.

Uso:  python -m alertas [--config config.yaml] [--estado data/vistos.json] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from . import filtros, mercadolibre, notificar, zonaprop
from .estado import Estado
from .http import descargar
from .modelo import Aviso

log = logging.getLogger("alertas")

# Si en una corrida aparecen más avisos que esto, se agrupan en un solo mail.
MAX_MAILS_INDIVIDUALES = 10


@dataclass
class Busqueda:
    nombre: str
    urls: list[str]
    filtros: dict = field(default_factory=dict)


@dataclass
class Config:
    busquedas: list[Busqueda]
    paginas: int = 1
    un_mail_por_aviso: bool = True
    notificar_en_primera_corrida: bool = False


def sitio(url: str) -> str:
    host = urlsplit(url).netloc
    if host.endswith("zonaprop.com.ar"):
        return "zonaprop"
    if "mercadolibre.com" in host:
        return "mercadolibre"
    raise ValueError(f"URL no soportada (solo MercadoLibre o Zonaprop): {url}")


def cargar_config(ruta: Path) -> Config:
    datos = yaml.safe_load(ruta.read_text()) or {}
    opciones = datos.get("opciones") or {}
    busquedas = []
    for i, b in enumerate(datos.get("busquedas") or [], 1):
        nombre = b.get("nombre") or f"Búsqueda {i}"
        urls = b.get("urls") or []
        if not urls:
            raise ValueError(f"{nombre}: falta 'urls'")
        for u in urls:
            sitio(u)
        f = b.get("filtros") or {}
        filtros.validar(f, nombre)
        busquedas.append(Busqueda(nombre=nombre, urls=urls, filtros=f))
    if not busquedas:
        raise ValueError("config.yaml no tiene ninguna búsqueda")
    return Config(
        busquedas=busquedas,
        paginas=int(opciones.get("paginas", 1)),
        un_mail_por_aviso=bool(opciones.get("un_mail_por_aviso", True)),
        notificar_en_primera_corrida=bool(opciones.get("notificar_en_primera_corrida", False)),
    )


def _pausa() -> None:
    time.sleep(random.uniform(2, 5))


def obtener_avisos(url: str, paginas: int) -> list[Aviso]:
    avisos: list[Aviso] = []
    if sitio(url) == "zonaprop":
        for n in range(1, paginas + 1):
            if n > 1:
                _pausa()
            pagina = zonaprop.parsear_listado(descargar(zonaprop.url_pagina(url, n)))
            avisos += pagina
            if not pagina:
                break
    else:
        siguiente: str | None = url
        for n in range(paginas):
            if n > 0:
                _pausa()
            html = descargar(siguiente)
            avisos += mercadolibre.parsear_listado(html)
            siguiente = mercadolibre.url_siguiente(html)
            if not siguiente:
                break
    return avisos


def _resumen_actions(linea: str) -> None:
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a") as f:
            f.write(linea + "\n")


def _enviar(avisos: list[Aviso], busqueda: Busqueda, estado: Estado, config: Config, dry_run: bool) -> bool:
    if config.un_mail_por_aviso and len(avisos) <= MAX_MAILS_INDIVIDUALES:
        tandas = [[a] for a in avisos]
    else:
        tandas = [avisos]
    ok = True
    for tanda in tandas:
        if dry_run:
            print(f"--- [dry-run] {notificar.asunto(tanda, busqueda.nombre)}\n{notificar.cuerpo_texto(tanda)}")
            continue
        try:
            notificar.enviar(tanda, busqueda.nombre)
        except Exception as e:  # noqa: BLE001
            log.error("No se pudo enviar el mail de '%s': %s", busqueda.nombre, e)
            ok = False
            continue
        # Solo se marcan como vistos si el mail salió; si falló, se reintenta en la próxima corrida.
        for a in tanda:
            estado.marcar(f"{busqueda.nombre}|{a.clave}")
        log.info("Mail enviado: %s", notificar.asunto(tanda, busqueda.nombre))
    return ok


def correr(config: Config, estado: Estado, dry_run: bool = False, ignorar_vistos: bool = False) -> int:
    urls_total = urls_fallidas = 0
    envios_ok = True
    for busqueda in config.busquedas:
        nuevos: dict[str, Aviso] = {}
        for url in busqueda.urls:
            urls_total += 1
            clave_url = f"{busqueda.nombre}|{url}"
            try:
                avisos = obtener_avisos(url, config.paginas)
            except Exception as e:  # noqa: BLE001
                urls_fallidas += 1
                log.error("No se pudo leer %s: %s", url, e)
                print(f"::warning::No se pudo leer {url}: {e}")
                _resumen_actions(f"- ⚠️ `{url}`: {e}")
                continue

            primera_vez = clave_url not in estado.urls_inicializadas
            silenciar = primera_vez and not config.notificar_en_primera_corrida and not ignorar_vistos
            candidatos = 0
            for a in avisos:
                clave = f"{busqueda.nombre}|{a.clave}"
                if (estado.visto(clave) and not ignorar_vistos) or silenciar:
                    # Refresca la fecha para que no se olvide mientras siga publicado.
                    estado.marcar(clave)
                    continue
                # Los rechazados no se marcan: si bajan de precio o cambian los filtros,
                # se vuelven a evaluar en la próxima corrida.
                motivo = filtros.motivo_rechazo(a, busqueda.filtros)
                if motivo:
                    log.debug("Descartado %s (%s): %s", a.clave, a.url, motivo)
                    continue
                candidatos += 1
                nuevos.setdefault(a.clave, a)
            estado.urls_inicializadas.add(clave_url)

            detalle = "primera corrida: se registran sin notificar" if silenciar else f"{candidatos} nuevos que cumplen"
            log.info("[%s] %s → %d avisos (%s)", busqueda.nombre, url, len(avisos), detalle)
            _resumen_actions(f"- `{url}`: {len(avisos)} avisos, {detalle}")

        if nuevos:
            envios_ok &= _enviar(list(nuevos.values()), busqueda, estado, config, dry_run)

    if urls_total and urls_fallidas == urls_total:
        log.error("Fallaron todas las URLs (%d). ¿Bloqueo anti-bot o cambió el sitio?", urls_total)
        return 1
    return 0 if envios_ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="alertas", description=__doc__)
    p.add_argument("--config", type=Path, default=Path("config.yaml"))
    p.add_argument("--estado", type=Path, default=Path("data/vistos.json"))
    p.add_argument("--dry-run", action="store_true", help="muestra los mails en consola, no envía ni guarda estado")
    p.add_argument(
        "--ignorar-vistos",
        action="store_true",
        help="trata todos los avisos como nuevos (útil con --dry-run para probar los filtros)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="muestra por qué se descarta cada aviso")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    config = cargar_config(args.config)
    estado = Estado(args.estado)
    codigo = correr(config, estado, dry_run=args.dry_run, ignorar_vistos=args.ignorar_vistos)
    if not args.dry_run:
        estado.guardar()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
