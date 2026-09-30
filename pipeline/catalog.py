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

-- Registro de cada decisão humana de aprovar/rejeitar um vídeo (com o
-- score de qualidade automático daquele momento) - evidência estruturada
-- de "controle editorial significativo" caso o canal precise contestar um
-- flag de "inauthentic content" da política do YouTube (ver ROADMAP.md).
-- Append-only por design: nunca é atualizado ou apagado, só inserido.
CREATE TABLE IF NOT EXISTS approval_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    quality_score INTEGER,
    created_at TEXT NOT NULL
);

-- Agenda semanal por canal: quais dias da semana geram vídeo automaticamente
-- e se usam a cascata de escolha de tema ou um tema fixo planejado com
-- antecedência (ver ensure_channel_schedule). weekday segue
-- datetime.date.weekday(): 0=segunda-feira ... 6=domingo.
CREATE TABLE IF NOT EXISTS channel_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    weekday INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    topic_mode TEXT NOT NULL DEFAULT 'auto',
    topic_label TEXT,
    topic_query TEXT,
    UNIQUE(channel_id, weekday)
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
        "thumbnail_b_path": "TEXT",
        "active_thumbnail": "TEXT NOT NULL DEFAULT 'a'",
        "published_at": "TEXT",
        "thumbnail_rotated_at": "TEXT",
        "quality_score": "INTEGER",
        "quality_breakdown": "TEXT",
        # Distinto de `status` de propósito: aprovar só o Short não muda o
        # `status` do vídeo longo (continua 'pending_review'), então esse
        # vídeo nunca saía da revisão em lote mesmo já tendo algo publicado.
        # `reviewed` é setado tanto por aprovar/rejeitar quanto por um botão
        # manual "revisado" (pra tirar da fila sem aprovar/rejeitar nada
        # ainda) - relatado como falha real: "quando enviado pro YouTube ali
        # não é atualizado".
        "reviewed": "INTEGER NOT NULL DEFAULT 0",
        "reviewed_at": "TEXT",
    },
    "channels": {
        "series_primary": "TEXT NOT NULL DEFAULT 'Direto da Fonte'",
        "series_fallback": "TEXT NOT NULL DEFAULT 'Round-up Rápido'",
        "language": "TEXT NOT NULL DEFAULT 'pt-BR'",
        "connected_youtube_channel_id": "TEXT",
        "connected_youtube_channel_title": "TEXT",
        "connected_youtube_channel_thumbnail": "TEXT",
        "connected_at": "TEXT",
        "default_privacy": "TEXT NOT NULL DEFAULT 'private'",
        "video_category_id": "TEXT NOT NULL DEFAULT '28'",
        "made_for_kids": "INTEGER NOT NULL DEFAULT 0",
        # Ajuste de ritmo/tom aplicado à voz neural gratuita (edge-tts) -
        # reduz a sensação "robótica" sem custar nada nem trocar de voz.
        # Formato esperado pelo edge-tts: rate em "+N%"/"-N%", pitch em
        # "+NHz"/"-NHz". Vazio = usa o padrão de fábrica da voz ("+0%"/"+0Hz").
        "narration_rate": "TEXT NOT NULL DEFAULT '+0%'",
        "narration_pitch": "TEXT NOT NULL DEFAULT '+0Hz'",
        # Provedor de narração opcional pago (voz bem mais natural que o
        # edge-tts gratuito) - 'edge' (padrão) usa o motor grátis de sempre,
        # 'elevenlabs' usa a conta/chave própria do dono. Se a chamada à
        # ElevenLabs falhar por qualquer motivo (cota do plano grátis
        # estourada, chave inválida, API fora do ar), o pipeline cai
        # automaticamente pro edge-tts - a geração diária nunca trava
        # esperando um provedor pago responder.
        "tts_provider": "TEXT NOT NULL DEFAULT 'edge'",
        "elevenlabs_api_key": "TEXT",
        "elevenlabs_voice_id": "TEXT",
    },
    "channel_schedule": {
        # Voz específica pra esse dia da semana - None/vazio usa a voz padrão
        # do canal (channels.narration_voice_for). Permite, por exemplo,
        # alternar de voz nos fins de semana sem mudar a voz padrão do canal.
        "voice": "TEXT",
    },
}


