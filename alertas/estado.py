"""Registro de avisos ya vistos, para mandar mail solo por los nuevos.

Se guarda en un JSON que el workflow de GitHub Actions commitea al repo.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Un aviso que no aparece en ninguna búsqueda durante este tiempo se olvida.
RETENCION = timedelta(days=60)


class Estado:
    def __init__(self, ruta: Path):
        self.ruta = ruta
        datos = json.loads(ruta.read_text()) if ruta.exists() else {}
        self.vistos: dict[str, str] = datos.get("vistos", {})
        self.urls_inicializadas: set[str] = set(datos.get("urls_inicializadas", []))
        self.hoy = datetime.now(timezone.utc).date()

    def visto(self, clave: str) -> bool:
        return clave in self.vistos

    def marcar(self, clave: str) -> None:
        # Solo la fecha: así el archivo cambia (y se commitea) a lo sumo una vez por día
        # por aviso, en lugar de en cada corrida.
        self.vistos[clave] = self.hoy.isoformat()

    def guardar(self) -> None:
        limite = self.hoy - RETENCION
        self.vistos = {k: v for k, v in self.vistos.items() if date.fromisoformat(v) >= limite}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(
            json.dumps(
                {
                    "urls_inicializadas": sorted(self.urls_inicializadas),
                    "vistos": dict(sorted(self.vistos.items())),
                },
                indent=1,
                ensure_ascii=False,
            )
            + "\n"
        )
