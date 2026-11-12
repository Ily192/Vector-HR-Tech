"""La insignia "Empresa verificada" y cómo publica la empresa (ADR-022).

**Interfaz para el alta con código (PR 1).** Cuando la persona dueña confirma el
código de 6 dígitos, el alta llama:

    await VerificarEmpresa(SqlRepositorioDeModeracion(db)).ejecutar(
        empresa_id,
        correo=correo_confirmado,
        publica_para=alta.publica_para,   # 'propia' | 'clientes', de altas_web
        web=alta.web_empresa,             # https o None
        linkedin=alta.linkedin,           # https o None
    )

y en la misma transacción hace `commit`. Guarda `publica_para`, `web` y `linkedin`
en `empresas` y da la insignia si `insignia_por_dominio()` lo permite. Llamarla dos
veces deja lo mismo. Antes de confirmar el código no se llama: el dominio del correo
no prueba nada hasta que la persona demuestra que lo lee.

Vector HR también la da a mano (revisó LinkedIn y la web): `forzar=True`, desde la
CLI `python -m app.cli.moderacion verificar --correo … --forzar`.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.moderacion import (
    RepositorioDeConfirmaciones,
    RepositorioDeModeracion,
    insignia_por_dominio,
)

PUBLICA_PARA = frozenset({"propia", "clientes"})


class VerificarEmpresa:
    def __init__(self, repositorio: RepositorioDeModeracion) -> None:
        self._repositorio = repositorio

    async def ejecutar(
        self,
        empresa_id: UUID,
        *,
        correo: str,
        publica_para: str,
        web: str | None,
        linkedin: str | None,
        forzar: bool = False,
    ) -> bool:
        """Devuelve si la empresa quedó con la insignia."""
        if publica_para not in PUBLICA_PARA:
            raise ValueError(f"publica_para inválido: {publica_para!r}")
        # Un reclutador independiente nunca lleva la insignia, ni a mano.
        verificada = publica_para == "propia" and (
            forzar or insignia_por_dominio(correo, web, publica_para)
        )
        # Suma la insignia, nunca la quita: una dada a mano sobrevive a otra llamada.
        quedo = await self._repositorio.guardar_verificacion(
            empresa_id,
            publica_para=publica_para,
            web=web or None,
            linkedin=linkedin or None,
            verificada=verificada,
        )
        return quedo


#: Altas por barrido. El barrido corre cada minuto, con la moderación.
LOTE_DE_CONFIRMACIONES = 100


class ConfirmarAltasDeLaWeb:
    """Da la insignia a las empresas cuyo dueño ya confirmó el código, y las marca.

    Es la conexión con el alta desde la web (enmienda de ADR-017): Auth pone
    `email_confirmed_at` cuando la persona escribe el código, y este caso de uso lo
    traduce en dos cosas, en este orden:

    1. `VerificarEmpresa` con lo que la empresa dio al registrarse (`altas_web`): cómo
       publica, su web y su LinkedIn, y la insignia si el dominio del correo coincide.
    2. `confirmado_en` en `altas_web`, la misma marca que lee la limpieza de 7 días.

    Si el proceso muere entre 1 y 2, el siguiente barrido repite 1, que no cambia
    nada la segunda vez (la insignia solo se suma).

    Corre antes de cada barrido de la moderación (`moderacion.barrer`): la primera
    vacante de una empresa que acaba de confirmar ya se modera con su insignia.
    """

    def __init__(
        self,
        confirmaciones: RepositorioDeConfirmaciones,
        verificar: VerificarEmpresa,
    ) -> None:
        self._confirmaciones = confirmaciones
        self._verificar = verificar

    async def ejecutar(self, *, lote: int = LOTE_DE_CONFIRMACIONES) -> int:
        """Devuelve cuántas altas marcó."""
        altas = await self._confirmaciones.confirmadas_sin_marcar(lote)
        for alta in altas:
            await self._verificar.ejecutar(
                alta.empresa_id,
                correo=alta.correo,
                publica_para=alta.publica_para,
                web=alta.web,
                linkedin=alta.linkedin,
            )
            await self._confirmaciones.marcar_confirmada(alta.alta_id, alta.confirmado_en)
        return len(altas)