@contextmanager
def get_conn():
    # WAL permite leitores e um escritor concorrentes sem se bloquearem, e
    # busy_timeout faz o SQLite ESPERAR (até 10s) por um lock em vez de
    # levantar "database is locked" na hora - sem isso, o worker da fila
    # (thread própria), as requests do Flask (múltiplas threads) e o job
    # agendado das 3h abrindo conexões curtas e concorrentes no mesmo
    # arquivo é receita clássica pra esse erro em picos de uso simultâneo.
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.CATALOG_DB, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
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


def log_approval_decision(track_id: int, channel_id: int, decision: str, quality_score: int | None) -> None:
    """Registra uma decisão humana de aprovar/rejeitar - append-only,
    evidência de revisão editorial real por vídeo (ver nota no schema)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO approval_log (track_id, channel_id, decision, quality_score, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (track_id, channel_id, decision, quality_score, datetime.now(timezone.utc).isoformat()),
        )


def list_approval_log(channel_id: int | None = None, limit: int = 200) -> list[sqlite3.Row]:
    query = "SELECT * FROM approval_log"
    params: tuple = ()
    if channel_id is not None:
        query += " WHERE channel_id = ?"
        params = (channel_id,)
    query += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


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


def recent_titles(channel_id: int, limit: int = 20) -> list[str]:
    """Títulos gerados recentemente NESSE canal - usado pra detectar
    repetição de hook/estilo (ver script_gen.compute_quality_score), não só
    de tema bruto (isso já existe em recent_topics). Título carrega o gancho
    de verdade, tema bruto às vezes é só uma palavra-chave interna."""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT title FROM tracks WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
            (channel_id, limit),
        )
        return [row["title"] for row in cur.fetchall()]


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


# --- Agenda semanal por canal (ver nota no schema, tabela channel_schedule) ---

def ensure_channel_schedule(channel_id: int) -> None:
    """Garante que o canal tem as 7 linhas de agenda (uma por dia da semana),
    todas habilitadas com modo 'auto' por padrão - idempotente, chamar
    quantas vezes quiser. Sem isso, a agenda semanal do canal fica vazia
    (equivalente a "nunca gerar"), então isso deve ser chamado na criação do
    canal e defensivamente sempre que a agenda for lida/editada."""
    with get_conn() as conn:
        for weekday in range(7):
            conn.execute(
                "INSERT OR IGNORE INTO channel_schedule (channel_id, weekday, enabled, topic_mode) "
                "VALUES (?, ?, 1, 'auto')",
                (channel_id, weekday),
            )


def get_channel_schedule(channel_id: int) -> list[sqlite3.Row]:
    """Retorna as 7 linhas de agenda desse canal, ordenadas por weekday (0-6).
    Chama ensure_channel_schedule primeiro pra garantir que sempre há 7
    linhas, mesmo pra canais criados antes desta feature existir."""
    ensure_channel_schedule(channel_id)
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM channel_schedule WHERE channel_id = ? ORDER BY weekday",
            (channel_id,),
        ).fetchall()


def update_schedule_day(channel_id: int, weekday: int, enabled: bool, topic_mode: str,
                         topic_label: str | None, topic_query: str | None,
                         voice: str | None = None) -> None:
    """Atualiza a configuração de UM dia da semana pra esse canal (upsert).
    `voice` é opcional - None/vazio significa "usar a voz padrão do canal"."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE channel_schedule SET enabled = ?, topic_mode = ?, topic_label = ?, topic_query = ?, voice = ? "
            "WHERE channel_id = ? AND weekday = ?",
            (int(enabled), topic_mode, topic_label, topic_query, voice, channel_id, weekday),
        )
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO channel_schedule (channel_id, weekday, enabled, topic_mode, topic_label, topic_query, voice) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (channel_id, weekday, int(enabled), topic_mode, topic_label, topic_query, voice),
            )
