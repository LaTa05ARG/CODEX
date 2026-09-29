"""Envío de mails por SMTP. Credenciales por variables de entorno:

SMTP_USER, SMTP_PASSWORD, MAIL_TO (obligatorias; MAIL_TO admite varias separadas por coma)
SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 465), MAIL_FROM (default SMTP_USER)
"""

from __future__ import annotations

import html
import os
import smtplib
import ssl
from email.message import EmailMessage

from .modelo import Aviso


class ConfigMailFaltante(Exception):
    pass


def _fmt_num(valor: float | None) -> str:
    return f"{valor:,.0f}".replace(",", ".") if valor is not None else "?"


def _precio(a: Aviso) -> str:
    if a.precio is None:
        return "Consultar precio"
    return f"{'USD' if a.moneda == 'USD' else '$'} {_fmt_num(a.precio)}"


def _resumen(a: Aviso) -> str:
    partes = [_precio(a)]
    if a.expensas:
        partes.append(f"+ $ {_fmt_num(a.expensas)} expensas")
    if a.ambientes:
        partes.append(f"{a.ambientes} amb.")
    if a.dormitorios:
        partes.append(f"{a.dormitorios} dorm.")
    if a.m2:
        partes.append(f"{a.m2:g} m²")
    return " · ".join(partes)


def asunto(avisos: list[Aviso], busqueda: str) -> str:
    if len(avisos) == 1:
        a = avisos[0]
        return f"[{busqueda}] {_precio(a)} · {a.ubicacion or a.titulo} ({a.fuente})"
    return f"[{busqueda}] {len(avisos)} departamentos nuevos"


def cuerpo_texto(avisos: list[Aviso]) -> str:
    bloques = []
    for a in avisos:
        lugar = ", ".join(p for p in (a.direccion, a.ubicacion) if p)
        bloques.append(f"{a.titulo}\n{_resumen(a)}\n{lugar}\n{a.fuente}: {a.url}")
    return "\n\n".join(bloques) + "\n"


def cuerpo_html(avisos: list[Aviso]) -> str:
    e = html.escape
    filas = []
    for a in avisos:
        lugar = ", ".join(p for p in (a.direccion, a.ubicacion) if p)
        foto = (
            f'<td style="padding:8px;vertical-align:top;width:160px">'
            f'<a href="{e(a.url)}"><img src="{e(a.imagen)}" width="150" style="border-radius:6px"></a></td>'
            if a.imagen
            else ""
        )
        filas.append(
            f"<tr>{foto}<td style='padding:8px;vertical-align:top;font-family:sans-serif'>"
            f"<a href='{e(a.url)}' style='font-size:16px;font-weight:bold'>{e(a.titulo or 'Ver aviso')}</a><br>"
            f"<span style='font-size:15px'>{e(_resumen(a))}</span><br>"
            f"<span style='color:#555'>{e(lugar)}</span><br>"
            f"<span style='color:#888;font-size:12px'>{e(a.fuente)}</span></td></tr>"
        )
    return f"<table style='border-collapse:collapse'>{''.join(filas)}</table>"


def _mandar(asunto_mail: str, texto: str, html_mail: str) -> None:
    usuario = os.environ.get("SMTP_USER")
    clave = os.environ.get("SMTP_PASSWORD")
    destino = os.environ.get("MAIL_TO")
    if not (usuario and clave and destino):
        raise ConfigMailFaltante("Faltan SMTP_USER, SMTP_PASSWORD o MAIL_TO")
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    puerto = int(os.environ.get("SMTP_PORT") or 465)

    msg = EmailMessage()
    msg["Subject"] = asunto_mail
    msg["From"] = os.environ.get("MAIL_FROM") or usuario
    msg["To"] = destino
    msg.set_content(texto)
    msg.add_alternative(html_mail, subtype="html")

    contexto = ssl.create_default_context()
    if puerto == 465:
        with smtplib.SMTP_SSL(host, puerto, context=contexto, timeout=30) as s:
            s.login(usuario, clave)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, puerto, timeout=30) as s:
            s.starttls(context=contexto)
            s.login(usuario, clave)
            s.send_message(msg)


def enviar(avisos: list[Aviso], busqueda: str) -> None:
    _mandar(asunto(avisos, busqueda), cuerpo_texto(avisos), cuerpo_html(avisos))


def enviar_prueba() -> None:
    texto = (
        "Las alertas de departamentos están configuradas correctamente.\n"
        "Desde ahora vas a recibir un mail por cada aviso nuevo que cumpla los filtros.\n"
    )
    _mandar("[Alertas de departamentos] Mail de prueba", texto, f"<p>{html.escape(texto)}</p>")
