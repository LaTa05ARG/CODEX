from pathlib import Path

import pytest

from alertas import __main__ as app
from alertas import filtros, mercadolibre, notificar, zonaprop
from alertas.estado import Estado
from alertas.modelo import Aviso, parsear_caracteristicas, parsear_numero

FIXTURES = Path(__file__).parent / "fixtures"


def leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text()


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("$ 850.000", 850000),
        ("USD 1.100", 1100),
        ("$ 1.250.000", 1250000),
        ("45,5 m²", 45.5),
        ("650", 650),
        ("Consultar precio", None),
        ("", None),
    ],
)
def test_parsear_numero(texto, esperado):
    assert parsear_numero(texto) == esperado


def test_parsear_caracteristicas():
    zp = parsear_caracteristicas("52 m² tot. | 48 m² cub. | 2 amb. | 1 dorm. | 1 baño")
    assert zp == {"ambientes": 2, "dormitorios": 1, "banos": 1, "m2_total": 52, "m2_cubierto": 48}
    ml = parsear_caracteristicas("Monoambiente | 32 m² totales")
    assert ml["ambientes"] == 1 and ml["m2_total"] == 32


def test_zonaprop_parsea_tarjetas():
    avisos = zonaprop.parsear_listado(leer("zonaprop_listado.html"))
    assert [a.id for a in avisos] == ["60000001", "60000002", "60000003"]
    a = avisos[0]
    assert a.url == "https://www.zonaprop.com.ar/propiedades/clasificado/alclapin-2-ambientes-con-balcon-palermo-60000001.html"
    assert a.titulo == "2 Ambientes Con Balcón En Palermo"
    assert (a.precio, a.moneda, a.expensas) == (850000, "ARS", 110000)
    assert (a.ambientes, a.dormitorios, a.m2_total, a.m2_cubierto) == (2, 1, 52, 48)
    assert a.ubicacion == "Palermo Soho, Palermo"
    assert a.direccion == "Gorriti al 4800"
    assert a.imagen.startswith("https://imgar.zonapropcdn.com/")
    assert (avisos[1].precio, avisos[1].moneda, avisos[1].expensas) == (1100, "USD", None)
    assert avisos[2].precio is None


def test_zonaprop_url_pagina():
    base = "https://www.zonaprop.com.ar/departamentos-alquiler-palermo-orden-publicado-descendente.html"
    assert zonaprop.url_pagina(base, 1) == base
    assert zonaprop.url_pagina(base, 3).endswith("-orden-publicado-descendente-pagina-3.html")
    assert zonaprop.url_pagina(zonaprop.url_pagina(base, 2), 3) == zonaprop.url_pagina(base, 3)


def test_mercadolibre_parsea_tarjetas():
    html = leer("mercadolibre_listado.html")
    avisos = mercadolibre.parsear_listado(html)
    assert [a.id for a in avisos] == ["MLA1500000001", "MLA1500000002", "MLA1500000003"]
    a = avisos[0]
    assert a.url == "https://departamento.mercadolibre.com.ar/MLA-1500000001-alquiler-2-ambientes-palermo-_JM"
    assert a.titulo == "Alquiler 2 Ambientes Palermo Con Balcón"
    assert (a.precio, a.moneda, a.ambientes, a.dormitorios, a.m2_cubierto) == (780000, "ARS", 2, 1, 45)
    assert a.ubicacion == "Honduras 5000, Palermo Soho, Capital Federal"
    # Aviso promocionado: precio vigente (no el tachado) y URL real, no la del tracker.
    b = avisos[1]
    assert (b.precio, b.moneda, b.ambientes) == (650, "USD", 1)
    assert b.url == "https://departamento.mercadolibre.com.ar/MLA-1500000002-monoambiente-palermo-_JM"
    assert b.imagen == "https://http2.mlstatic.com/D_Q_NP_2-O.webp"
    # Layout anterior.
    c = avisos[2]
    assert (c.titulo, c.precio, c.ambientes, c.m2_total) == ("3 Ambientes Belgrano R", 1250000, 3, 70)
    assert mercadolibre.url_siguiente(html).endswith("/_Desde_49_NoIndex_True")


def _aviso(**kw) -> Aviso:
    base = dict(fuente="Zonaprop", id="1", url="u", titulo="2 amb luminoso", precio=800000, moneda="ARS",
                expensas=100000, ambientes=2, m2_total=50, ubicacion="Palermo Soho, Palermo")
    return Aviso(**{**base, **kw})


FILTROS = {
    "precio_max": {"ARS": 900000, "USD": 700},
    "expensas_max": 150000,
    "ambientes_min": 2,
    "m2_min": 40,
    "ubicacion_incluye": ["Palermo", "Belgrano"],
    "palabras_excluidas": ["temporario"],
}


@pytest.mark.parametrize(
    "cambios, pasa",
    [
        ({}, True),
        ({"precio": 950000}, False),
        ({"precio": 650, "moneda": "USD"}, True),
        ({"precio": 750, "moneda": "USD"}, False),
        ({"precio": None, "moneda": None}, False),
        ({"expensas": 200000}, False),
        ({"expensas": None}, True),  # dato faltante no descarta
        ({"ambientes": 1}, False),
        ({"m2_total": None, "m2_cubierto": 45}, True),
        ({"m2_total": 35}, False),
        ({"ubicacion": "Caballito, Capital Federal"}, False),
        ({"titulo": "Alquiler TEMPORARIO"}, False),
    ],
)
def test_filtros(cambios, pasa):
    assert (filtros.motivo_rechazo(_aviso(**cambios), FILTROS) is None) == pasa


