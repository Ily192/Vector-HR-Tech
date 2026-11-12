"""Casos de uso de la moderación (ADR-022): barrido, resumen a hola@, revisión e insignia."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.moderar_vacantes import (
    AvisarColaDeRevision,
    ModerarVacantesPendientes,
    MotivoVacioError,
    ResolverRevision,
    armar_resumen,
)
from app.application.verificar_empresa import ConfirmarAltasDeLaWeb, VerificarEmpresa
from app.domain.moderacion import (
    AltaConfirmada,
    AvisosRecientes,
    Decision,
    EstadoDeModeracion,
    Gravedad,
    Marca,
    VacanteAModerar,
    VacanteEnCola,
)
from app.security import enlaces_de_revision

AHORA = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)


def _vacante(descripcion: str = "Controlarás el inventario.", **kw: object) -> VacanteAModerar:
    datos: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": uuid4(),
        "titulo": "Analista",
        "descripcion": descripcion,
        "empresa_verificada": True,
        "publica_para": "propia",
        "tiene_publicadas": True,
        "duplicada": False,
        "creadas_en_la_ultima_hora": 1,
        "cuenta_nueva": False,
    }
    datos.update(kw)
    return VacanteAModerar(**datos)  # type: ignore[arg-type]


def _en_cola(estado: EstadoDeModeracion = EstadoDeModeracion.EN_REVISION) -> VacanteEnCola:
    return VacanteEnCola(
        id=uuid4(),
        titulo="Promotor",
        descripcion="Escríbenos por WhatsApp",
        empresa="Andes",
        empresa_verificada=False,
        publica_para="propia",
        estado=estado,
        motivos=(Marca("contacto_externo", "Manda a WhatsApp", Gravedad.MEDIA, cita="WhatsApp"),),
    )


class RepoFalso:
    def __init__(self) -> None:
        self.pendientes_: list[VacanteAModerar] = []
        self.guardadas: dict[UUID, Decision] = {}
        self.ya_no_pendientes: set[UUID] = set()
        self.cola: list[VacanteEnCola] = []
        self.avisadas: list[UUID] = []
        self.avisos = AvisosRecientes(ultimo=None, ultimas_24_horas=0)
        self.registrados: list[tuple[bool, int]] = []
        self.estados: dict[UUID, EstadoDeModeracion] = {}
        self.motivos: dict[UUID, Marca | None] = {}
        self.verificaciones: list[dict[str, object]] = []
        self.ya_verificada = False

    async def pendientes(self, lote: int) -> list[VacanteAModerar]:
        return self.pendientes_[:lote]

    async def guardar(self, vacante_id: UUID, decision: Decision) -> bool:
        if vacante_id in self.ya_no_pendientes:
            return False
        self.guardadas[vacante_id] = decision
        return True

    async def cola_sin_avisar(self, limite: int) -> list[VacanteEnCola]:
        return self.cola[:limite]

    async def vacante_en_cola(self, vacante_id: UUID) -> VacanteEnCola | None:
        return next((v for v in self.cola if v.id == vacante_id), None)

    async def marcar_avisadas(self, ids: Sequence[UUID]) -> None:
        self.avisadas.extend(ids)

    async def avisos_recientes(self) -> AvisosRecientes:
        return self.avisos

    async def registrar_aviso(self, *, urgente: bool, vacantes: int) -> None:
        self.registrados.append((urgente, vacantes))

    async def resolver(
        self,
        vacante_id: UUID,
        estado: EstadoDeModeracion,
        motivo: Marca | None,
        desde: Sequence[EstadoDeModeracion],
    ) -> bool:
        if self.estados.get(vacante_id) not in desde:
            return False
        self.estados[vacante_id] = estado
        self.motivos[vacante_id] = motivo
        return True

    async def guardar_verificacion(
        self,
        empresa_id: UUID,
        *,
        publica_para: str,
        web: str | None,
        linkedin: str | None,
        verificada: bool,
    ) -> bool:
        self.verificaciones.append(
            {
                "publica_para": publica_para,
                "web": web,
                "linkedin": linkedin,
                "verificada": verificada,
            }
        )
        return publica_para == "propia" and (verificada or self.ya_verificada)


class CorreoFalso:
    def __init__(self) -> None:
        self.enviados: list[tuple[str, str, str]] = []

    async def enviar(self, *, para: str, asunto: str, texto: str) -> None:
        self.enviados.append((para, asunto, texto))


# ─────────────────────────────── el barrido ───────────────────────────────


async def test_el_barrido_decide_y_cuenta_cada_vacante() -> None:
    repo = RepoFalso()
    limpia = _vacante()
    con_whatsapp = _vacante("Informes por WhatsApp.")
    con_cobro = _vacante("Debes pagar el kit.")
    repo.pendientes_ = [limpia, con_whatsapp, con_cobro]

    resultado = await ModerarVacantesPendientes(repo).ejecutar(lote=10)

    assert (resultado.publicadas, resultado.en_revision, resultado.rechazadas) == (1, 1, 1)
    assert repo.guardadas[limpia.id].estado is EstadoDeModeracion.PUBLICADA
    assert repo.guardadas[con_whatsapp.id].estado is EstadoDeModeracion.EN_REVISION
    assert repo.guardadas[con_cobro.id].estado is EstadoDeModeracion.RECHAZADA


async def test_si_la_editaron_entre_leer_y_guardar_no_cuenta() -> None:
    repo = RepoFalso()
    v = _vacante()
    repo.pendientes_ = [v]
    repo.ya_no_pendientes = {v.id}
    resultado = await ModerarVacantesPendientes(repo).ejecutar(lote=10)
    assert (resultado.publicadas, resultado.descartadas) == (0, 1)


class RevisorQueMarca:
    async def revisar(self, vacante: VacanteAModerar) -> Sequence[Marca]:
        return [Marca("ia", "Parece engañosa", Gravedad.MEDIA)]


class RevisorCaido:
    async def revisar(self, vacante: VacanteAModerar) -> Sequence[Marca]:
        raise TimeoutError("sin respuesta")


async def test_las_marcas_del_revisor_externo_cuentan() -> None:
    repo = RepoFalso()
    v = _vacante()
    repo.pendientes_ = [v]
    await ModerarVacantesPendientes(repo, RevisorQueMarca()).ejecutar(lote=10)
    assert repo.guardadas[v.id].estado is EstadoDeModeracion.EN_REVISION
    assert [m.regla for m in repo.guardadas[v.id].motivos] == ["ia"]


async def test_si_el_revisor_falla_la_vacante_espera_al_siguiente_barrido() -> None:
    repo = RepoFalso()
    repo.pendientes_ = [_vacante()]
    resultado = await ModerarVacantesPendientes(repo, RevisorCaido()).ejecutar(lote=10)
    assert resultado.en_espera == 1
    assert repo.guardadas == {}


# ─────────────────────────────── el resumen ───────────────────────────────


def _avisar(repo: RepoFalso, correo: CorreoFalso, **kw: object) -> AvisarColaDeRevision:
    opciones: dict[str, object] = {
        "destino": "hola@vectorhrtech.com",
        "enlace": lambda vid: f"https://api.test/moderacion/revisar?t={vid}",
        "horas_entre_resumenes": 6,
        "max_en_24_horas": 6,
        "ahora": lambda: AHORA,
    }
    opciones.update(kw)
    return AvisarColaDeRevision(repo, correo, **opciones)  # type: ignore[arg-type]


async def test_sin_cola_no_se_manda_nada() -> None:
    repo, correo = RepoFalso(), CorreoFalso()
    assert await _avisar(repo, correo).ejecutar() == 0
    assert correo.enviados == []


async def test_el_primer_resumen_sale_y_marca_las_vacantes() -> None:
    repo, correo = RepoFalso(), CorreoFalso()
    repo.cola = [_en_cola(), _en_cola()]
    assert await _avisar(repo, correo).ejecutar() == 2
    ((para, asunto, texto),) = correo.enviados
    assert para == "hola@vectorhrtech.com"
    assert asunto == "2 vacantes esperan revisión"
    assert f"https://api.test/moderacion/revisar?t={repo.cola[0].id}" in texto
    assert repo.avisadas == [v.id for v in repo.cola]
    assert repo.registrados == [(False, 2)]


async def test_no_se_repite_antes_de_las_horas_entre_resumenes() -> None:
    repo, correo = RepoFalso(), CorreoFalso()
    repo.cola = [_en_cola()]
    repo.avisos = AvisosRecientes(ultimo=AHORA - timedelta(hours=5), ultimas_24_horas=1)
    assert await _avisar(repo, correo).ejecutar() == 0
    repo.avisos = AvisosRecientes(ultimo=AHORA - timedelta(hours=6), ultimas_24_horas=1)
    assert await _avisar(repo, correo).ejecutar() == 1


async def test_una_oculta_por_reportes_se_avisa_antes() -> None:
    repo, correo = RepoFalso(), CorreoFalso()
    repo.cola = [_en_cola(EstadoDeModeracion.OCULTA)]
    repo.avisos = AvisosRecientes(ultimo=AHORA - timedelta(minutes=20), ultimas_24_horas=1)
    assert await _avisar(repo, correo).ejecutar() == 1
    assert correo.enviados[0][1].startswith("[Urgente]")
    assert repo.registrados == [(True, 1)]


async def test_ni_urgente_antes_de_15_minutos() -> None:
    repo, correo = RepoFalso(), CorreoFalso()
    repo.cola = [_en_cola(EstadoDeModeracion.OCULTA)]
    repo.avisos = AvisosRecientes(ultimo=AHORA - timedelta(minutes=10), ultimas_24_horas=1)
    assert await _avisar(repo, correo).ejecutar() == 0


async def test_el_tope_diario_cuida_la_cuota_de_resend() -> None:
    repo, correo = RepoFalso(), CorreoFalso()
    repo.cola = [_en_cola(EstadoDeModeracion.OCULTA)]
    repo.avisos = AvisosRecientes(ultimo=AHORA - timedelta(hours=7), ultimas_24_horas=6)
    assert await _avisar(repo, correo).ejecutar() == 0
    assert correo.enviados == []


def test_el_resumen_trae_motivos_citas_y_quien_publica() -> None:
    v = _en_cola()
    texto = armar_resumen([v], lambda vid: f"https://x/{vid}")
    assert "Promotor · Andes (empresa sin verificar)" in texto
    assert "Manda a WhatsApp — «WhatsApp»" in texto
    assert f"Revisar: https://x/{v.id}" in texto


# ─────────────────────────────── la revisión ───────────────────────────────


async def test_aprobar_publica_lo_que_espera_revision() -> None:
    repo = RepoFalso()
    vid = uuid4()
    repo.estados[vid] = EstadoDeModeracion.EN_REVISION
    assert await ResolverRevision(repo).aprobar(vid)
    assert repo.estados[vid] is EstadoDeModeracion.PUBLICADA


async def test_rechazar_guarda_el_motivo_para_la_empresa() -> None:
    repo = RepoFalso()
    vid = uuid4()
    repo.estados[vid] = EstadoDeModeracion.OCULTA
    assert await ResolverRevision(repo).rechazar(vid, "  Pide un   depósito  ")
    assert repo.estados[vid] is EstadoDeModeracion.RECHAZADA
    marca = repo.motivos[vid]
    assert marca is not None and marca.corregir == "Pide un depósito"
    assert marca.gravedad is Gravedad.ALTA


async def test_rechazar_sin_motivo_no_hace_nada() -> None:
    repo = RepoFalso()
    vid = uuid4()
    repo.estados[vid] = EstadoDeModeracion.EN_REVISION
    with pytest.raises(MotivoVacioError):
        await ResolverRevision(repo).rechazar(vid, "   ")
    assert repo.estados[vid] is EstadoDeModeracion.EN_REVISION


async def test_no_se_aprueba_lo_que_no_esta_en_revision() -> None:
    repo = RepoFalso()
    vid = uuid4()
    repo.estados[vid] = EstadoDeModeracion.PUBLICADA
    assert not await ResolverRevision(repo).aprobar(vid)


# ─────────────────────────────── la insignia (interfaz del PR 1) ───────────────────────────────


async def test_verificar_da_la_insignia_si_el_dominio_coincide() -> None:
    repo = RepoFalso()
    assert await VerificarEmpresa(repo).ejecutar(
        uuid4(),
        correo="rh@andes.com.mx",
        publica_para="propia",
        web="https://www.andes.com.mx",
        linkedin=None,
    )
    assert repo.verificaciones[-1]["verificada"] is True


async def test_verificar_sin_coincidencia_guarda_los_datos_sin_insignia() -> None:
    repo = RepoFalso()
    quedo = await VerificarEmpresa(repo).ejecutar(
        uuid4(),
        correo="dueno@gmail.com",
        publica_para="propia",
        web="https://andes.mx",
        linkedin="",
    )
    assert quedo is False
    assert repo.verificaciones[-1] == {
        "publica_para": "propia",
        "web": "https://andes.mx",
        "linkedin": None,
        "verificada": False,
    }


async def test_a_mano_se_da_aunque_el_dominio_no_coincida() -> None:
    repo = RepoFalso()
    assert await VerificarEmpresa(repo).ejecutar(
        uuid4(),
        correo="dueno@gmail.com",
        publica_para="propia",
        web=None,
        linkedin=None,
        forzar=True,
    )


async def test_un_reclutador_nunca_lleva_la_insignia_ni_a_mano() -> None:
    repo = RepoFalso()
    quedo = await VerificarEmpresa(repo).ejecutar(
        uuid4(),
        correo="ana@reclutaconana.com",
        publica_para="clientes",
        web="https://reclutaconana.com",
        linkedin="https://www.linkedin.com/in/ana",
        forzar=True,
    )
    assert quedo is False
    assert repo.verificaciones[-1]["verificada"] is False


async def test_publica_para_invalido() -> None:
    with pytest.raises(ValueError, match="publica_para"):
        await VerificarEmpresa(RepoFalso()).ejecutar(
            uuid4(), correo="a@b.com", publica_para="agencia", web=None, linkedin=None
        )


# ─────────────────────────────── el enlace firmado ───────────────────────────────

SECRETO = "s" * 64


def test_el_enlace_firmado_vuelve_a_su_vacante() -> None:
    vid = uuid4()
    token = enlaces_de_revision.firmar(SECRETO, vid, ahora=1_000)
    assert enlaces_de_revision.verificar(SECRETO, token, ahora=1_000) == vid


def test_el_enlace_vence_a_la_semana() -> None:
    token = enlaces_de_revision.firmar(SECRETO, uuid4(), ahora=1_000)
    vigencia = enlaces_de_revision.VIGENCIA_S
    assert enlaces_de_revision.verificar(SECRETO, token, ahora=1_000 + vigencia) is not None
    assert enlaces_de_revision.verificar(SECRETO, token, ahora=1_001 + vigencia) is None


@pytest.mark.parametrize(
    "estropear",
    [
        lambda t: t[:-1] + ("0" if t[-1] != "0" else "1"),  # firma alterada
        lambda t: f"{uuid4()}.{t.split('.', 1)[1]}",  # otra vacante con la misma firma
        lambda t: t.replace(
            t.split(".")[1], str(int(t.split(".")[1]) + 999_999)
        ),  # alarga la vigencia
        lambda t: "basura",
        lambda t: "",
        lambda t: "a.b.c",
    ],
)
def test_un_enlace_alterado_no_sirve(estropear) -> None:
    token = enlaces_de_revision.firmar(SECRETO, uuid4(), ahora=1_000)
    assert enlaces_de_revision.verificar(SECRETO, estropear(token), ahora=1_000) is None


def test_otro_secreto_no_valida() -> None:
    token = enlaces_de_revision.firmar(SECRETO, uuid4(), ahora=1_000)
    assert enlaces_de_revision.verificar("otro" * 16, token, ahora=1_000) is None
    assert enlaces_de_revision.verificar("", token, ahora=1_000) is None


def test_sin_secreto_no_se_firma() -> None:
    with pytest.raises(ValueError):
        enlaces_de_revision.firmar("", uuid4())


# ─────────────────────────────── la conexión con el alta (PR 1) ───────────────────────────────


class ConfirmacionesFalsas:
    def __init__(self, altas: list[AltaConfirmada]) -> None:
        self.altas = altas
        self.marcadas: list[int] = []

    async def confirmadas_sin_marcar(self, limite: int) -> list[AltaConfirmada]:
        return [a for a in self.altas if a.alta_id not in self.marcadas][:limite]

    async def marcar_confirmada(self, alta_id: int, confirmado_en: datetime) -> None:
        self.marcadas.append(alta_id)


def _alta(alta_id: int, correo: str, web: str | None, **kw: object) -> AltaConfirmada:
    datos: dict[str, object] = {
        "alta_id": alta_id,
        "empresa_id": uuid4(),
        "correo": correo,
        "publica_para": "propia",
        "web": web,
        "linkedin": None,
        "confirmado_en": AHORA,
    }
    datos.update(kw)
    return AltaConfirmada(**datos)  # type: ignore[arg-type]


async def test_confirmar_da_la_insignia_y_marca_cada_alta() -> None:
    repo = RepoFalso()
    confirmaciones = ConfirmacionesFalsas(
        [
            _alta(1, "rh@andes.com.mx", "https://andes.com.mx"),
            _alta(2, "dueno@gmail.com", "https://andes.com.mx"),
        ]
    )
    caso = ConfirmarAltasDeLaWeb(confirmaciones, VerificarEmpresa(repo))
    assert await caso.ejecutar() == 2
    assert [v["verificada"] for v in repo.verificaciones] == [True, False]
    assert confirmaciones.marcadas == [1, 2]
    # Lo ya marcado no se repite.
    assert await caso.ejecutar() == 0


class VerificacionQueFalla(RepoFalso):
    async def guardar_verificacion(self, empresa_id: UUID, **kw: object) -> bool:  # type: ignore[override]
        raise ConnectionError("la base se cayó")


async def test_si_la_insignia_falla_no_se_marca_y_se_reintenta() -> None:
    confirmaciones = ConfirmacionesFalsas([_alta(7, "rh@andes.com.mx", None)])
    caso = ConfirmarAltasDeLaWeb(confirmaciones, VerificarEmpresa(VerificacionQueFalla()))
    with pytest.raises(ConnectionError):
        await caso.ejecutar()
    assert confirmaciones.marcadas == []
