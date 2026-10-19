"""Adaptadores de la coincidencia de skills del plan gratis (ADR-019).

Storage de Supabase, el texto de un PDF o un DOCX, y el SQL. Traducen y nada más:
qué es legible, qué se compara y cuándo se reintenta son del dominio y del caso
de uso. Ninguno llama a un LLM.
"""

from __future__ import annotations

import io
import json
import zipfile
from urllib.parse import quote
from xml.etree import ElementTree

import httpx
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as DefusedElementTree
from pypdf import PasswordType, PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entidades import CvPendiente
from app.domain.puertos import AlmacenNoDisponibleError, CvInaccesibleError
from app.monitoring import logger
from app.repositories import coincidencias as coincidencias_repo

BUCKET = "cvs"
#: El `file_size_limit` del bucket (migración 0005).
MAX_BYTES_DEL_CV = 10 * 1024 * 1024
#: Un CV no pasa de aquí, y así se acota la CPU de un PDF largo.
MAX_PAGINAS = 10
#: pypdf: "Extracting the text of a page requires parsing its whole content
#: stream". Una página con más contenido que esto no se lee.
MAX_BYTES_POR_PAGINA = 5 * 1024 * 1024
#: Tope del XML de un DOCX al descomprimirlo.
MAX_BYTES_DEL_XML_DOCX = 5 * 1024 * 1024

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class SqlRepositorioDeCoincidencias:
    """`RepositorioDeCoincidencias` sobre la sesión del worker (rol dueño).

    Confirma cada escritura: la marca de ilegible tiene que sobrevivir aunque el
    proceso muera leyendo un PDF.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def pendientes(self, limite: int) -> list[CvPendiente]:
        return [
            CvPendiente(
                application_id=f.application_id,
                empresa_id=f.empresa_id,
                ruta=f.ruta,
                skills=tuple(f.skills),
            )
            for f in await coincidencias_repo.pendientes(self._db, limite)
        ]

    async def guardar(self, cv: CvPendiente, encontradas: tuple[str, ...]) -> bool:
        guardada = await coincidencias_repo.guardar(
            self._db,
            application_id=cv.application_id,
            skills=list(cv.skills),
            encontradas=list(encontradas),
        )
        await self._db.commit()
        return guardada

    async def marcar_ilegible(self, cv: CvPendiente) -> None:
        await coincidencias_repo.marcar_ilegible(
            self._db, application_id=cv.application_id, empresa_id=cv.empresa_id
        )
        await self._db.commit()

    async def desmarcar_ilegible(self, cv: CvPendiente) -> None:
        await coincidencias_repo.desmarcar_ilegible(self._db, application_id=cv.application_id)
        await self._db.commit()


class AlmacenSupabase:
    """`AlmacenDeCvs` sobre la API de Storage con la clave secreta. Solo de servidor.

    Supabase: "Send publishable and secret keys on the `apikey` header, not on
    `Authorization: Bearer`", y una clave secreta no funciona desde un navegador.
    La `service_role` legada es un JWT y Storage la pide también como Bearer.
    """

    def __init__(self, url: str, clave: str, http: httpx.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._clave = clave
        self._http = http

    def _cabeceras(self) -> dict[str, str]:
        cabeceras = {"apikey": self._clave}
        if self._clave.startswith("eyJ"):
            cabeceras["Authorization"] = f"Bearer {self._clave}"
        return cabeceras

    async def descargar(self, ruta: str) -> bytes:
        url = f"{self._url}/storage/v1/object/{BUCKET}/{quote(ruta, safe='/')}"
        try:
            async with self._http.stream("GET", url, headers=self._cabeceras()) as respuesta:
                if respuesta.status_code != 200:
                    await respuesta.aread()
                    if _no_existe(respuesta):
                        raise CvInaccesibleError(f"el CV no está en Storage: {ruta}")
                    raise AlmacenNoDisponibleError(f"Storage respondió {respuesta.status_code}")
                contenido = bytearray()
                async for trozo in respuesta.aiter_bytes():
                    contenido.extend(trozo)
                    if len(contenido) > MAX_BYTES_DEL_CV:
                        raise CvInaccesibleError(f"el CV pasa de {MAX_BYTES_DEL_CV} bytes: {ruta}")
                return bytes(contenido)
        except httpx.HTTPError as exc:
            raise AlmacenNoDisponibleError(f"Storage no responde: {type(exc).__name__}") from exc


def _no_existe(respuesta: httpx.Response) -> bool:
    """404, o el 400 con `"statusCode": "404"` con el que Storage responde a un objeto que falta."""
    if respuesta.status_code == 404:
        return True
    if respuesta.status_code != 400:
        return False
    try:
        cuerpo = respuesta.json()
    except json.JSONDecodeError:
        return False
    return isinstance(cuerpo, dict) and str(cuerpo.get("statusCode")) == "404"


class ExtractorDeTextoDeCv:
    """`ExtractorDeTexto` para PDF (pypdf) y DOCX (su XML). Lo demás, como un .doc, no se lee."""

    def extraer(self, contenido: bytes) -> str | None:
        if contenido.startswith(b"%PDF"):
            return _texto_de_pdf(contenido)
        if contenido.startswith(b"PK\x03\x04"):
            return _texto_de_docx(contenido)
        return None


def _texto_de_pdf(contenido: bytes) -> str | None:
    # pypdf: "We consider it the task of the library user to catch exceptions".
    # Un PDF roto o malicioso es un CV ilegible, no un fallo del barrido.
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted and lector.decrypt("") == PasswordType.NOT_DECRYPTED:
            return None
        partes = []
        for i in range(min(len(lector.pages), MAX_PAGINAS)):
            pagina = lector.pages[i]
            datos = pagina.get_contents()
            if datos is not None and len(datos.get_data()) > MAX_BYTES_POR_PAGINA:
                continue
            partes.append(pagina.extract_text())
        return "\n".join(partes)
    except Exception as exc:
        logger.info("coincidencias.pdf_ilegible", error_type=type(exc).__name__)
        return None


def _texto_de_docx(contenido: bytes) -> str | None:
    # El DOCX lo sube un candidato: es XML no confiable. La documentación de Python
    # recomienda defusedxml "for any server code that parses untrusted XML data". Un
    # document.xml de Word nunca trae DTD, así que también se prohíbe.
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as docx, docx.open("word/document.xml") as f:
            xml = f.read(MAX_BYTES_DEL_XML_DOCX + 1)
        if len(xml) > MAX_BYTES_DEL_XML_DOCX:
            return None
        raiz = DefusedElementTree.fromstring(xml, forbid_dtd=True)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, DefusedXmlException):
        return None
    return "\n".join(
        "".join(t.text or "" for t in parrafo.iter(f"{_W}t")) for parrafo in raiz.iter(f"{_W}p")
    )
