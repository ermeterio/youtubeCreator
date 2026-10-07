"""Testa o retry com backoff exponencial do worker da fila contra um banco
sqlite real (temporário), não mockado - só orchestrator.prepare_daily_video
é substituído (é a chamada cara/externa de verdade: LLM, ffmpeg etc.)."""

from datetime import datetime, timezone

import pytest

from pipeline import channels, queue_worker


@pytest.fixture
def channel_id(temp_catalog):
    return channels.create_channel("Canal de Teste")


@pytest.fixture
def queue_item(temp_catalog, channel_id):
    with temp_catalog.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO generation_queue (channel_id, topic_label, topic_query, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (channel_id, "Tema de teste", "teste", datetime.now(timezone.utc).isoformat()),
        )
        item_id = cur.lastrowid
    with temp_catalog.get_conn() as conn:
        return conn.execute("SELECT * FROM generation_queue WHERE id = ?", (item_id,)).fetchone()


def _reload(temp_catalog, item_id):
    with temp_catalog.get_conn() as conn:
        return conn.execute("SELECT * FROM generation_queue WHERE id = ?", (item_id,)).fetchone()


def test_transient_failure_schedules_retry_with_backoff(monkeypatch, temp_catalog, queue_item):
    def _boom(*a, **kw):
        raise RuntimeError("Ollama indisponível")

    monkeypatch.setattr(queue_worker.orchestrator, "prepare_daily_video", _boom)

    queue_worker._process_one(queue_item)

    row = _reload(temp_catalog, queue_item["id"])
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert row["next_attempt_at"] is not None
    assert row["started_at"] is None

    next_attempt = datetime.fromisoformat(row["next_attempt_at"])
    delta_minutes = (next_attempt - datetime.now(timezone.utc)).total_seconds() / 60
    assert 2 <= delta_minutes <= 2.4  # primeiro backoff: 2min + até 20% de jitter


def test_exhausting_all_attempts_marks_permanently_failed(monkeypatch, temp_catalog, queue_item):
    def _boom(*a, **kw):
        raise RuntimeError("falha persistente")

    monkeypatch.setattr(queue_worker.orchestrator, "prepare_daily_video", _boom)

    item = queue_item
    for _ in range(queue_worker._MAX_ATTEMPTS):
        queue_worker._process_one(item)
        item = _reload(temp_catalog, item["id"])

    assert item["status"] == "failed"
    assert item["attempts"] == queue_worker._MAX_ATTEMPTS
    assert item["error"] == "falha persistente"


def test_success_marks_done_with_track_id(monkeypatch, temp_catalog, queue_item):
    monkeypatch.setattr(queue_worker.orchestrator, "prepare_daily_video", lambda *a, **kw: 42)

    queue_worker._process_one(queue_item)

    row = _reload(temp_catalog, queue_item["id"])
    assert row["status"] == "done"
    assert row["track_id"] == 42
    assert row["finished_at"] is not None
