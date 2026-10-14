"""La guarda de los tests RLS solo deja borrar una base de prueba en un host local."""

from __future__ import annotations

import pytest

from tests.security.conftest import _assert_disposable


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://vortex:vortex@localhost:5432/vortex_test",
        "postgresql://vortex:vortex@127.0.0.1:55432/vortex_test",
    ],
)
def test_acepta_una_base_de_prueba_local(dsn: str) -> None:
    _assert_disposable(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        # La base persistente del compose de dev: antes pasaba la guarda.
        "postgresql://vortex:vortex@localhost:5432/vortex_dev",
        "postgresql://vortex:vortex@localhost:5432/postgres",
        "postgresql://vortex:pw@db.prod.vortex:5432/vortex_test",
    ],
)
def test_rechaza_lo_que_no_es_desechable(dsn: str) -> None:
    with pytest.raises(RuntimeError, match="Aborto"):
        _assert_disposable(dsn)
