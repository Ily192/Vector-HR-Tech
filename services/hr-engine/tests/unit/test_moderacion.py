"""Moderación de vacantes sin IA (ADR-022): reglas fijas, insignia y decisión.

Las reglas buscan frases de las vacantes falsas de siempre. Estos tests fijan dos
cosas a la vez: que cada señal se detecta con y sin acentos, y que una vacante
normal —sobre todo una de ventas con comisiones— no cae.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.moderacion import (
    MOTIVO_PRIMERA_VACANTE,
    MOTIVO_RECLUTADOR,
    RAFAGA_MINIMA,
    EstadoDeModeracion,
    Gravedad,
    Marca,
    VacanteAModerar,
    decidir,
    dominio_registrable,
    evaluar,
    insignia_por_dominio,
    plano,
    revisar_texto,
)


def _reglas(titulo: str, descripcion: str = "") -> set[str]:
    return {m.regla for m in revisar_texto(titulo, descripcion)}


# ─────────────────────────────── texto plano ───────────────────────────────


def test_plano_quita_acentos_y_mayusculas_sin_cambiar_el_largo() -> None:
    original = "Ejecutivo de VENTAS · Señal ÁÉÍÓÚ İstanbul"
    assert plano(original) == "ejecutivo de ventas · senal aeiou istanbul"
    assert len(plano(original)) == len(original)


def test_la_cita_sale_del_original_con_sus_acentos() -> None:
    (marca,) = revisar_texto("Asesor", "Para iniciar DEBERÁS PAGAR tu kit de inicio.")
    assert marca.regla == "pago"
    assert marca.cita == "DEBERÁS PAGAR"


# ─────────────────────────────── vacantes normales ───────────────────────────────

NORMALES = [
    (
        "Ejecutivo de ventas",
        "Sueldo base de $9,000 más comisiones, con ingresos de hasta $25,000 al mes. "
        "Experiencia de 1 año en ventas de campo. Presencial en Monterrey. Te pagamos "
        "la capacitación y recibes un kit de bienvenida.",
    ),
    (
        "Asesor comercial",
        "Pago semanal, comisiones sin tope y prestaciones de ley. Requisito: cuenta "
        "bancaria para el depósito de nómina al contratarte.",
    ),
    (
        "Analista de inventarios",
        "Controlarás el inventario del almacén y los conteos cíclicos con el equipo de turno.",
    ),
    (
        "Desarrollador backend",
        "Trabajo remoto desde cualquier país de LATAM. Python, FastAPI y PostgreSQL. "
        "3 años de experiencia. Pago en USD.",
    ),
    (
        "Recepcionista",
        "Atención en recepción y agenda. Capacitación pagada. Lleva tu CV a la entrevista.",
    ),
    (
        "Auxiliar contable",
        "Conciliaciones bancarias, cuentas por pagar y registro de facturas en el sistema.",
    ),
]


@pytest.mark.parametrize(("titulo", "descripcion"), NORMALES, ids=[t for t, _ in NORMALES])
def test_una_vacante_normal_no_cae(titulo: str, descripcion: str) -> None:
    assert revisar_texto(titulo, descripcion) == []


# ─────────────────────────────── pago ───────────────────────────────


@pytest.mark.parametrize(
    "texto",
    [
        "Para iniciar debes pagar $500 de inscripción.",
        "Deberás depositar una cuota de registro de 300 pesos.",
        "Costo de capacitación: $800, reembolsable al primer mes.",
        "Compra tu kit y empieza a vender hoy.",
        "Incluye kit de inicio con productos.",
        "Se requiere pagar el curso de inducción.",
        "Cuota única de inscripción de $250.",
        "TIENES QUE PAGAR EL UNIFORME",
    ],
)
def test_pago_se_detecta(texto: str) -> None:
    marcas = revisar_texto("Promotor", texto)
    assert "pago" in {m.regla for m in marcas}
    assert next(m for m in marcas if m.regla == "pago").gravedad is Gravedad.ALTA


# ─────────────────────────────── datos bancarios y documentos ───────────────────────────────


@pytest.mark.parametrize(
    "texto",
    [
        "Envíanos tu número de cuenta para darte de alta.",
        "Necesitamos tus datos bancarios para el registro.",
        "Manda tu CLABE interbancaria por correo.",
        "Comparte el NIP de tu tarjeta para validar.",
        "Pide el código de seguridad de tu tarjeta.",
        "Indica el número de tarjeta de débito.",
    ],
)
def test_datos_bancarios_se_detectan(texto: str) -> None:
    assert "datos_bancarios" in _reglas("Capturista", texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Envía foto de tu INE antes de la entrevista.",
        "Manda tu CURP y RFC para agendar tu entrevista.",
        "Antes de la entrevista necesitamos tu cédula y pasaporte.",
    ],
)
def test_documentos_antes_de_la_entrevista(texto: str) -> None:
    marcas = revisar_texto("Auxiliar", texto)
    (marca,) = [m for m in marcas if m.regla == "documentos_antes"]
    assert marca.gravedad is Gravedad.MEDIA


def test_pedir_documentos_al_contratar_no_cae() -> None:
    assert _reglas("Auxiliar", "Al contratarte te pediremos INE, CURP y comprobante.") == set()


# ─────────────────────────────── contacto externo ───────────────────────────────


@pytest.mark.parametrize(
    "texto",
    [
        "Escríbenos por WhatsApp al 55 1234 5678.",
        "Informes solo por Telegram.",
        "Postúlate aquí: https://wa.me/5215512345678",
        "Llena el formulario: bit.ly/vacante-hoy",
        "Más info en https://t.me/empleos_rapidos",
        "Mándanos un wasap",
    ],
)
def test_contacto_externo(texto: str) -> None:
    assert "contacto_externo" in _reglas("Vendedor", texto)


def test_un_dominio_que_contiene_un_acortador_no_cae() -> None:
    assert _reglas("Vendedor", "Conoce más en https://www.mibit.ly-empresa.mx/") == set()


# ─────────────────────────────── multinivel, inversión y cripto ───────────────────────────────


@pytest.mark.parametrize(
    ("texto", "regla", "gravedad"),
    [
        ("Únete a nuestro negocio multinivel.", "multinivel", Gravedad.ALTA),
        ("Se requiere una inversión inicial mínima.", "multinivel", Gravedad.ALTA),
        ("Recuperas tu inversión en 2 meses.", "multinivel", Gravedad.ALTA),
        ("Invierte $1,000 y gana el doble.", "multinivel", Gravedad.ALTA),
        ("Opera criptomonedas desde tu casa.", "inversion_o_cripto", Gravedad.MEDIA),
        (
            "Sé tu propio jefe y alcanza tu libertad financiera.",
            "inversion_o_cripto",
            Gravedad.MEDIA,
        ),
        ("Aprende trading y forex.", "inversion_o_cripto", Gravedad.MEDIA),
    ],
)
def test_multinivel_inversion_y_cripto(texto: str, regla: str, gravedad: Gravedad) -> None:
    marcas = {m.regla: m for m in revisar_texto("Oportunidad", texto)}
    assert marcas[regla].gravedad is gravedad


def test_invertir_en_la_gente_no_cae() -> None:
    assert _reglas("Gerente", "Invertimos en tu desarrollo profesional.") == set()


# ─────────────────────────────── sueldo irreal ───────────────────────────────


def test_sueldo_irreal_es_la_combinacion_de_las_tres_cosas() -> None:
    texto = "Gana hasta $40,000 al mes sin experiencia, desde tu casa."
    (marca,) = revisar_texto("Asistente virtual", texto)
    assert marca.regla == "sueldo_irreal"
    assert marca.gravedad is Gravedad.MEDIA
    assert marca.cita == "Gana hasta $4"


@pytest.mark.parametrize(
    "texto",
    [
        "Gana hasta $40,000 al mes desde tu casa. Experiencia de 2 años.",
        "Gana hasta $40,000 al mes sin experiencia. Presencial en Guadalajara.",
        "Sin experiencia, home office, sueldo de $12,000 mensuales.",
    ],
)
def test_sin_las_tres_cosas_no_es_sueldo_irreal(texto: str) -> None:
    assert "sueldo_irreal" not in _reglas("Asistente", texto)


def test_dinero_facil_cae_solo() -> None:
    assert _reglas("Promotor", "Gana dinero fácil en tus ratos libres.") == {"sueldo_irreal"}


def test_pago_diario_alto_con_home_office_y_sin_experiencia() -> None:
    texto = "$1,500 diarios desde casa. No se requiere experiencia."
    assert _reglas("Capturista", texto) == {"sueldo_irreal"}


def test_una_marca_por_regla() -> None:
    texto = "Debes pagar el kit. También debes pagar el curso. Compra tu kit."
    marcas = revisar_texto("Promotor", texto)
    assert [m.regla for m in marcas] == ["pago"]
    assert marcas[0].cita == "Debes pagar"


def test_la_cita_larga_se_recorta() -> None:
    texto = (
        "Envía por correo " + "a" * 40 + " tu INE vigente " + "b" * 70 + " antes de la entrevista."
    )
    (marca,) = revisar_texto("Auxiliar", texto)
    assert marca.cita is not None and len(marca.cita) == 140
    assert marca.cita.startswith("Envía por correo") and marca.cita.endswith("…")


# ─────────────────────────────── la decisión ───────────────────────────────


def _vacante(
    *,
    titulo: str = "Analista de inventarios",
    descripcion: str = "Controlarás el inventario del almacén.",
    verificada: bool = True,
    publica_para: str = "propia",
    tiene_publicadas: bool = True,
    duplicada: bool = False,
    creadas: int = 1,
    cuenta_nueva: bool = False,
) -> VacanteAModerar:
    return VacanteAModerar(
        id=uuid4(),
        empresa_id=uuid4(),
        titulo=titulo,
        descripcion=descripcion,
        empresa_verificada=verificada,
        publica_para=publica_para,
        tiene_publicadas=tiene_publicadas,
        duplicada=duplicada,
        creadas_en_la_ultima_hora=creadas,
        cuenta_nueva=cuenta_nueva,
    )


def _decidir(v: VacanteAModerar) -> tuple[EstadoDeModeracion, list[str]]:
    d = decidir(v, evaluar(v))
    return d.estado, [m.regla for m in d.motivos]


def test_verificada_y_sin_riesgo_se_publica() -> None:
    assert _decidir(_vacante()) == (EstadoDeModeracion.PUBLICADA, [])


def test_verificada_publica_aunque_sea_su_primera() -> None:
    assert _decidir(_vacante(tiene_publicadas=False))[0] is EstadoDeModeracion.PUBLICADA


def test_la_primera_de_una_empresa_sin_verificar_va_a_revision() -> None:
    estado, reglas = _decidir(_vacante(verificada=False, tiene_publicadas=False))
    assert (estado, reglas) == (EstadoDeModeracion.EN_REVISION, ["primera_vacante"])


def test_la_segunda_de_una_empresa_sin_verificar_se_publica_si_no_hay_riesgo() -> None:
    assert _decidir(_vacante(verificada=False))[0] is EstadoDeModeracion.PUBLICADA


def test_un_reclutador_siempre_va_a_revision() -> None:
    estado, reglas = _decidir(_vacante(publica_para="clientes"))
    assert (estado, reglas) == (EstadoDeModeracion.EN_REVISION, ["reclutador_independiente"])


def test_riesgo_medio_va_a_revision_aunque_este_verificada() -> None:
    v = _vacante(descripcion="Informes solo por WhatsApp.")
    assert _decidir(v) == (EstadoDeModeracion.EN_REVISION, ["contacto_externo"])


def test_riesgo_alto_se_rechaza_aunque_este_verificada() -> None:
    v = _vacante(descripcion="Debes pagar tu kit. Escríbenos por WhatsApp.")
    d = decidir(v, evaluar(v))
    assert d.estado is EstadoDeModeracion.RECHAZADA
    assert d.riesgo is Gravedad.ALTA
    # Lo más grave primero, y cada uno con qué corregir.
    assert [m.regla for m in d.motivos] == ["pago", "contacto_externo"]
    assert all(m.corregir for m in d.motivos)


def test_un_reclutador_con_riesgo_alto_se_rechaza() -> None:
    v = _vacante(publica_para="clientes", descripcion="Manda tu número de cuenta.")
    assert _decidir(v)[0] is EstadoDeModeracion.RECHAZADA


def test_texto_duplicado_en_otra_cuenta_va_a_revision() -> None:
    assert _decidir(_vacante(duplicada=True)) == (EstadoDeModeracion.EN_REVISION, ["duplicada"])


def test_rafaga_de_una_cuenta_nueva_va_a_revision() -> None:
    v = _vacante(cuenta_nueva=True, creadas=RAFAGA_MINIMA)
    assert _decidir(v) == (EstadoDeModeracion.EN_REVISION, ["rafaga"])


def test_varias_vacantes_de_una_cuenta_vieja_no_son_rafaga() -> None:
    assert _decidir(_vacante(cuenta_nueva=False, creadas=10))[0] is EstadoDeModeracion.PUBLICADA


def test_por_debajo_del_umbral_no_es_rafaga() -> None:
    v = _vacante(cuenta_nueva=True, creadas=RAFAGA_MINIMA - 1)
    assert _decidir(v)[0] is EstadoDeModeracion.PUBLICADA


def test_las_marcas_de_un_revisor_externo_suman_sin_cambiar_la_decision() -> None:
    """El punto de extensión del PR 3: el modelo devuelve marcas como las reglas."""
    v = _vacante()
    del_modelo = Marca("ia", "El modelo vio una oferta engañosa.", Gravedad.MEDIA, cita="x")
    d = decidir(v, evaluar(v, [del_modelo]))
    assert (d.estado, [m.regla for m in d.motivos]) == (EstadoDeModeracion.EN_REVISION, ["ia"])


def test_los_motivos_informativos_dicen_por_que_va_a_revision() -> None:
    assert MOTIVO_RECLUTADOR.gravedad is Gravedad.BAJA
    assert MOTIVO_PRIMERA_VACANTE.gravedad is Gravedad.BAJA


def test_la_marca_va_y_vuelve_del_json() -> None:
    marca = Marca("pago", "Cobra", Gravedad.ALTA, cita="«debes pagar»", corregir="Quita el cobro")
    assert marca.a_json() == {
        "regla": "pago",
        "cita": "«debes pagar»",
        "senal": "Cobra",
        "gravedad": "alta",
        "corregir": "Quita el cobro",
    }
    assert Marca.de_json(marca.a_json()) == marca


# ─────────────────────────────── insignia ───────────────────────────────


@pytest.mark.parametrize(
    ("host", "esperado"),
    [
        ("empresa.com", "empresa.com"),
        ("www.empresa.com", "empresa.com"),
        ("rh.empresa.com.mx", "empresa.com.mx"),
        ("empresa.com.ve", "empresa.com.ve"),
        ("empresa.co", "empresa.co"),
        ("tienda.empresa.com.co", "empresa.com.co"),
        ("acme.com.au", "acme.com.au"),  # com.au no está en la lista, pero es sufijo
        ("com.mx", None),
        ("localhost", None),
        ("192.168.0.1", None),
        ("empresa..com", None),
        ("EMPRESA.COM.", "empresa.com"),
        ("café.mx", "xn--caf-dma.mx"),
    ],
)
def test_dominio_registrable(host: str, esperado: str | None) -> None:
    assert dominio_registrable(host) == esperado


@pytest.mark.parametrize(
    ("correo", "web", "publica_para", "esperado"),
    [
        ("rh@empresa.com.mx", "https://www.empresa.com.mx", "propia", True),
        ("rh@mx.empresa.com", "https://empresa.com/empleos", "propia", True),
        ("Ana@Empresa.com", "empresa.com", "propia", True),
        ("rh@empresa.com.mx", "https://otra.com.mx", "propia", False),
        ("rh@empresa.com", "https://empresa.com.mx", "propia", False),
        ("dueno@gmail.com", "https://gmail.com", "propia", False),
        ("rh@yahoo.com.mx", "https://yahoo.com.mx", "propia", False),
        ("rh@prodigy.net.mx", "https://prodigy.net.mx", "propia", False),
        ("rh@empresa.com.mx", None, "propia", False),
        ("rh@empresa.com.mx", "https://empresa.com.mx", "clientes", False),
        ("sin-arroba", "https://empresa.com", "propia", False),
        ("rh@acme.com.au", "https://otra.com.au", "propia", False),
    ],
)
def test_insignia_por_dominio(
    correo: str, web: str | None, publica_para: str, esperado: bool
) -> None:
    assert insignia_por_dominio(correo, web, publica_para) is esperado