def test_filtros_tildes_y_requeridas():
    f = {"palabras_requeridas": ["balcon", "terraza"]}
    assert filtros.motivo_rechazo(_aviso(titulo="Con BALCÓN"), f) is None
    assert filtros.motivo_rechazo(_aviso(titulo="Interno"), f) is not None


def test_validar_filtros():
    filtros.validar(FILTROS, "ok")
    with pytest.raises(ValueError):
        filtros.validar({"precio_maximo": 1}, "x")
    with pytest.raises(ValueError):
        filtros.validar({"precio_max": 900000}, "x")


def test_mail():
    avisos = zonaprop.parsear_listado(leer("zonaprop_listado.html"))[:1]
    assert notificar.asunto(avisos, "Palermo") == "[Palermo] $ 850.000 · Palermo Soho, Palermo (Zonaprop)"
    texto = notificar.cuerpo_texto(avisos)
    assert "+ $ 110.000 expensas · 2 amb. · 1 dorm. · 52 m²" in texto
    assert avisos[0].url in notificar.cuerpo_html(avisos)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Config con una URL de cada sitio que devuelve las fixtures, y mails capturados."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "busquedas:\n"
        "  - nombre: Test\n"
        "    urls:\n"
        "      - https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html\n"
        "      - https://inmuebles.mercadolibre.com.ar/departamentos/alquiler/capital-federal/palermo/\n"
        "    filtros:\n"
        "      precio_max: {ARS: 900000, USD: 700}\n"
        "      palabras_excluidas: [temporario]\n"
    )
    paginas = {
        "zonaprop": [leer("zonaprop_listado.html")],
        "mercadolibre": [leer("mercadolibre_listado.html")],
    }
    monkeypatch.setattr(app, "descargar", lambda url: paginas[app.sitio(url)][0])
    monkeypatch.setattr(app, "_pausa", lambda: None)
    enviados = []
    monkeypatch.setattr(notificar, "enviar", lambda avisos, busqueda: enviados.append([a.clave for a in avisos]))
    return app.cargar_config(config), tmp_path / "vistos.json", paginas, enviados


def test_flujo_completo(entorno):
    config, ruta_estado, paginas, enviados = entorno

    # 1ª corrida: registra lo publicado sin mandar mails.
    estado = Estado(ruta_estado)
    assert app.correr(config, estado) == 0
    estado.guardar()
    assert enviados == []

    # 2ª corrida sin cambios: nada nuevo.
    assert app.correr(config, Estado(ruta_estado)) == 0
    assert enviados == []

    # Aparece un aviso nuevo en Zonaprop que cumple y otro que no.
    nuevo = leer("zonaprop_listado.html").replace("60000001", "60000099")
    caro = nuevo.replace("60000002", "60000098")
    paginas["zonaprop"][0] = caro
    estado = Estado(ruta_estado)
    assert app.correr(config, estado) == 0
    estado.guardar()
    assert enviados == [["Zonaprop:60000099"]]

    # No se repite.
    assert app.correr(config, Estado(ruta_estado)) == 0
    assert enviados == [["Zonaprop:60000099"]]


def test_falla_de_envio_reintenta(entorno, monkeypatch):
    config, ruta_estado, paginas, enviados = entorno
    config.notificar_en_primera_corrida = True

    def falla(avisos, busqueda):
        raise OSError("SMTP caído")

    monkeypatch.setattr(notificar, "enviar", falla)
    estado = Estado(ruta_estado)
    assert app.correr(config, estado) == 1
    estado.guardar()

    monkeypatch.setattr(notificar, "enviar", lambda avisos, busqueda: enviados.append([a.clave for a in avisos]))
    assert app.correr(config, Estado(ruta_estado)) == 0
    # Zonaprop 60000001 (ARS 850k) y ML 1 (ARS 780k) y 2 (USD 650) cumplen; el resto no.
    assert sorted(c for tanda in enviados for c in tanda) == [
        "MercadoLibre:MLA1500000001",
        "MercadoLibre:MLA1500000002",
        "Zonaprop:60000001",
    ]


def test_todas_las_urls_fallan(entorno, monkeypatch):
    config, ruta_estado, _, _ = entorno

    def bloqueada(url):
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(app, "descargar", bloqueada)
    assert app.correr(config, Estado(ruta_estado)) == 1


def test_detecta_desafio_antibot():
    from alertas.http import es_desafio

    assert es_desafio("<html><head><title>Just a moment...</title></head><body></body></html>")
    assert es_desafio('<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>')
    # Un listado real que carga scripts de Cloudflare no es un desafío.
    assert not es_desafio(leer("zonaprop_listado.html") + '<script src="/cdn-cgi/challenge-platform/x.js"></script>')
    assert not es_desafio(leer("mercadolibre_listado.html"))


def test_url_mapa_pasa_a_lista():
    ml = (
        "https://inmuebles.mercadolibre.com.ar/departamentos/venta/apto-credito/mas-de-3-dormitorios/"
        "_DisplayType_M_PriceRange_0USD-400000USD_PublishedToday_YES_NoIndex_True_PARKING*LOTS_1-*"
    )
    assert mercadolibre.url_listado(ml) == ml.replace("_DisplayType_M", "")
    assert mercadolibre.url_listado(ml.replace("_DisplayType_M", "")) == ml.replace("_DisplayType_M", "")
    zp = "https://www.zonaprop.com.ar/departamentos-venta-belgrano-palermo-recoleta-menos-400000-dolar-map.html"
    assert zonaprop.url_listado(zp) == zp.replace("-map.html", ".html")
    assert zonaprop.url_pagina(zonaprop.url_listado(zp), 2).endswith("-400000-dolar-pagina-2.html")


def test_config_del_repo_es_valida():
    config = app.cargar_config(Path(__file__).parent.parent / "config.yaml")
    assert config.busquedas and all(b.urls for b in config.busquedas)
