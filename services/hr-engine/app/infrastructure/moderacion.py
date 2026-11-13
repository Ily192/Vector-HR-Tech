"""Adaptadores de la moderación de vacantes (ADR-022, migración 0019).

- `SqlRepositorioDeModeracion`: el puerto sobre el SQL de
  `app/repositories/moderacion.py`, con la sesión del hr-engine (rol dueño).
  Confirma cada escritura.
- `CorreoSmtp`: el resumen de la cola a hola@ por el mismo SMTP de Resend que usa
  Auth, con la biblioteca estándar.
- `RegistroDeIntentosRedis`: cuántas veces falló el revisor con IA con cada vacante,
  en Redis, para mandarla a revisión humana después de unos intentos.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import smtplib
import ssl
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any
from uuid import UUID

import redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.moderacion import (
    DIAS_DE_CUENTA_NUEVA,
    AvisosRecientes,
    Decision,
    EstadoDeModeracion,
    Marca,
    VacanteAModerar,
    VacanteEnCola,
)
from app.repositories import moderacion as moderacion_repo


def _motivos(crudo: Any) -> tuple[Marca, ...]:
    lista = json.loads(crudo) if isinstance(crudo, str) else (crudo or [])
    return tuple(Marca.de_json(m) for m in lista if isinstance(m, dict))


def _en_cola(fila: Any) -> VacanteEnCola:
    return VacanteEnCola(
        id=fila.id,
        titulo=fila.titulo,
        descripcion=fila.descripcion,
        empresa=fila.empresa,
        empresa_verificada=fila.verificada,
        publica_para=fila.publica_para,
        estado=EstadoDeModeracion(fila.moderacion),
        motivos=_motivos(fila.motivos_moderacion),
    )


class SqlRepositorioDeModeracion:
    """`RepositorioDeModeracion` sobre la sesión del hr-engine (rol dueño)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def pendientes(self, lote: int) -> list[VacanteAModerar]:
        filas = await moderacion_repo.pendientes(self._db, lote=lote, dias=DIAS_DE_CUENTA_NUEVA)
        return [
            VacanteAModerar(
                id=f.id,
                empresa_id=f.empresa_id,
                titulo=f.titulo,
                descripcion=f.descripcion,
                empresa_verificada=f.verificada,
                publica_para=f.publica_para,
                tiene_publicadas=f.tiene_publicadas,
                duplicada=bool(f.duplicada),
                creadas_en_la_ultima_hora=int(f.creadas_en_la_ultima_hora),
                cuenta_nueva=f.cuenta_nueva,
            )
            for f in filas
        ]

    async def guardar(self, vacante_id: UUID, decision: Decision) -> bool:
        guardada = await moderacion_repo.guardar(
            self._db,
            vacante_id=vacante_id,
            estado=decision.estado.value,
            motivos=json.dumps([m.a_json() for m in decision.motivos], ensure_ascii=False),
        )
        await self._db.commit()
        return guardada

    async def cola_sin_avisar(self, limite: int) -> list[VacanteEnCola]:
        return [_en_cola(f) for f in await moderacion_repo.cola_sin_avisar(self._db, limite)]

    async def cola_completa(self) -> list[VacanteEnCola]:
        """Para la CLI: todo lo que espera revisión, avisado o no."""
        return [_en_cola(f) for f in await moderacion_repo.cola_completa(self._db)]

    async def vacante_en_cola(self, vacante_id: UUID) -> VacanteEnCola | None:
        fila = await moderacion_repo.una(self._db, vacante_id)
        return _en_cola(fila) if fila else None

    async def marcar_avisadas(self, ids: Sequence[UUID]) -> None:
        await moderacion_repo.marcar_avisadas(self._db, ids)
        await self._db.commit()

    async def avisos_recientes(self) -> AvisosRecientes:
        fila = await moderacion_repo.avisos_recientes(self._db)
        return AvisosRecientes(ultimo=fila.ultimo, ultimas_24_horas=int(fila.ultimas))

    async def registrar_aviso(self, *, urgente: bool, vacantes: int) -> None:
        await moderacion_repo.registrar_aviso(self._db, urgente=urgente, vacantes=vacantes)
        await self._db.commit()

    async def resolver(
        self,
        vacante_id: UUID,
        estado: EstadoDeModeracion,
        motivo: Marca | None,
        desde: Sequence[EstadoDeModeracion],
    ) -> bool:
        resuelta = await moderacion_repo.resolver(
            self._db,
            vacante_id=vacante_id,
            estado=estado.value,
            motivo=json.dumps(motivo.a_json(), ensure_ascii=False) if motivo else None,
            desde=[e.value for e in desde],
        )
        await self._db.commit()
        return resuelta

    async def guardar_verificacion(
        self,
        empresa_id: UUID,
        *,
        publica_para: str,
        web: str | None,
        linkedin: str | None,
        verificada: bool,
    ) -> bool:
        quedo = await moderacion_repo.guardar_verificacion(
            self._db,
            empresa_id=empresa_id,
            publica_para=publica_para,
            web=web,
            linkedin=linkedin,
            verificada=verificada,
        )
        await self._db.commit()
        if quedo is None:
            raise LookupError(f"no existe la empresa {empresa_id}")
        return quedo

    async def empresa_por_correo(self, correo: str) -> UUID | None:
        """Para la CLI: la empresa de la persona con ese correo."""
        return await moderacion_repo.empresa_por_correo(self._db, correo)


