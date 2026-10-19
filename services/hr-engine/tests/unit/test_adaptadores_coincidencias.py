"""Adaptadores de la coincidencia de skills: el texto de un PDF o un DOCX, y Storage (ADR-019).

Los PDF y los DOCX se arman aquí mismo; Storage se simula con `httpx.MockTransport`.
"""

from __future__ import annotations

import io
import json
import zipfile

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

from app.domain.puertos import AlmacenNoDisponibleError, CvInaccesibleError
from app.infrastructure import coincidencias as adaptadores
from app.infrastructure.coincidencias import AlmacenSupabase, ExtractorDeTextoDeCv

URL = "https://proyecto.supabase.co"
CLAVE_SECRETA = "sb_secret_de_prueba"


def _pdf(*lineas: str) -> bytes:
    """Un PDF mínimo y válido, con una línea de texto por línea, en Helvetica."""
    texto = " ".join(f"({linea}) Tj 0 -14 Td" for linea in lineas)
    contenido = f"BT /F1 12 Tf 72 720 Td {texto} ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1,
        xref,
    )
    return bytes(salida)


def _cifrado(contenido: bytes, *, clave_de_lectura: str) -> bytes:
    escritor = PdfWriter(clone_from=PdfReader(io.BytesIO(contenido)))
    escritor.encrypt(user_password=clave_de_lectura, owner_password="duena", algorithm="AES-128")
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def _docx(*parrafos: str, document_xml: str | None = None) -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    cuerpo = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in parrafos)
    xml = (
        document_xml
        or f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{cuerpo}</w:body></w:document>'
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as docx:
        docx.writestr("[Content_Types].xml", "<Types/>")
        docx.writestr("word/document.xml", xml)
    return salida.getvalue()


# ───────────────────────────── el texto del CV ─────────────────────────────

extraer = ExtractorDeTextoDeCv().extraer


def test_saca_el_texto_de_un_pdf() -> None:
    texto = extraer(_pdf("Analista de datos", "Python, SQL y Power BI"))
    assert texto is not None
    assert "Analista de datos" in texto
    assert "Python, SQL y Power BI" in texto


def test_un_pdf_con_clave_de_lectura_no_se_lee() -> None:
    assert extraer(_cifrado(_pdf("Python"), clave_de_lectura="secreta")) is None


def test_un_pdf_cifrado_sin_clave_de_lectura_si() -> None:
    """Muchos PDFs solo traen clave de dueño (para no editarlos): se abren con la clave vacía."""
    texto = extraer(_cifrado(_pdf("Python y SQL"), clave_de_lectura=""))
    assert texto is not None and "Python y SQL" in texto


def test_un_pdf_roto_no_se_lee() -> None:
    assert extraer(b"%PDF-1.4\nesto no es un PDF") is None


def test_una_pagina_demasiado_pesada_no_se_lee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adaptadores, "MAX_BYTES_POR_PAGINA", 10)
    assert extraer(_pdf("Python")) == ""


def test_saca_el_texto_de_un_docx_con_un_parrafo_por_linea() -> None:
    assert extraer(_docx("Analista de datos", "Python y SQL")) == "Analista de datos\nPython y SQL"


def test_un_docx_con_dtd_no_se_lee() -> None:
    """Word nunca escribe una DTD en document.xml: si trae una, es un ataque (billion laughs, XXE)."""
    bomba = (
        '<?xml version="1.0"?><!DOCTYPE w [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><w>&b;</w>'
    )
    assert extraer(_docx(document_xml=bomba)) is None


def test_un_docx_sin_documento_no_se_lee() -> None:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as docx:
        docx.writestr("otra/cosa.xml", "<a/>")
    assert extraer(salida.getvalue()) is None


def test_un_docx_demasiado_grande_no_se_lee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adaptadores, "MAX_BYTES_DEL_XML_DOCX", 50)
    assert extraer(_docx("Python " * 50)) is None


@pytest.mark.parametrize(
    "contenido",
    [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 un .doc de Word 97", b"\x89PNG imagen", b""],
    ids=["doc", "imagen", "vacio"],
)
def test_lo_que_no_es_pdf_ni_docx_no_se_lee(contenido: bytes) -> None:
    assert extraer(contenido) is None


# ──────────────────────────────── Storage ────────────────────────────────


async def _descargar(
    responder: httpx.MockTransport, ruta: str = "empresa/cv.pdf", clave: str = CLAVE_SECRETA
) -> bytes:
    async with httpx.AsyncClient(transport=responder) as http:
        return await AlmacenSupabase(URL, clave, http).descargar(ruta)


async def test_baja_el_cv_con_la_clave_secreta_solo_en_apikey() -> None:
    vistas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(200, content=b"%PDF-1.4 ...")

    contenido = await _descargar(httpx.MockTransport(responder), ruta="emp/Ana María.pdf")
    assert contenido == b"%PDF-1.4 ..."
    (pedida,) = vistas
    assert str(pedida.url) == f"{URL}/storage/v1/object/cvs/emp/Ana%20Mar%C3%ADa.pdf"
    assert pedida.headers["apikey"] == CLAVE_SECRETA
    # Supabase: las claves nuevas van en `apikey`, no en `Authorization: Bearer`.
    assert "authorization" not in pedida.headers


async def test_la_service_role_legada_va_tambien_como_bearer() -> None:
    legada = "eyJhbGciOiJIUzI1NiJ9.e30.firma"
    vistas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(200, content=b"%PDF")

    await _descargar(httpx.MockTransport(responder), clave=legada)
    assert vistas[0].headers["authorization"] == f"Bearer {legada}"


@pytest.mark.parametrize(
    ("estado", "cuerpo"),
    [
        (404, {}),
        # Así responde Storage a un objeto que no existe.
        (400, {"statusCode": "404", "error": "not_found", "message": "Object not found"}),
    ],
    ids=["404", "400-not-found"],
)
async def test_un_cv_que_no_existe_es_inaccesible(estado: int, cuerpo: dict[str, str]) -> None:
    transporte = httpx.MockTransport(lambda _r: httpx.Response(estado, json=cuerpo))
    with pytest.raises(CvInaccesibleError):
        await _descargar(transporte)


@pytest.mark.parametrize(
    ("estado", "cuerpo"),
    [
        (400, json.dumps({"statusCode": "400", "error": "invalid_jwt"})),
        (401, "{}"),
        (403, "{}"),
        (503, "no es JSON"),
    ],
    ids=["400-otro", "401", "403", "503"],
)
async def test_los_demas_errores_dejan_el_cv_para_despues(estado: int, cuerpo: str) -> None:
    """Una clave mal puesta no puede volver ilegibles todos los CVs: se reintentan."""
    transporte = httpx.MockTransport(lambda _r: httpx.Response(estado, content=cuerpo.encode()))
    with pytest.raises(AlmacenNoDisponibleError):
        await _descargar(transporte)


async def test_sin_conexion_el_cv_espera() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    with pytest.raises(AlmacenNoDisponibleError):
        await _descargar(httpx.MockTransport(responder))


async def test_un_cv_mas_grande_que_el_bucket_es_inaccesible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adaptadores, "MAX_BYTES_DEL_CV", 5)
    transporte = httpx.MockTransport(lambda _r: httpx.Response(200, content=b"%PDF-1.4 largo"))
    with pytest.raises(CvInaccesibleError):
        await _descargar(transporte)
