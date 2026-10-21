"""El caso de uso del aviso de los diagnósticos gratuitos, con adaptadores falsos."""

from __future__ import annotations

from app.application.avisar_diagnosticos import AvisarDiagnosticos, ResultadoDelAviso

from .fakes import CorreoFalso, RepositorioDeDiagnosticosEnMemoria, VerificadorFalso
from .test_diagnostico import PARA, diagnostico


def _caso(
    repo: RepositorioDeDiagnosticosEnMemoria,
    verificador: VerificadorFalso | None,
    correo: CorreoFalso | None,
    max_por_dia: int = 20,
) -> AvisarDiagnosticos:
    return AvisarDiagnosticos(repo, verificador, correo, para=PARA, max_por_dia=max_por_dia)


async def test_un_correo_por_barrido_con_los_que_pasan_turnstile() -> None:
    bueno, otro, bot = (
        diagnostico(turnstile_token="t1"),
        diagnostico(turnstile_token="t2", empresa="Siete Mares"),
        diagnostico(turnstile_token="falso", empresa="Bot S.A."),
    )
    repo = RepositorioDeDiagnosticosEnMemoria([bueno, otro, bot])
    correo = CorreoFalso()

    resultado = await _caso(repo, VerificadorFalso({"t1", "t2"}), correo).ejecutar()

    assert resultado == ResultadoDelAviso(avisados=2, descartados=1)
    assert len(correo.enviados) == 1
    assert "Siete Mares" in correo.enviados[0].cuerpo
    assert "Bot S.A." not in correo.enviados[0].cuerpo
    assert repo.descartados == [bot.id]
    assert repo.verificados == [bueno.id, otro.id]
    assert repo.avisados == [bueno.id, otro.id]
    assert repo.confirmaciones == 1


async def test_sin_token_se_descarta() -> None:
    sin_token = diagnostico(turnstile_token=None)
    repo = RepositorioDeDiagnosticosEnMemoria([sin_token])
    verificador = VerificadorFalso({"t1"})

    resultado = await _caso(repo, verificador, CorreoFalso()).ejecutar()

    assert resultado.descartados == 1
    assert repo.avisados == []


async def test_un_verificado_antes_no_se_vuelve_a_verificar() -> None:
    """Turnstile no acepta un token dos veces: verificarlo otra vez lo descartaría."""
    ya = diagnostico(turnstile_token="t1", verificado=True)
    repo = RepositorioDeDiagnosticosEnMemoria([ya])
    verificador = VerificadorFalso(set())

    resultado = await _caso(repo, verificador, CorreoFalso()).ejecutar()

    assert verificador.tokens == []
    assert resultado.avisados == 1


async def test_sin_secreto_de_turnstile_todos_pasan() -> None:
    d = diagnostico(turnstile_token=None)
    repo = RepositorioDeDiagnosticosEnMemoria([d])

    resultado = await _caso(repo, None, CorreoFalso()).ejecutar()

    assert resultado.avisados == 1
    assert repo.verificados == [d.id]


async def test_si_turnstile_no_responde_espera_sin_descartar() -> None:
    d = diagnostico(turnstile_token="t1")
    repo = RepositorioDeDiagnosticosEnMemoria([d])
    correo = CorreoFalso()

    resultado = await _caso(repo, VerificadorFalso({"t1"}, disponible=False), correo).ejecutar()

    assert resultado == ResultadoDelAviso(en_espera=1)
    assert (repo.descartados, repo.verificados, correo.enviados) == ([], [], [])


async def test_los_que_pasan_del_tope_del_dia_van_en_una_linea_y_quedan_avisados() -> None:
    diagnosticos = [diagnostico(turnstile_token=f"t{i}", empresa=f"Empresa {i}") for i in range(4)]
    repo = RepositorioDeDiagnosticosEnMemoria(diagnosticos, avisados_antes_hoy=18)
    correo = CorreoFalso()

    resultado = await _caso(
        repo, VerificadorFalso({f"t{i}" for i in range(4)}), correo, max_por_dia=20
    ).ejecutar()

    assert resultado == ResultadoDelAviso(avisados=4, sin_detalle=2)
    (enviado,) = correo.enviados
    assert "Empresa 0" in enviado.cuerpo and "Empresa 1" in enviado.cuerpo
    assert "Empresa 2" not in enviado.cuerpo and "Empresa 3" not in enviado.cuerpo
    assert "y 2 diagnósticos más (revísalos en la base)" in enviado.cuerpo
    assert repo.avisados == [d.id for d in diagnosticos]


async def test_con_el_tope_lleno_solo_va_la_linea() -> None:
    repo = RepositorioDeDiagnosticosEnMemoria([diagnostico()], avisados_antes_hoy=25)
    correo = CorreoFalso()

    resultado = await _caso(repo, None, correo, max_por_dia=20).ejecutar()

    assert resultado == ResultadoDelAviso(avisados=1, sin_detalle=1)
    assert "Empresa:" not in correo.enviados[0].cuerpo


async def test_si_el_correo_falla_cada_uno_suma_un_intento() -> None:
    a, b = diagnostico(), diagnostico()
    repo = RepositorioDeDiagnosticosEnMemoria([a, b])

    resultado = await _caso(repo, None, CorreoFalso(disponible=False)).ejecutar()

    assert resultado == ResultadoDelAviso(sin_avisar=2)
    assert repo.intentos == {a.id: 1, b.id: 1}
    assert repo.avisados == []
    # La verificación queda: el token ya no se podría volver a verificar.
    assert repo.verificados == [a.id, b.id]
    assert repo.confirmaciones == 1


async def test_sin_smtp_verifica_y_deja_los_avisos_pendientes() -> None:
    d = diagnostico(turnstile_token="t1")
    repo = RepositorioDeDiagnosticosEnMemoria([d])

    resultado = await _caso(repo, VerificadorFalso({"t1"}), None).ejecutar()

    assert resultado == ResultadoDelAviso(sin_avisar=1)
    assert (repo.verificados, repo.avisados, repo.intentos) == ([d.id], [], {})


async def test_sin_pendientes_no_manda_nada_pero_confirma() -> None:
    repo = RepositorioDeDiagnosticosEnMemoria()
    correo = CorreoFalso()

    assert await _caso(repo, VerificadorFalso(), correo).ejecutar() == ResultadoDelAviso()
    assert correo.enviados == []
    assert repo.confirmaciones == 1


async def test_respeta_el_lote() -> None:
    repo = RepositorioDeDiagnosticosEnMemoria([diagnostico() for _ in range(5)])
    resultado = await _caso(repo, None, CorreoFalso()).ejecutar(lote=3)
    assert resultado.avisados == 3
