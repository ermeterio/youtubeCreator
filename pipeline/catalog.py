import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    niche TEXT,
    topics_json TEXT NOT NULL,
    nasa_api_key TEXT,
    narration_voice TEXT,
    language TEXT NOT NULL DEFAULT 'pt-BR',
    series_primary TEXT NOT NULL DEFAULT 'Direto da Fonte',
    series_fallback TEXT NOT NULL DEFAULT 'Round-up Rápido',
    connected_youtube_channel_id TEXT,
    connected_youtube_channel_title TEXT,
    connected_youtube_channel_thumbnail TEXT,
    connected_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS generation_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    topic_label TEXT NOT NULL,
    topic_query TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    track_id INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    script TEXT NOT NULL,
    image_credits TEXT,
    narration_path TEXT,
    video_path TEXT,
    video_vertical_path TEXT,
    thumbnail_path TEXT,
    youtube_video_id TEXT,
    youtube_short_video_id TEXT,
    fact_check_flag TEXT,
    series TEXT,
    feedback TEXT,
    feedback_notes TEXT,
    feedback_action TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL
);
"""

# Colunas adicionadas depois da criação inicial da tabela - CREATE TABLE IF
# NOT EXISTS não afeta um banco já existente, então o init_db() migra bancos
# antigos adicionando as colunas que faltarem.
_MIGRATION_COLUMNS = {
    "tracks": {
        "video_vertical_path": "TEXT",
        "youtube_short_video_id": "TEXT",
        "channel_id": "INTEGER NOT NULL DEFAULT 1",
        "fact_check_flag": "TEXT",
        "series": "TEXT",
        "feedback": "TEXT",
        "feedback_notes": "TEXT",
        "feedback_action": "TEXT",
        "clarity_review": "TEXT",
        "fact_check_details": "TEXT",
    },
    "channels": {
        "series_primary": "TEXT NOT NULL DEFAULT 'Direto da Fonte'",
        "series_fallback": "TEXT NOT NULL DEFAULT 'Round-up Rápido'",
        "language": "TEXT NOT NULL DEFAULT 'pt-BR'",
        "connected_youtube_channel_id": "TEXT",
        "connected_youtube_channel_title": "TEXT",
        "connected_youtube_channel_thumbnail": "TEXT",
        "connected_at": "TEXT",
    },
}


@contextmanager
def get_conn():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.CATALOG_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        for table, columns in _MIGRATION_COLUMNS.items():
            existing_columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, col_type in columns.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def create_track(title: str, topic: str, script: str, image_credits: str, channel_id: int = 1) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tracks (channel_id, title, topic, script, image_credits, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'planned', ?)",
            (channel_id, title, topic, script, image_credits, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def update_track(track_id: int, **fields):
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [track_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE tracks SET {columns} WHERE id = ?", values)


def get_track(track_id: int) -> sqlite3.Row:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        return cur.fetchone()


def list_tracks(channel_id: int | None = None, limit: int = 200) -> list[sqlite3.Row]:
    query = "SELECT * FROM tracks"
    params: tuple = ()
    if channel_id is not None:
        query += " WHERE channel_id = ?"
        params = (channel_id,)
    query += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def count_pending_review() -> int:
    """Quantos vídeos estão prontos e esperando só a publicação no YouTube -
    usado pra mostrar um contador na navegação (padrão familiar de quem usa
    o YouTube Studio: contagem de itens pendentes visível sem precisar
    entrar em cada canal pra descobrir)."""
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM tracks WHERE status = 'pending_review'").fetchone()
    return row["n"]


def feedback_examples(channel_id: int, feedback: str, limit: int = 5) -> list[sqlite3.Row]:
    """Últimos tracks do canal com essa avaliação (`liked`/`disliked`) - usado
    pra montar exemplos reais no prompt do roteirista (ver script_gen.py),
    fazendo o LLM local aprender por few-shot com o que o dono já validou,
    já que não há infraestrutura de fine-tuning nesse pipeline."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tracks WHERE channel_id = ? AND feedback = ? "
            "ORDER BY id DESC LIMIT ?",
            (channel_id, feedback, limit),
        ).fetchall()


def recent_topics(channel_id: int, lookback: int = 10) -> set[str]:
    """Temas usados recentemente NESSE canal - usado pra evitar repetição
    perceptível quando o pipeline roda por meses seguidos (ver
    script_gen._choose_fallback_topic). Filtrado por canal porque temas de
    canais diferentes não têm relação entre si."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT topic FROM tracks WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
            (channel_id, lookback),
        )
        return {row["topic"] for row in cur.fetchall()}


def topic_recently_used(topic: str, channel_id: int, lookback: int = 10) -> bool:
    return topic in recent_topics(channel_id, lookback)


# --- Sugestões de tema (persistidas, não em memória - sobrevivem a reinício
# do servidor e não somem quando o dono age em outra coisa) ---

def save_suggested_topics(channel_id: int, topics: list[tuple[str, str]]) -> None:
    import json
    set_setting(f"suggested_topics_channel_{channel_id}", json.dumps(topics, ensure_ascii=False))


def get_suggested_topics(channel_id: int) -> list[tuple[str, str]]:
    import json
    raw = get_setting(f"suggested_topics_channel_{channel_id}")
    if not raw:
        return []
    return [tuple(t) for t in json.loads(raw)]


# --- Fila de geração sob demanda (várias sugestões marcadas de uma vez,
# processadas 1 por vez em segundo plano - ver pipeline.queue_worker) ---

def enqueue_topics(channel_id: int, topics: list[tuple[str, str]]) -> list[int]:
    ids = []
    with get_conn() as conn:
        for label, query in topics:
            cur = conn.execute(
                "INSERT INTO generation_queue (channel_id, topic_label, topic_query, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (channel_id, label, query, datetime.now(timezone.utc).isoformat()),
            )
            ids.append(cur.lastrowid)
    return ids


def next_pending_queue_item() -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM generation_queue WHERE status = 'pending' ORDER BY id LIMIT 1"
        ).fetchone()


def update_queue_item(item_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [item_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE generation_queue SET {columns} WHERE id = ?", values)


def list_queue_items(channel_id: int | None = None, limit: int = 50) -> list[sqlite3.Row]:
    query = "SELECT * FROM generation_queue"
    params: tuple = ()
    if channel_id is not None:
        query += " WHERE channel_id = ?"
        params = (channel_id,)
    query += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def delete_queue_item(item_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM generation_queue WHERE id = ? AND status = 'pending'", (item_id,))
