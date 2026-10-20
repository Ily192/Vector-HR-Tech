"""Los casos de uso del alta de empresas, con adaptadores falsos."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.dar_de_alta_empresa import DarDeAltaEmpresa, ReenviarInvitacion
from app.domain.alta import SolicitudDeAlta, hash_del_token
from app.domain.puertos import CuentaYaExisteError, EstadoDeCuenta, InvitacionNoEnviadaError

SOLICITUD = SolicitudDeAlta.nueva(
    empresa="Ferretería Norte", correo="ana@ferreterianorte.mx", nombre="Ana Ruiz", tamano=35
)


class RepositorioEnMemoria:
    def __init__(
        self, estado: EstadoDeCuenta = "sin-cuenta", ocupados: tuple[str, ...] = ()
    ) -> None:
        self.estado: EstadoDeCuenta = estado
        self.ocupados = set(ocupados)
        self.empresas: dict[UUID, tuple[str, str]] = {}

    async def estado_de_la_cuenta(self, correo: str) -> EstadoDeCuenta:
        return self.estado

    async def crear_empresa_con_invitacion(
        self, solicitud: SolicitudDeAlta, slug: str, token_hash: str
    ) -> UUID | None:
        if slug in self.ocupados:
            return None
        self.ocupados.add(slug)
        empresa_id = uuid4()
        self.empresas[empresa_id] = (slug, token_hash)
        return empresa_id

    async def deshacer(self, empresa_id: UUID) -> None:
        del self.empresas[empresa_id]


class InvitacionesEnMemoria:
    def __init__(self, falla: Exception | None = None) -> None:
        self.falla = falla
        self.enviadas: list[tuple[str, str, str]] = []
        self.reenviadas: list[str] = []

    async def invitar(self, correo: str, token: str, nombre: str) -> None:
        if self.falla:
            raise self.falla
        self.enviadas.append((correo, token, nombre))

    async def reenviar(self, correo: str) -> None:
        self.reenviadas.append(correo)


async def test_crea_la_empresa_y_manda_el_token_cuyo_hash_guardo() -> None:
    repositorio, invitaciones = RepositorioEnMemoria(), InvitacionesEnMemoria()
    alta = await DarDeAltaEmpresa(repositorio, invitaciones).ejecutar(SOLICITUD)

    assert alta.slug == "ferreteria-norte"
    slug, token_hash = repositorio.empresas[alta.empresa_id]
    ((correo, token, nombre),) = invitaciones.enviadas
    assert (slug, correo, nombre) == ("ferreteria-norte", "ana@ferreterianorte.mx", "Ana Ruiz")
    assert token_hash == hash_del_token(token)


async def test_si_el_slug_es_de_otra_empresa_le_pone_sufijo() -> None:
    repositorio = RepositorioEnMemoria(ocupados=("ferreteria-norte",))
    alta = await DarDeAltaEmpresa(
        repositorio, InvitacionesEnMemoria(), sufijo=lambda: "3f9a"
    ).ejecutar(SOLICITUD)
    assert alta.slug == "ferreteria-norte-3f9a"


async def test_sin_slug_libre_no_crea_ni_invita() -> None:
    repositorio = RepositorioEnMemoria(ocupados=("ferreteria-norte", "ferreteria-norte-3f9a"))
    invitaciones = InvitacionesEnMemoria()
    with pytest.raises(RuntimeError, match="slug libre"):
        await DarDeAltaEmpresa(repositorio, invitaciones, sufijo=lambda: "3f9a").ejecutar(SOLICITUD)
    assert (repositorio.empresas, invitaciones.enviadas) == ({}, [])


@pytest.mark.parametrize(
    ("estado", "mensaje"), [("pendiente", "reenvíala"), ("confirmada", "ya tiene cuenta")]
)
async def test_un_correo_con_cuenta_no_se_da_de_alta_otra_vez(
    estado: EstadoDeCuenta, mensaje: str
) -> None:
    repositorio, invitaciones = RepositorioEnMemoria(estado), InvitacionesEnMemoria()
    with pytest.raises(CuentaYaExisteError, match=mensaje):
        await DarDeAltaEmpresa(repositorio, invitaciones).ejecutar(SOLICITUD)
    assert (repositorio.empresas, invitaciones.enviadas) == ({}, [])


async def test_si_el_correo_no_sale_deshace_la_empresa() -> None:
    repositorio = RepositorioEnMemoria()
    invitaciones = InvitacionesEnMemoria(falla=InvitacionNoEnviadaError("Auth respondió 500"))
    with pytest.raises(InvitacionNoEnviadaError):
        await DarDeAltaEmpresa(repositorio, invitaciones).ejecutar(SOLICITUD)
    # Se puede repetir el alta tal cual: el slug quedó libre otra vez en la base.
    assert repositorio.empresas == {}


async def test_reenviar_solo_a_quien_tiene_invitacion_sin_aceptar() -> None:
    invitaciones = InvitacionesEnMemoria()
    await ReenviarInvitacion(RepositorioEnMemoria("pendiente"), invitaciones).ejecutar(
        " Ana@FerreteriaNorte.mx "
    )
    assert invitaciones.reenviadas == ["ana@ferreterianorte.mx"]

    with pytest.raises(LookupError, match="no tiene invitación"):
        await ReenviarInvitacion(RepositorioEnMemoria("sin-cuenta"), invitaciones).ejecutar(
            "ana@ferreterianorte.mx"
        )
    with pytest.raises(CuentaYaExisteError, match="ya entró"):
        await ReenviarInvitacion(RepositorioEnMemoria("confirmada"), invitaciones).ejecutar(
            "ana@ferreterianorte.mx"
        )
    assert invitaciones.reenviadas == ["ana@ferreterianorte.mx"]
