"""El arnés que compara modelos para el verificador de vacantes (app/cli/evals_verificador)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.cli import evals_verificador as ev


def _texto(contenido: dict) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=json.dumps(contenido))


def _respuesta_claude(contenido=None, *, stop="end_turn", model="claude-haiku-5-5"):
    bloques = [SimpleNamespace(type="thinking", thinking="")]
    if contenido is not None:
        bloques.append(_texto(contenido))
    uso = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return SimpleNamespace(content=bloques, stop_reason=stop, usage=uso, model=model)


CASO = ev.Caso("x", "mx", "alto", "cobro", "Título", "Pagar $500 de kit")
HAIKU = ev.PRECIOS["claude-haiku-5-5"]


def test_el_set_tiene_40_casos_balanceados():
    casos = ev.cargar_casos(ev.DIRECTORIO / "casos.yaml")
    assert len(casos) == 40
    assert len({c.id for c in casos}) == 40
    conteo = {r: sum(c.esperado == r for c in casos) for r in ev.RIESGOS}
    assert conteo == {"bajo": 22, "medio": 5, "alto": 13}
    assert all(c.descripcion.strip() and c.titulo for c in casos)


def test_un_set_invalido_junta_los_problemas(tmp_path: Path):
    (tmp_path / "casos.yaml").write_text(
        "casos:\n  - {id: a, esperado: tal vez, titulo: t, descripcion: d}\n"
        "  - {id: a, esperado: bajo, titulo: t}\n",
        encoding="utf-8",
    )
    with pytest.raises(ev.SetInvalidoError) as exc:
        ev.cargar_casos(tmp_path / "casos.yaml")
    assert "esperado" in str(exc.value) and "repetido" in str(exc.value)


def test_las_credenciales_no_pisan_el_entorno(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "del-entorno")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    archivo = tmp_path / "var-local.env"
    archivo.write_text(
        "GITHUB_TOKEN=no-se-toca\nANTHROPIC_API_KEY=del-archivo\nGEMINI_API_KEY='g-123'\n",
        encoding="utf-8",
    )
    ev.cargar_credenciales(archivo)
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "del-entorno"
    assert os.environ["GEMINI_API_KEY"] == "g-123"
    assert ev.clave_de_gemini() == "g-123"
    assert os.environ.get("GITHUB_TOKEN") != "no-se-toca"


def test_lee_la_respuesta_estructurada_de_claude():
    r = ev.leer_respuesta_claude(
        HAIKU,
        CASO,
        _respuesta_claude(
            {
                "riesgo": "alto",
                "motivos": [{"frase": "Pagar $500 de kit", "explicacion": "cobra"}],
                "senales": ["cobro_al_candidato"],
            }
        ),
        0.8,
    )
    assert r.riesgo == "alto" and r.decision == "alto" and r.error is None
    assert r.senales == ["cobro_al_candidato"]
    assert r.costo_usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1_000_000)


def test_una_negativa_va_a_revision_manual():
    r = ev.leer_respuesta_claude(HAIKU, CASO, _respuesta_claude(stop="refusal"), 0.5)
    assert r.rechazo and r.decision == "medio" and r.error is None


def test_una_respuesta_cortada_es_error():
    r = ev.leer_respuesta_claude(HAIKU, CASO, _respuesta_claude(stop="max_tokens"), 0.5)
    assert r.error and r.decision is None


def test_el_fallback_se_cobra_al_precio_del_modelo_que_respondio():
    opus = ev.PRECIOS["claude-opus-5-5"]
    r = ev.leer_respuesta_claude(
        opus,
        CASO,
        _respuesta_claude(
            {"riesgo": "bajo", "motivos": [], "senales": []}, model="claude-haiku-5-5"
        ),
        0.5,
    )
    assert r.servido_por == "claude-haiku-5-5"
    assert r.costo_usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1_000_000)


def test_lee_la_respuesta_de_gemini_con_el_pensamiento_como_salida():
    gemini = ev.PRECIOS["gemini-3.5-flash-lite"]
    respuesta = SimpleNamespace(
        text=json.dumps({"riesgo": "medio", "motivos": [], "senales": ["enlace_acortado"]}),
        usage_metadata=SimpleNamespace(
            prompt_token_count=900, candidates_token_count=100, thoughts_token_count=50
        ),
        candidates=[],
    )
    r = ev.leer_respuesta_gemini(gemini, CASO, respuesta, 0.4)
    assert r.riesgo == "medio"
    assert r.tokens_salida == 150
    assert r.costo_usd == pytest.approx((900 * 0.30 + 150 * 2.50) / 1_000_000)


def _r(caso: str, esperado: str, riesgo: str | None, costo=0.001, **kw) -> ev.Resultado:
    return ev.Resultado(caso, esperado, "m", riesgo=riesgo, costo_usd=costo, latencia_s=1.0, **kw)


def test_las_metricas_cuentan_lo_que_importa():
    rs = [
        _r("a1", "alto", "alto"),
        _r("a2", "alto", "medio"),
        _r("m1", "medio", "bajo"),
        _r("b1", "bajo", "bajo"),
        _r("b2", "bajo", "medio"),
        _r("b3", "bajo", None, rechazo=True),
        _r("b4", "bajo", None, error="API 500"),
    ]
    m = ev.metricas("m", 7, rs)
    assert m.recall_alto == 0.5
    assert m.estafas_como_bajo == 1
    assert m.falsos_positivos == pytest.approx(2 / 3)  # b2 y la negativa de b3
    assert m.errores == 1 and m.rechazos == 1
    assert m.exactitud == pytest.approx(2 / 6)
    assert m.costo_por_vacante == pytest.approx(0.001)


def _m(modelo: str, recall: float, fp: float, costo: float, **kw) -> ev.Metricas:
    base = {
        "modelo": modelo,
        "casos": 40,
        "corridos": 40,
        "errores": 0,
        "rechazos": 0,
        "recall_alto": recall,
        "estafas_como_bajo": 0,
        "falsos_positivos": fp,
        "exactitud": 0.9,
        "costo_total": costo * 40,
        "costo_por_vacante": costo,
        "latencia_media": 1.0,
    }
    base.update(kw)
    return ev.Metricas(**base)


def test_por_defecto_solo_corren_los_gemini():
    elegidos, apagados = ev.elegir_modelos(None, con_claude=False)
    assert [m.id for m in elegidos] == [
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    ]
    assert set(apagados) == {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"}
    assert all("--con-claude" in motivo for motivo in apagados.values())


def test_claude_solo_corre_con_la_bandera():
    pedidos = ["claude-haiku-5-5", "gemini-2.5-flash-lite"]
    sin, apagados = ev.elegir_modelos(pedidos, con_claude=False)
    assert [m.id for m in sin] == ["gemini-2.5-flash-lite"] and "claude-haiku-5-5" in apagados
    con, apagados = ev.elegir_modelos(pedidos, con_claude=True)
    assert [m.id for m in con] == ["claude-haiku-5-5", "gemini-2.5-flash-lite"] and not apagados


def test_recomienda_el_mas_barato_que_cumple():
    elegido, texto = ev.recomendar(
        [
            _m("caro", 1.0, 0.0, 0.02),
            _m("barato", 1.0, 0.05, 0.0005),
            _m("mas-barato-pero-falla", 0.9, 0.0, 0.0001),
            _m("barato-que-deja-pasar", 1.0, 0.0, 0.0002, estafas_como_bajo=1),
        ]
    )
    assert elegido is not None and elegido.modelo == "barato"
    assert "barato" in texto


def test_sin_modelo_apto_lo_dice():
    elegido, texto = ev.recomendar([_m("a", 0.9, 0.0, 0.001), _m("b", 1.0, 0.3, 0.001)])
    assert elegido is None and "Ningún modelo cumplió" in texto


def test_el_informe_lista_lo_que_no_corrio():
    casos = ev.cargar_casos(ev.DIRECTORIO / "casos.yaml")
    md = ev.informe_markdown(
        fecha=datetime(2026, 11, 12, tzinfo=UTC),
        casos=casos,
        instrucciones="x",
        metricas_por_modelo=[],
        resultados=[],
        sin_correr={"claude-haiku-5-5": "falta ANTHROPIC_API_KEY"},
        gastado=0.0,
        tope=2.0,
    )
    assert "Todavía no corrió ningún modelo." in md
    assert "falta ANTHROPIC_API_KEY" in md
    assert "gemini-3.5-flash-lite" in md  # la tabla de estimación


def test_el_esquema_es_estricto():
    assert ev.ESQUEMA["additionalProperties"] is False
    assert ev.ESQUEMA["properties"]["riesgo"]["enum"] == ["bajo", "medio", "alto"]
    assert set(ev.ESQUEMA["required"]) == {"riesgo", "motivos", "senales"}