class CorreoSmtp:
    """`ServicioDeCorreo` por SMTP (Resend en producción, Mailpit en la prueba local).

    `smtplib` es bloqueante: corre en un hilo para no frenar el event loop.
    """

    def __init__(
        self,
        *,
        host: str,
        puerto: int,
        usuario: str,
        clave: str,
        remitente: str,
        nombre: str,
        starttls: bool,
        timeout_s: float = 20.0,
    ) -> None:
        self._host = host
        self._puerto = puerto
        self._usuario = usuario
        self._clave = clave
        self._remitente = remitente
        self._nombre = nombre
        self._starttls = starttls
        self._timeout = timeout_s

    async def enviar(self, *, para: str, asunto: str, texto: str) -> None:
        await asyncio.to_thread(self._enviar, para, asunto, texto)

    def _enviar(self, para: str, asunto: str, texto: str) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = formataddr((self._nombre, self._remitente))
        mensaje["To"] = para
        mensaje["Subject"] = asunto
        mensaje.set_content(texto)
        with smtplib.SMTP(self._host, self._puerto, timeout=self._timeout) as smtp:
            if self._starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self._usuario:
                smtp.login(self._usuario, self._clave)
            smtp.send_message(mensaje)


class RegistroDeIntentosRedis:
    """Los fallos del revisor por vacante, en Redis, con vencimiento.

    La clave lleva un hash del título y la descripción: si la empresa edita la
    vacante, la cuenta empieza de cero. Redis se usa con un cliente síncrono (como
    el circuit breaker): son operaciones de milisegundos y no se atan a ningún loop.
    """

    def __init__(self, cliente: redis.Redis, *, vence_s: int = 86_400) -> None:
        self._redis = cliente
        self._vence_s = vence_s

    @staticmethod
    def clave(vacante: VacanteAModerar) -> str:
        texto = f"{vacante.titulo}\n{vacante.descripcion}"
        huella = hashlib.sha256(texto.encode()).hexdigest()
        return f"moderacion:ia:intentos:{vacante.id}:{huella[:16]}"

    async def sumar(self, vacante: VacanteAModerar) -> int:
        clave = self.clave(vacante)
        canal = self._redis.pipeline()
        canal.incr(clave)
        canal.expire(clave, self._vence_s)
        total, _ = canal.execute()
        return int(total)

    async def limpiar(self, vacante: VacanteAModerar) -> None:
        self._redis.delete(self.clave(vacante))
