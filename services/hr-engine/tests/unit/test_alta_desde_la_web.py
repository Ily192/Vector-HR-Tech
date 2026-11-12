"""Los casos de uso del alta desde la web, con adaptadores falsos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.alta_desde_la_web import DarDeAltaDesdeLaWeb, LimpiarAltasSinConfirmar
from app.domain.alta import hash_del_token
from app.domain.alta_web import SolicitudDeAltaWeb
from app.domain.puertos import (
    AltaPendiente,
    CodigoNoEnviadoError,
    CodigoReenviadoMuyProntoError,
    EstadoDeCuenta,
    LimiteDeAltasError,
    ResultadoDeAltaWeb,
)

from .test_alta_web import datos
from .test_dar_de_alta_empresa import RepositorioEnMemoria

PANEL = "https://panel.vectorhrtech.com"
URL_ESPERADA = f"{PANEL}/verificar#correo=ana%40ferreterianorte.mx"


def solicitud(**cambios: object) -> SolicitudDeAltaWeb:
    return SolicitudDeAltaWeb.nueva(**datos(correo="ana@ferreterianorte.mx", **cambios))  # type: ignore[arg-type]


class AltasWebEnMemoria:
    def __init__(self) -> None:
        self.filas: dict[str, dict[str, object]] = {}
        self.confirmadas = 0
        self.pendientes: list[AltaPendiente] = []
        self.borradas: list[UUID] = []

    async def reservar(self, s: SolicitudDeAltaWeb, ip_hash: str | None) -> bool:
        if s.lead_id in self.filas:
            return False
        self.filas[s.lead_id] = {"ip_hash": ip_hash, "resultado": None, "empresa_id": None}
        return True

    async def completar(
        self, lead_id: str, empresa_id: UUID | None, resultado: ResultadoDeAltaWeb
    ) -> None:
        self.filas[lead_id] |= {"empresa_id": empresa_id, "resultado": resultado}

    async def liberar(self, lead_id: str) -> None:
        if self.filas.get(lead_id, {}).get("resultado") is None:
            self.filas.pop(lead_id, None)

    async def marcar_confirmadas(self) -> int:
        return self.confirmadas

    async def pendientes_desde(self, antes_de: datetime) -> list[AltaPendiente]:
        self.antes_de = antes_de
        return self.pendientes

    async def borrar_empresa(self, empresa_id: UUID) -> None:
        self.borradas.append(empresa_id)


class CodigosEnMemoria:
    def __init__(
        self, falla_alta: Exception | None = None, falla_entrada: Exception | None = None
    ) -> None:
        self.falla_alta, self.falla_entrada = falla_alta, falla_entrada
        self.altas: list[tuple[str, str, str, str | None]] = []
        self.entradas: list[tuple[str, str | None]] = []
        self.usuarios_borrados: list[UUID] = []
        self.falla_al_borrar: set[UUID] = set()

    async def mandar_codigo_de_alta(
        self, correo: str, token: str, nombre: str, ip: str | None
    ) -> None:
        if self.falla_alta:
            raise self.falla_alta
        self.altas.append((correo, token, nombre, ip))

    async def mandar_codigo_de_entrada(self, correo: str, ip: str | None) -> None:
        self.entradas.append((correo, ip))
        if self.falla_entrada:
            raise self.falla_entrada

    async def borrar_usuario(self, usuario_id: UUID) -> None:
        if usuario_id in self.falla_al_borrar:
            raise CodigoNoEnviadoError("Auth no responde")
        self.usuarios_borrados.append(usuario_id)


class LimitadorEnMemoria:
    def __init__(self, corta: bool = False) -> None:
        self.corta = corta
        self.consumidos: list[tuple[str | None, str]] = []

    async def consumir(self, ip_hash: str | None, correo: str) -> None:
        if self.corta:
            raise LimiteDeAltasError(120)
        self.consumidos.append((ip_hash, correo))


def caso(
    estado: EstadoDeCuenta = "sin-cuenta",
    codigos: CodigosEnMemoria | None = None,
    limitador: LimitadorEnMemoria | None = None,
) -> tuple[DarDeAltaDesdeLaWeb, RepositorioEnMemoria, AltasWebEnMemoria, CodigosEnMemoria]:
    repositorio, altas_web = RepositorioEnMemoria(estado=estado), AltasWebEnMemoria()
    codigos = codigos or CodigosEnMemoria()
    uso = DarDeAltaDesdeLaWeb(
        repositorio, altas_web, codigos, limitador or LimitadorEnMemoria(), PANEL
    )
    return uso, repositorio, altas_web, codigos


async def test_sin_cuenta_crea_la_empresa_y_manda_el_codigo_con_el_token_guardado() -> None:
    uso, repositorio, altas_web, codigos = caso()
    respuesta = await uso.ejecutar(solicitud(), "hash-de-la-ip")

    assert (respuesta.estado, respuesta.verificar_url) == ("codigo_enviado", URL_ESPERADA)
    ((empresa_id, (slug, token_hash)),) = repositorio.empresas.items()
    ((correo, token, nombre, ip),) = codigos.altas
    assert (slug, correo, nombre, ip) == (
        "ferreteria-norte",
        "ana@ferreterianorte.mx",
        "Ana Ruiz",
        "203.0.113.7",
    )
    assert token_hash == hash_del_token(token)
    assert altas_web.filas["1024"] == {
        "ip_hash": "hash-de-la-ip",
        "resultado": "empresa_creada",
        "empresa_id": empresa_id,
    }


@pytest.mark.parametrize("estado", ["pendiente", "confirmada"])
async def test_con_cuenta_solo_manda_un_codigo_y_responde_igual(estado: EstadoDeCuenta) -> None:
    uso, repositorio, altas_web, codigos = caso(estado=estado)
    respuesta = await uso.ejecutar(solicitud(), None)

    assert (respuesta.estado, respuesta.verificar_url) == ("codigo_enviado", URL_ESPERADA)
    assert repositorio.empresas == {}
    assert codigos.altas == []
    assert codigos.entradas == [("ana@ferreterianorte.mx", "203.0.113.7")]
    assert altas_web.filas["1024"]["resultado"] == "cuenta_existente"


async def test_un_reintento_de_la_web_no_crea_ni_manda_nada() -> None:
    limitador = LimitadorEnMemoria()
    uso, repositorio, _, codigos = caso(limitador=limitador)
    primera = await uso.ejecutar(solicitud(), None)
    segunda = await uso.ejecutar(solicitud(), None)

    assert primera == segunda
    assert len(repositorio.empresas) == 1
    assert len(codigos.altas) == 1
    assert len(limitador.consumidos) == 1


async def test_un_codigo_de_hace_menos_de_un_minuto_sigue_sirviendo() -> None:
    codigos = CodigosEnMemoria(falla_entrada=CodigoReenviadoMuyProntoError("pronto"))
    uso, _, altas_web, _ = caso(estado="confirmada", codigos=codigos)
    respuesta = await uso.ejecutar(solicitud(), None)
    assert respuesta.verificar_url == URL_ESPERADA
    assert altas_web.filas["1024"]["resultado"] == "cuenta_existente"


async def test_si_el_codigo_no_sale_no_queda_nada_y_la_web_puede_reintentar() -> None:
    codigos = CodigosEnMemoria(falla_alta=CodigoNoEnviadoError("Auth caído"))
    uso, repositorio, altas_web, _ = caso(codigos=codigos)
    with pytest.raises(CodigoNoEnviadoError):
        await uso.ejecutar(solicitud(), None)
    assert repositorio.empresas == {}
    assert altas_web.filas == {}

    codigos.falla_alta = None
    await uso.ejecutar(solicitud(), None)
    assert len(repositorio.empresas) == 1


async def test_pasado_el_tope_no_crea_nada_y_libera_el_lead() -> None:
    uso, repositorio, altas_web, codigos = caso(limitador=LimitadorEnMemoria(corta=True))
    with pytest.raises(LimiteDeAltasError) as error:
        await uso.ejecutar(solicitud(), "hash")
    assert error.value.reintentar_en_s == 120
    assert (repositorio.empresas, altas_web.filas, codigos.altas) == ({}, {}, [])


async def test_la_limpieza_borra_la_cuenta_y_despues_la_empresa() -> None:
    altas_web, codigos = AltasWebEnMemoria(), CodigosEnMemoria()
    sana, rota = AltaPendiente(uuid4(), (uuid4(),)), AltaPendiente(uuid4(), (uuid4(),))
    altas_web.pendientes, altas_web.confirmadas = [sana, rota], 2
    codigos.falla_al_borrar = {rota.usuarios[0]}
    ahora = datetime(2026, 11, 20, 4, 30, tzinfo=UTC)

    resultado = await LimpiarAltasSinConfirmar(altas_web, codigos, ahora=lambda: ahora).ejecutar()

    assert (resultado.confirmadas, resultado.borradas, resultado.con_error) == (2, 1, 1)
    assert altas_web.antes_de == ahora - timedelta(days=7)
    assert codigos.usuarios_borrados == [sana.usuarios[0]]
    # Si Auth no borró la cuenta, la empresa espera al día siguiente.
    assert altas_web.borradas == [sana.empresa_id]
