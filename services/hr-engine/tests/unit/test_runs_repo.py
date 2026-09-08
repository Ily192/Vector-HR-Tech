"""Tests del repositorio de `runs` (creación, lock de idempotencia, update).

Regresión del bug 5: `update_run_status` hacía `UPDATE runs WHERE id = :run_id`
sobre una fila que NUNCA se creaba → 0 filas afectadas, sin error, cost tracking
perdido en silencio.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.repositories import runs as runs_repo

EMPRESA_ID = uuid4()
RUN_ID = uuid4()


class _FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> _FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row


class FakeSession:
    """AsyncSession de mentira: devuelve resultados pre-cargados en orden."""

    def __init__(self, results: list[dict[str, Any] | None]) -> None:
        self._results = list(results)
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        if not self._results:
            raise AssertionError("execute() llamado más veces de las previstas")
        return _FakeResult(self._results.pop(0))

    async def commit(self) -> None:
        return None


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": RUN_ID,
        "empresa_id": EMPRESA_ID,
        "agent_skill": "sourcer",
        "status": runs_repo.STATUS_PENDING,
        "cost_usd": 0,
        "cost_cap_usd": 0.05,
        "error_message": None,
        "payload": None,
    }
    row.update(overrides)
    return row


def _as_db(session: FakeSession) -> Any:
    return session


# ── update_run_status ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_run_status_raises_when_no_rows_affected() -> None:
    session = FakeSession([None])
    with pytest.raises(runs_repo.RunNotFoundError, match=str(RUN_ID)):
        await runs_repo.update_run_status(
            _as_db(session),
            run_id=RUN_ID,
            status=runs_repo.STATUS_COMPLETED,
            cost_usd=0.01,
        )


@pytest.mark.asyncio
async def test_update_run_status_persists_error_message() -> None:
    session = FakeSession([{"id": RUN_ID}])
    await runs_repo.update_run_status(
        _as_db(session),
        run_id=RUN_ID,
        status=runs_repo.STATUS_FAILED,
        cost_usd=0.02,
        error_message="CostCapExceeded: cost cap excedido",
    )
    params = session.params[0]
    assert params["status"] == "failed"
    assert params["cost_usd"] == 0.02
    assert params["error_message"].startswith("CostCapExceeded")


# ── create_run ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_run_inserts_pending_row() -> None:
    session = FakeSession([{"id": RUN_ID}])
    created = await runs_repo.create_run(
        _as_db(session),
        run_id=RUN_ID,
        empresa_id=EMPRESA_ID,
        agent_skill="sourcer",
        cost_cap_usd=0.05,
    )
    assert created is True
    assert "insert into runs" in session.statements[0]
    assert session.params[0]["cost_cap_usd"] == 0.05


@pytest.mark.asyncio
async def test_create_run_is_idempotent() -> None:
    # insert → conflicto (None), luego el select del run existente.
    session = FakeSession([None, _row()])
    created = await runs_repo.create_run(
        _as_db(session),
        run_id=RUN_ID,
        empresa_id=EMPRESA_ID,
        agent_skill="sourcer",
        cost_cap_usd=0.05,
    )
    assert created is False


@pytest.mark.asyncio
async def test_create_run_detects_tenant_mismatch() -> None:
    session = FakeSession([None, _row(empresa_id=uuid4())])
    with pytest.raises(runs_repo.TenantMismatchError):
        await runs_repo.create_run(
            _as_db(session),
            run_id=RUN_ID,
            empresa_id=EMPRESA_ID,
            agent_skill="sourcer",
            cost_cap_usd=0.05,
        )


# ── claim_run ───────────────────────────────────────────────────────────────


async def _claim(session: FakeSession) -> runs_repo.RunClaim:
    return await runs_repo.claim_run(
        _as_db(session),
        run_id=RUN_ID,
        empresa_id=EMPRESA_ID,
        agent_skill="sourcer",
        cost_cap_usd=0.05,
        stale_after_seconds=660,
    )


@pytest.mark.asyncio
async def test_claim_run_claims_pending_row() -> None:
    # create (insert ok) → update claim ok
    session = FakeSession([{"id": RUN_ID}, _row(status=runs_repo.STATUS_RUNNING)])
    claim = await _claim(session)
    assert claim.outcome is runs_repo.ClaimOutcome.CLAIMED
    assert claim.run.cost_cap_usd == 0.05
    assert session.params[-1]["stale"] == 660


@pytest.mark.asyncio
async def test_claim_run_detects_already_completed() -> None:
    # create (conflicto) → select existente → update claim falla → select estado
    completed = _row(status=runs_repo.STATUS_COMPLETED, cost_usd=0.004)
    session = FakeSession([None, completed, None, completed])
    claim = await _claim(session)
    assert claim.outcome is runs_repo.ClaimOutcome.ALREADY_COMPLETED
    assert claim.run.cost_usd == pytest.approx(0.004)


@pytest.mark.asyncio
async def test_claim_run_detects_in_progress() -> None:
    running = _row(status=runs_repo.STATUS_RUNNING)
    session = FakeSession([None, running, None, running])
    claim = await _claim(session)
    assert claim.outcome is runs_repo.ClaimOutcome.IN_PROGRESS


@pytest.mark.asyncio
async def test_claim_run_filters_by_tenant() -> None:
    session = FakeSession([{"id": RUN_ID}, _row(status=runs_repo.STATUS_RUNNING)])
    await _claim(session)
    assert session.params[-1]["empresa_id"] == str(EMPRESA_ID)
    assert "empresa_id = :empresa_id" in session.statements[-1]


@pytest.mark.asyncio
async def test_get_run_parses_json_payload() -> None:
    session = FakeSession([_row(payload='{"candidates_found": 3}')])
    run = await runs_repo.get_run(_as_db(session), RUN_ID)
    assert run is not None
    assert run.payload == {"candidates_found": 3}
    assert isinstance(run.id, UUID)


# ── run_state: sesión propia, sin tenant context (por RLS) ──────────────────


@pytest.mark.asyncio
async def test_run_state_uses_its_own_session_without_tenant_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`runs` solo tiene política RLS `for select`.

    Bajo el rol `authenticated` el UPDATE matchearía 0 filas, así que el estado
    del run se escribe en una sesión aparte que NO llama a `set_tenant_context`.
    """
    from contextlib import asynccontextmanager

    from app.workers import run_state

    opened: list[FakeSession] = []

    @asynccontextmanager
    async def fake_session() -> Any:
        session = FakeSession([{"id": RUN_ID}])
        opened.append(session)
        yield session

    monkeypatch.setattr(run_state, "db_session", fake_session)

    await run_state.finish_run(
        run_id=str(RUN_ID),
        status=runs_repo.STATUS_COMPLETED,
        cost_usd=0.01,
        payload={"ok": True},
    )

    assert len(opened) == 1
    sql = " ".join(opened[0].statements).lower()
    assert "set local role" not in sql
    assert "set_config" not in sql
    assert "update runs" in sql


def test_retry_countdown_grows_and_is_capped() -> None:
    from app.workers import run_state

    assert 1 <= run_state.retry_countdown(0) <= 5
    assert 1 <= run_state.retry_countdown(1) <= 10
    assert run_state.retry_countdown(10) <= 60


def test_truncate_error_includes_type_and_is_bounded() -> None:
    from app.workers import run_state

    message = run_state.truncate_error(ValueError("x" * 1000))
    assert message.startswith("ValueError: ")
    assert len(message) == 500


def test_stale_after_seconds_exceeds_task_time_limit() -> None:
    from app.config import settings
    from app.workers import run_state

    assert run_state.stale_after_seconds() > settings.celery_task_time_limit
