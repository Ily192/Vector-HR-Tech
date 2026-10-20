"""Alta de una empresa en el plan gratis, desde la terminal de Vector HR.

    python -m app.cli.alta_empresa --empresa "Ferretería Norte" \\
        --correo ana@ferreterianorte.mx --nombre "Ana Ruiz" --tamano 35
    python -m app.cli.alta_empresa --reenviar ana@ferreterianorte.mx

Crea la empresa con plan gratis y su invitación de un solo uso, y Supabase Auth
manda el correo; el enlace deja a la persona dentro del panel. `--reenviar`
vuelve a mandarlo a quien no ha entrado (el enlace dura una hora).

Necesita DATABASE_URL (el rol dueño de la base), SUPABASE_URL,
SUPABASE_SECRET_KEY y PANEL_URL. La lógica está en
`application/dar_de_alta_empresa.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import httpx

from app.application.dar_de_alta_empresa import DarDeAltaEmpresa, ReenviarInvitacion
from app.config import settings
from app.database import db_session
from app.domain.alta import SolicitudDeAlta, SolicitudInvalidaError
from app.domain.puertos import CuentaYaExisteError, InvitacionNoEnviadaError
from app.infrastructure.altas import InvitacionesSupabase, SqlRepositorioDeAltas

#: Lo que se espera a la API de Auth antes de dar la invitación por no enviada.
TIMEOUT_DE_AUTH_S = 30.0


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.alta_empresa",
        description="Da de alta una empresa en el plan gratis e invita a su HR al panel.",
    )
    parser.add_argument("--empresa", help="nombre de la empresa, como lo verán los candidatos")
    parser.add_argument("--correo", help="correo de trabajo de quien usará el panel")
    parser.add_argument("--nombre", help="nombre de esa persona")
    parser.add_argument(
        "--tamano",
        type=int,
        help="número de personas: con 51 o más tiene 4 vacantes activas; si no, 3",
    )
    parser.add_argument("--rol", choices=["HR", "Director"], default="HR")
    parser.add_argument(
        "--reenviar", metavar="CORREO", help="vuelve a mandar la invitación a quien no ha entrado"
    )
    args = parser.parse_args(argv)
    if not args.reenviar and not (args.empresa and args.correo and args.nombre):
        parser.error("hacen falta --empresa, --correo y --nombre, o --reenviar CORREO")
    return args


async def _correr(args: argparse.Namespace) -> str:
    async with db_session() as db, httpx.AsyncClient(timeout=TIMEOUT_DE_AUTH_S) as http:
        repositorio = SqlRepositorioDeAltas(db)
        invitaciones = InvitacionesSupabase(
            settings.supabase_url, settings.supabase_secret_key, settings.panel_url, http
        )
        if args.reenviar:
            await ReenviarInvitacion(repositorio, invitaciones).ejecutar(args.reenviar)
            return (
                f"Invitación reenviada a {args.reenviar.strip().lower()}. "
                f"El enlace vuelve a {settings.panel_url}."
            )
        solicitud = SolicitudDeAlta.nueva(
            empresa=args.empresa,
            correo=args.correo,
            nombre=args.nombre,
            tamano=args.tamano,
            rol=args.rol,
        )
        alta = await DarDeAltaEmpresa(repositorio, invitaciones).ejecutar(solicitud)
        return (
            f"{solicitud.empresa} quedó dada de alta en el plan gratis "
            f"(slug {alta.slug}, id {alta.empresa_id}).\n"
            f"Invitación enviada a {solicitud.correo}. El enlace vuelve a {settings.panel_url}."
        )


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    # En desarrollo el motor imprime cada SQL (`echo`); en un comando solo estorba.
    logging.getLogger("sqlalchemy.engine.Engine").disabled = True
    if not (settings.supabase_url and settings.supabase_secret_key):
        print("Faltan SUPABASE_URL y SUPABASE_SECRET_KEY.", file=sys.stderr)
        return 2
    try:
        print(asyncio.run(_correr(args)))
    except (SolicitudInvalidaError, CuentaYaExisteError, LookupError) as exc:
        print(f"No se hizo nada: {exc}.", file=sys.stderr)
        return 1
    except InvitacionNoEnviadaError as exc:
        print(f"La invitación no salió y no quedó nada a medias: {exc}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
