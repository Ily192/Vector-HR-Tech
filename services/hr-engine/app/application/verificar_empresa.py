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

from app.domain.moderacion import RepositorioDeModeracion, insignia_por_dominio

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
