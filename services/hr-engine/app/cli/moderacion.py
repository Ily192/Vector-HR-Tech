"""La moderación de vacantes desde la terminal de Vector HR (ADR-022).

    python -m app.cli.moderacion cola                     # lo que espera revisión
    python -m app.cli.moderacion aprobar --vacante <id>
    python -m app.cli.moderacion rechazar --vacante <id> --motivo "Pide un depósito"
    python -m app.cli.moderacion verificar --correo rh@empresa.com.mx \\
        [--web https://empresa.com.mx] [--linkedin …] [--publica-para propia|clientes] [--forzar]
    python -m app.cli.moderacion barrer                   # un barrido, sin esperar al beat

`verificar` sin `--forzar` da la insignia solo si el dominio del correo coincide con
el de la web; con `--forzar`, Vector HR la da a mano (revisó LinkedIn y la web). Un
reclutador independiente nunca la lleva.

Necesita DATABASE_URL (el rol dueño de la base). La lógica está en
`application/moderar_vacantes.py` y `application/verificar_empresa.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import asdict
from uuid import UUID

from app.application.moderar_vacantes import (
    ModerarVacantesPendientes,
    MotivoVacioError,
    ResolverRevision,
)
from app.application.verificar_empresa import VerificarEmpresa
from app.config import settings
from app.database import db_session
from app.infrastructure.moderacion import SqlRepositorioDeModeracion


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.moderacion",
        description="Cola de revisión, insignia de empresas y barrido de la moderación.",
    )
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("cola", help="vacantes en revisión u ocultas por reportes")
    sub.add_parser("barrer", help="modera ahora las vacantes pendientes")
    aprobar = sub.add_parser("aprobar", help="publica una vacante en revisión")
    aprobar.add_argument("--vacante", type=UUID, required=True)
    rechazar = sub.add_parser("rechazar", help="no publica una vacante; la empresa ve el motivo")
    rechazar.add_argument("--vacante", type=UUID, required=True)
    rechazar.add_argument("--motivo", required=True)
    verificar = sub.add_parser("verificar", help="guarda cómo publica una empresa y su insignia")
    verificar.add_argument("--correo", required=True, help="correo de una persona de la empresa")
    verificar.add_argument("--web")
    verificar.add_argument("--linkedin")
    verificar.add_argument("--publica-para", choices=["propia", "clientes"], default="propia")
    verificar.add_argument("--forzar", action="store_true", help="da la insignia a mano")
    return parser.parse_args(argv)


async def _correr(args: argparse.Namespace) -> str:
    async with db_session() as db:
        repositorio = SqlRepositorioDeModeracion(db)
        match args.orden:
            case "barrer":
                resultado = await ModerarVacantesPendientes(repositorio).ejecutar(
                    lote=settings.moderacion_lote
                )
                return str(asdict(resultado))
            case "cola":
                lineas = []
                for v in await repositorio.cola_completa():
                    lineas.append(f"{v.id}  {v.estado.value:<11}  {v.titulo} · {v.empresa}")
                    lineas += [f"    - {m.senal}" for m in v.motivos]
                return "\n".join(lineas) or "No hay vacantes esperando revisión."
            case "aprobar":
                if await ResolverRevision(repositorio).aprobar(args.vacante):
                    return f"Vacante {args.vacante} publicada."
                raise LookupError(f"la vacante {args.vacante} no estaba esperando revisión")
            case "rechazar":
                if await ResolverRevision(repositorio).rechazar(args.vacante, args.motivo):
                    return f"Vacante {args.vacante} rechazada. La empresa ve el motivo en su panel."
                raise LookupError(f"la vacante {args.vacante} no se podía rechazar")
            case "verificar":
                empresa_id = await repositorio.empresa_por_correo(args.correo)
                if empresa_id is None:
                    raise LookupError(f"nadie con el correo {args.correo} tiene cuenta")
                verificada = await VerificarEmpresa(repositorio).ejecutar(
                    empresa_id,
                    correo=args.correo,
                    publica_para=args.publica_para,
                    web=args.web,
                    linkedin=args.linkedin,
                    forzar=args.forzar,
                )
                return (
                    f"Empresa {empresa_id}: publica para {args.publica_para}, "
                    f"{'con' if verificada else 'sin'} insignia de empresa verificada."
                )
    raise AssertionError(args.orden)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    logging.getLogger("sqlalchemy.engine.Engine").disabled = True
    try:
        print(asyncio.run(_correr(args)))
    except (LookupError, MotivoVacioError, ValueError) as exc:
        print(f"No se hizo nada: {exc}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
