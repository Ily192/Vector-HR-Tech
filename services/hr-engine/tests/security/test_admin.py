"""El SQL del área de admin (ADR-022, enmienda del 2026-11-17) contra Postgres real.

El tablero cuenta con el rol dueño, sin contexto de tenant, como el resto del hr-engine;
la cola trae la web y el LinkedIn de la empresa para quien revisa. La base es compartida
por toda la suite: se comparan diferencias, no totales.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.domain.moderacion import EstadoDeModeracion
from app.infrastructure.admin import SqlResumenDeLaPlataforma
from app.infrastructure.moderacion import SqlRepositorioDeModeracion

from .conftest import _asyncpg_dsn
from .test_moderacion import _como_dueno, _del_panel
from .test_plan_gratis import _empresa

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def sesion(_migrated_db: None) -> AsyncIterator[AsyncSession]:
    """La sesión del hr-engine: rol dueño, sin contexto de tenant."""
    motor = create_async_engine(
        _asyncpg_dsn().replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool
    )
    async with AsyncSession(motor) as s:
        yield s
    await motor.dispose()


async def _alta_web(
    db: asyncpg.Connection, empresa_id: str, *, hace: timedelta, confirmada: bool
) -> None:
    await _como_dueno(
        db,
        """
        insert into privado.altas_web (
            lead_id, empresa_id, correo, resultado, publica_para, verificacion, pais,
            sector, contrataciones_mes, creado_en, confirmado_en
        ) values (
            $1, $2::uuid, 'rh@andes.test', 'empresa_creada', 'propia', 'revision', 'mx',
            'logistica', '1-2', now() - $3::interval,
            case when $4::boolean then now() end
        )
        """,
        f"e2e-{uuid.uuid4()}",
        empresa_id,
        hace,
        confirmada,
    )


async def test_el_resumen_cuenta_empresas_altas_y_vacantes(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    resumen = SqlResumenDeLaPlataforma(sesion)
    antes = await resumen.resumen()

    empresa_id = await _empresa(db, tamano=30)
    await _como_dueno(
        db,
        "update empresas set verificada = true, verificada_en = now() where id = $1::uuid",
        empresa_id,
    )
    # Una de esta semana que confirmó el código y una vieja que no.
    await _alta_web(db, empresa_id, hace=timedelta(hours=1), confirmada=True)
    await _alta_web(db, empresa_id, hace=timedelta(days=10), confirmada=False)
    en_revision = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'en_revision' where id = $1::uuid", en_revision
    )
    cerrada = await _del_panel(db, empresa_id, titulo="Chofer")
    await _como_dueno(db, "update vacantes set status = 'closed' where id = $1::uuid", cerrada)
    await sesion.rollback()  # que la sesión vea lo nuevo

    despues = await resumen.resumen()
    assert despues.empresas - antes.empresas == 1
    assert despues.empresas_verificadas - antes.empresas_verificadas == 1
    assert despues.altas_web_confirmadas - antes.altas_web_confirmadas == 1
    assert despues.altas_ultimos_7_dias - antes.altas_ultimos_7_dias == 1
    assert despues.vacantes_abiertas - antes.vacantes_abiertas == 1
    assert despues.vacantes_cerradas - antes.vacantes_cerradas == 1
    # Por estado cuentan solo las abiertas: la cerrada (pendiente) no suma.
    diferencia = {
        e: despues.vacantes_por_moderacion[e] - antes.vacantes_por_moderacion[e]
        for e in EstadoDeModeracion
    }
    assert diferencia == {e: int(e is EstadoDeModeracion.EN_REVISION) for e in EstadoDeModeracion}
    assert despues.aplicaciones >= despues.aplicaciones_ultimos_7_dias >= 0


async def test_la_cola_trae_la_web_el_linkedin_y_la_fecha(
    db: asyncpg.Connection, sesion: AsyncSession
) -> None:
    empresa_id = await _empresa(db)
    await _como_dueno(
        db,
        "update empresas set web = 'https://andes.mx',"
        " linkedin = 'https://www.linkedin.com/company/andes' where id = $1::uuid",
        empresa_id,
    )
    vacante_id = await _del_panel(db, empresa_id)
    await _como_dueno(
        db, "update vacantes set moderacion = 'en_revision' where id = $1::uuid", vacante_id
    )

    repo = SqlRepositorioDeModeracion(sesion)
    (en_cola,) = [v for v in await repo.cola_completa() if str(v.id) == vacante_id]
    assert (en_cola.web, en_cola.linkedin) == (
        "https://andes.mx",
        "https://www.linkedin.com/company/andes",
    )
    assert en_cola.creada_en is not None
    una = await repo.vacante_en_cola(en_cola.id)
    assert una is not None and una.web == "https://andes.mx"
