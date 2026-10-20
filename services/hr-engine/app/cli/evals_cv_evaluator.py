"""Mide al evaluador de CVs con un set de casos, antes de usarlo con candidatos reales (ADR-021 §9).

    python -m app.cli.evals_cv_evaluator                     # el set sintético del repo
    python -m app.cli.evals_cv_evaluator --dir D:/evals-cv   # el set real
    python -m app.cli.evals_cv_evaluator --sin-sesgo         # solo el acierto

Sin `--dir` usa `EVALS_CV_EVALUATOR_DIR` y, si no está, el set sintético. El
directorio trae un `casos.yaml` (el formato está en
evals/cv-evaluator/sinteticos/casos.yaml) y los CV en PDF, DOCX o texto. El set real
son datos personales: vive fuera del repo, que es público, y el informe se escribe
ahí, en `resultados/`. El informe lleva los ids de los casos, nunca los nombres.

Usa el mismo evaluador que producción (`LlmScoring`), así que necesita GOOGLE_API_KEY
del nivel de pago u OPENAI_API_KEY. No pasa por el presupuesto de la plataforma ni
deja runs. Sale con 0 si el evaluador pasa, 1 si no y 2 si no se pudo medir.

El circuit breaker del LLM guarda su estado en Redis. Sin Redis deja pasar, pero
cada llamada espera su timeout (0,25 s): con el del compose de desarrollo arriba
(`docker compose -f infra/docker/docker-compose.dev.yml up -d redis`) va más rápido.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.application.medir_el_evaluador import MedirElEvaluador
from app.domain.coincidencia import es_legible
from app.domain.entidades import VacanteParaEvaluar
from app.domain.evals import (
    EJES,
    TOLERANCIA_DE_ACIERTO,
    TOLERANCIA_DE_SESGO,
    CasoDeEval,
    Medicion,
    ParContrafactual,
    ResumenDeAcierto,
    Umbrales,
    porcentaje,
)
from app.domain.puertos import EvaluadorDeCvs, ExtractorDeTexto, ProveedorNoDisponibleError
from app.infrastructure.coincidencias import ExtractorDeTextoDeCv
from app.infrastructure.evaluacion import LlmScoring
from app.skills import load_skill

#: El set sintético del repo (services/hr-engine/app/cli → raíz del repo).
SET_SINTETICO = Path(__file__).resolve().parents[4] / "evals" / "cv-evaluator" / "sinteticos"


class SetInvalidoError(ValueError):
    """El `casos.yaml` o sus CV no sirven para medir."""


@dataclass(frozen=True, slots=True)
class SetDeCasos:
    casos: list[CasoDeEval]
    umbrales: Umbrales


@dataclass(frozen=True, slots=True)
class Informe:
    acierto: ResumenDeAcierto
    pares: tuple[ParContrafactual, ...]
    umbrales: Umbrales
    repeticiones: int
    costo_usd: float
    evaluaciones: int
    modelos: list[str]

    @property
    def sesgados(self) -> list[ParContrafactual]:
        return [p for p in self.pares if p.sesgado]

    @property
    def fallas(self) -> list[str]:
        fallas = self.acierto.fallas(self.umbrales)
        if self.sesgados:
            fallas.append(
                f"{len(self.sesgados)} de {len(self.pares)} pares contrafactuales se movieron"
            )
        return fallas


def cargar_set(directorio: Path, extractor: ExtractorDeTexto | None = None) -> SetDeCasos:
    """Lee `casos.yaml` y el texto de cada CV. Junta todos los problemas antes de fallar."""
    archivo = directorio / "casos.yaml"
    if not archivo.is_file():
        raise SetInvalidoError(f"no hay casos.yaml en {directorio}")
    datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
    extractor = extractor or ExtractorDeTextoDeCv()
    problemas: list[str] = []
    vacantes = {
        str(clave): _vacante(str(clave), v or {}, problemas)
        for clave, v in (datos.get("vacantes") or {}).items()
    }
    casos: list[CasoDeEval] = []
    vistos: set[str] = set()
    for i, caso in enumerate(datos.get("casos") or [], start=1):
        identificador = str(caso.get("id") or f"#{i}")
        if identificador in vistos:
            problemas.append(f"{identificador}: el id está repetido")
            continue
        vistos.add(identificador)
        texto = _texto_del_cv(directorio, caso.get("cv"), extractor, identificador, problemas)
        vacante = vacantes.get(str(caso.get("vacante")))
        if vacante is None:
            problemas.append(f"{identificador}: no existe la vacante {caso.get('vacante')!r}")
        esperado = caso.get("esperado")
        if esperado is not None and (
            isinstance(esperado, bool)
            or not isinstance(esperado, int | float)
            or not 0 <= esperado <= 10
        ):
            problemas.append(f"{identificador}: esperado tiene que ir de 0 a 10")
            esperado = None
        if texto is None or vacante is None:
            continue
        casos.append(
            CasoDeEval(
                id=identificador,
                texto=texto,
                nombre=caso.get("nombre"),
                correo=caso.get("correo"),
                vacante=vacante,
                esperado=None if esperado is None else float(esperado),
            )
        )
    if not casos and not problemas:
        problemas.append("casos.yaml no trae casos")
    if problemas:
        raise SetInvalidoError("\n".join(f"- {p}" for p in problemas))
    return SetDeCasos(casos=casos, umbrales=_umbrales(datos.get("umbrales") or {}))


def _vacante(clave: str, datos: dict[str, Any], problemas: list[str]) -> VacanteParaEvaluar | None:
    titulo, descripcion = datos.get("titulo"), datos.get("descripcion")
    if not titulo or not descripcion:
        problemas.append(f"vacante {clave}: le falta el titulo o la descripcion")
        return None
    return VacanteParaEvaluar(
        titulo=str(titulo).strip(),
        descripcion=str(descripcion).strip(),
        skills=tuple(str(s) for s in datos.get("skills") or ()),
        nivel=datos.get("nivel"),
        modalidad=datos.get("modalidad"),
        ubicacion=datos.get("ubicacion"),
        icp_text=datos.get("icp"),
    )


def _texto_del_cv(
    directorio: Path,
    nombre_del_archivo: object,
    extractor: ExtractorDeTexto,
    identificador: str,
    problemas: list[str],
) -> str | None:
    if not nombre_del_archivo:
        problemas.append(f"{identificador}: falta el cv")
        return None
    ruta = (directorio / str(nombre_del_archivo)).resolve()
    if not ruta.is_relative_to(directorio.resolve()) or not ruta.is_file():
        problemas.append(f"{identificador}: no está el cv {nombre_del_archivo} en el directorio")
        return None
    # El sintético va en texto; el real, como lo mandó el candidato.
    texto = (
        ruta.read_text(encoding="utf-8")
        if ruta.suffix.lower() == ".txt"
        else extractor.extraer(ruta.read_bytes())
    )
    if texto is None or not es_legible(texto):
        problemas.append(f"{identificador}: el cv no se puede leer, igual que en producción")
        return None
    return texto


def _umbrales(datos: dict[str, Any]) -> Umbrales:
    base = Umbrales()
    return Umbrales(
        pearson_r=float(datos.get("pearson_r", base.pearson_r)),
        tasa_de_acierto=float(datos.get("tasa_de_acierto", base.tasa_de_acierto)),
        min_casos=int(datos.get("min_casos", base.min_casos)),
    )


async def medir(
    set_de_casos: SetDeCasos,
    evaluador: EvaluadorDeCvs,
    *,
    repeticiones: int,
    ejes: list[str],
) -> Informe:
    medidor = MedirElEvaluador(evaluador, repeticiones=repeticiones)
    acierto = await medidor.acierto(set_de_casos.casos)
    pares = await medidor.sesgo(set_de_casos.casos, ejes) if ejes else ()
    return Informe(
        acierto=acierto,
        pares=pares,
        umbrales=set_de_casos.umbrales,
        repeticiones=repeticiones,
        costo_usd=medidor.costo_usd,
        evaluaciones=medidor.evaluaciones,
        modelos=sorted(medidor.modelos),
    )


def _medicion(m: Medicion) -> dict[str, Any]:
    return {
        "scores": list(m.scores),
        "media": None if m.media is None else round(m.media, 2),
        "ruido": round(m.ruido, 2),
        "errores": m.errores,
    }


def como_dict(
    informe: Informe, *, fecha: datetime, version_del_skill: str | None
) -> dict[str, Any]:
    """El informe en JSON. Solo ids de casos: nada que identifique a un candidato."""
    a, u = informe.acierto, informe.umbrales
    return {
        "fecha": fecha.isoformat(),
        "skill": {"nombre": "cv-evaluator", "version": version_del_skill},
        "modelos": informe.modelos,
        "repeticiones": informe.repeticiones,
        "tolerancias": {"acierto": TOLERANCIA_DE_ACIERTO, "sesgo": TOLERANCIA_DE_SESGO},
        "umbrales": {
            "pearson_r": u.pearson_r,
            "tasa_de_acierto": u.tasa_de_acierto,
            "min_casos": u.min_casos,
        },
        "acierto": {
            "pearson_r": None if a.pearson_r is None else round(a.pearson_r, 3),
            "tasa_de_acierto": round(a.tasa_de_acierto, 3),
            "acuerdo_en_el_paso": round(a.acuerdo_en_el_paso, 3),
            "casos": [
                {
                    "id": x.caso,
                    "esperado": x.esperado,
                    **_medicion(x.medicion),
                    "acierta": x.acierta,
                    "mismo_paso": x.mismo_paso,
                }
                for x in a.aciertos
            ],
        },
        "sesgo": {
            "pares": [
                {
                    "caso": p.caso,
                    "eje": p.eje,
                    "valores": list(p.valores),
                    "a": _medicion(p.a),
                    "b": _medicion(p.b),
                    "diferencia": None if p.diferencia is None else round(p.diferencia, 2),
                    "cambia_el_paso": p.cambia_el_paso,
                    "sesgado": p.sesgado,
                }
                for p in informe.pares
            ],
            "sesgados": len(informe.sesgados),
        },
        "costo_usd": round(informe.costo_usd, 4),
        "evaluaciones": informe.evaluaciones,
        "pasa": not informe.fallas,
        "fallas": informe.fallas,
    }


def _media(m: Medicion) -> str:
    return "—" if m.media is None else f"{m.media:.1f}"


def como_texto(informe: Informe, *, version_del_skill: str | None, salida: Path) -> str:
    a, u = informe.acierto, informe.umbrales
    modelos = ", ".join(informe.modelos) or "sin respuesta"
    lineas = [
        f"cv-evaluator {version_del_skill or '?'} · {modelos} · "
        f"{len(a.aciertos)} casos con score esperado · {informe.repeticiones} repeticiones",
        "",
        f"Acierto: a {TOLERANCIA_DE_ACIERTO} puntos o menos de lo que puso la persona",
    ]
    for x in a.aciertos:
        errores = f" · {x.medicion.errores} errores" if x.medicion.errores else ""
        lineas.append(
            f"  {x.caso:<32} esperado {x.esperado:>4.1f}  obtenido {_media(x.medicion):>4} "
            f"±{x.medicion.ruido:.1f}  {'acierta' if x.acierta else 'FALLA  '}  "
            f"{'mismo paso' if x.mismo_paso else 'otro paso'}{errores}"
        )
    r = "—" if a.pearson_r is None else f"{a.pearson_r:.2f}"
    lineas.append(
        f"  Pearson r {r} (mín. {u.pearson_r:.2f}) · acierta el {porcentaje(a.tasa_de_acierto)} "
        f"(mín. {porcentaje(u.tasa_de_acierto)}) · mismo paso el "
        f"{porcentaje(a.acuerdo_en_el_paso)}"
    )
    if informe.pares:
        lineas += [
            "",
            f"Sesgo: el score no debe moverse más de {TOLERANCIA_DE_SESGO} ni cambiar la sugerencia",
        ]
        for p in informe.pares:
            diferencia = "sin medición" if p.diferencia is None else f"Δ {p.diferencia:.2f}"
            marca = "  SE MOVIÓ" if p.sesgado else ""
            lineas.append(
                f"  {p.caso:<32} {p.eje:<7} {p.valores[0]} {_media(p.a)} / "
                f"{p.valores[1]} {_media(p.b)}  {diferencia}{marca}"
            )
        lineas.append(f"  {len(informe.sesgados)} de {len(informe.pares)} pares se movieron.")
    lineas += [
        "",
        f"Costo: US${informe.costo_usd:.2f} en {informe.evaluaciones} evaluaciones.",
        f"Informe: {salida}",
        "PASA" if not informe.fallas else "NO PASA",
        *(f"- {f}" for f in informe.fallas),
    ]
    return "\n".join(lineas)


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.evals_cv_evaluator",
        description="Mide el acierto y el sesgo del evaluador de CVs con un set de casos.",
    )
    parser.add_argument(
        "--dir", help="directorio con casos.yaml; por defecto EVALS_CV_EVALUATOR_DIR o el sintético"
    )
    parser.add_argument(
        "--repeticiones",
        type=int,
        default=3,
        help="cuántas veces se evalúa cada CV: el modelo no es determinista (3)",
    )
    parser.add_argument("--sin-sesgo", action="store_true", help="solo mide el acierto")
    parser.add_argument(
        "--ejes", nargs="+", choices=list(EJES), default=list(EJES), help="ejes del sesgo"
    )
    parser.add_argument("--salida", help="dónde escribir el informe JSON")
    args = parser.parse_args(argv)
    if args.repeticiones < 1:
        parser.error("--repeticiones tiene que ser 1 o más")
    return args


def main(argv: list[str] | None = None, evaluador: EvaluadorDeCvs | None = None) -> int:
    args = _argumentos(argv)
    directorio = Path(args.dir or os.environ.get("EVALS_CV_EVALUATOR_DIR") or SET_SINTETICO)
    try:
        set_de_casos = cargar_set(directorio)
    except SetInvalidoError as exc:
        print(f"El set de {directorio} no sirve para medir:\n{exc}", file=sys.stderr)
        return 2
    ejes = [] if args.sin_sesgo else list(dict.fromkeys(args.ejes))
    con_esperado = sum(c.esperado is not None for c in set_de_casos.casos)
    llamadas = args.repeticiones * (con_esperado + 2 * len(ejes) * len(set_de_casos.casos))
    print(f"Unas {llamadas} llamadas al modelo.", file=sys.stderr)
    try:
        informe = asyncio.run(
            medir(
                set_de_casos, evaluador or LlmScoring(), repeticiones=args.repeticiones, ejes=ejes
            )
        )
    except ProveedorNoDisponibleError as exc:
        print(
            f"No hay modelo disponible ({exc}). Pon GOOGLE_API_KEY, del nivel de pago, u "
            "OPENAI_API_KEY en services/hr-engine/.env.",
            file=sys.stderr,
        )
        return 2
    fecha = datetime.now(UTC)
    salida = (
        Path(args.salida)
        if args.salida
        else directorio / "resultados" / f"{fecha:%Y-%m-%dT%H%M%S}.json"
    )
    version = load_skill("cv-evaluator").metadata.get("version")
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(
            como_dict(informe, fecha=fecha, version_del_skill=version), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(como_texto(informe, version_del_skill=version, salida=salida))
    return 0 if not informe.fallas else 1


def _sin_el_aviso_de_redis(
    _logger: object, _metodo: str, evento: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    """Sin Redis, el breaker avisa en cada llamada: en una medición es solo ruido."""
    if evento.get("event") == "llm.breaker.redis_down":
        raise structlog.DropEvent
    return evento


def _avisos_a_stderr() -> None:
    """Lo que avisa el cliente del modelo (un respaldo, un reintento) va a stderr; lo demás no."""
    structlog.configure(
        processors=[_sin_el_aviso_de_redis, *structlog.get_config()["processors"]],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
    )


if __name__ == "__main__":
    _avisos_a_stderr()
    raise SystemExit(main())
