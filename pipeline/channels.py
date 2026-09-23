"""Gestão de múltiplos canais (multi-conta) - cada canal é um "perfil"
independente: nicho/temas próprios, chave da NASA própria (opcional), e
credenciais OAuth do YouTube próprias, isoladas em secrets/<slug>/ e com
saída própria em data/output/<slug>/.

Isso permite manter vários canais de assuntos diferentes rodando no mesmo
pipeline/máquina, cada um publicando na sua própria conta do YouTube.
"""

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import config
from pipeline import catalog

DEFAULT_TOPICS = [
    ("buracos negros", "black hole"),
    ("nebulosas", "nebula"),
    ("exoplanetas", "exoplanet"),
    ("a vida das estrelas", "star formation"),
    ("sistema solar", "solar system"),
    ("galáxias e colisões cósmicas", "galaxy collision"),
    ("matéria escura e energia escura", "dark matter"),
    ("missões espaciais históricas", "space mission"),
    ("aglomerados de estrelas", "star cluster"),
    ("a origem do universo", "big bang"),
]


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "canal"


def secrets_dir(slug: str) -> Path:
    d = config.SECRETS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def output_dir(slug: str) -> Path:
    d = config.OUTPUT_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def client_secret_path(slug: str) -> Path:
    return secrets_dir(slug) / "client_secret.json"


def token_path(slug: str) -> Path:
    return secrets_dir(slug) / "youtube_token.json"


def shared_nasa_api_key() -> str | None:
    """Chave da NASA compartilhada por TODOS os canais - configurada uma vez
    na interface (painel principal) em vez de repetida canal por canal.
    Canais novos já nascem usando essa chave automaticamente."""
    return catalog.get_setting("shared_nasa_api_key")


def set_shared_nasa_api_key(value: str | None) -> None:
    catalog.set_setting("shared_nasa_api_key", value)


def nasa_api_key_for(channel: sqlite3.Row) -> str:
    # Prioridade: chave específica desse canal (raro, só se alguém quiser um
    # canal usando uma chave diferente da compartilhada) -> chave
    # compartilhada global -> DEMO_KEY (último recurso, limite baixo).
    return channel["nasa_api_key"] or shared_nasa_api_key() or config.NASA_API_KEY


def language_for(channel: sqlite3.Row) -> dict:
    code = channel["language"] if "language" in channel.keys() and channel["language"] else config.DEFAULT_LANGUAGE
    return config.LANGUAGES.get(code, config.LANGUAGES[config.DEFAULT_LANGUAGE])


def narration_voice_for(channel: sqlite3.Row) -> str:
    if channel["narration_voice"]:
        return channel["narration_voice"]
    return language_for(channel)["default_voice"]


def topics_for(channel: sqlite3.Row) -> list[tuple[str, str]]:
    return [tuple(t) for t in json.loads(channel["topics_json"])]


def has_youtube_credentials(channel: sqlite3.Row) -> bool:
    return client_secret_path(channel["slug"]).exists()


def set_connected_channel_info(channel_id: int, info: dict) -> None:
    """Guarda qual canal REAL do YouTube ficou conectado depois de uma
    autorização - mostrado na interface pra o dono conferir na hora se é o
    canal certo, em vez de descobrir só quando um vídeo sai no canal errado."""
    update_channel(
        channel_id,
        connected_youtube_channel_id=info.get("id"),
        connected_youtube_channel_title=info.get("title"),
        connected_youtube_channel_thumbnail=info.get("thumbnail_url"),
        connected_at=datetime.now(timezone.utc).isoformat(),
    )


def disconnect_channel(channel_id: int) -> None:
    """Remove o token salvo (mantém o client_secret.json) e limpa a
    identidade conectada - a próxima autorização abre o navegador do zero
    com prompt=select_account, forçando a tela de escolha de conta/canal do
    Google a aparecer de novo."""
    channel = get_channel(channel_id)
    token_path(channel["slug"]).unlink(missing_ok=True)
    update_channel(
        channel_id,
        connected_youtube_channel_id=None,
        connected_youtube_channel_title=None,
        connected_youtube_channel_thumbnail=None,
        connected_at=None,
    )


def delete_channel(channel_id: int, delete_local_files: bool = True) -> None:
    """Exclui o canal do YouTube Content Creator: linha do banco + (opcionalmente) a pasta
    de secrets e a pasta de vídeos gerados locais. NUNCA apaga nada no
    YouTube - vídeos já publicados lá continuam existindo, isso exige ação
    separada e explícita (excluir pelo YouTube antes, se for o caso)."""
    import shutil

    channel = get_channel(channel_id)
    if delete_local_files:
        shutil.rmtree(secrets_dir(channel["slug"]), ignore_errors=True)
        shutil.rmtree(output_dir(channel["slug"]), ignore_errors=True)
    with catalog.get_conn() as conn:
        conn.execute("DELETE FROM tracks WHERE channel_id = ?", (channel_id,))
        conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))


def create_channel(name: str, niche: str = "", topics: list[tuple[str, str]] | None = None,
                    nasa_api_key: str | None = None, narration_voice: str | None = None,
                    language: str | None = None, series_primary: str | None = None,
                    series_fallback: str | None = None) -> int:
    slug = slugify(name)
    topics = topics or DEFAULT_TOPICS
    language = language if language in config.LANGUAGES else config.DEFAULT_LANGUAGE
    lang_defaults = config.LANGUAGES[language]
    # Nomes de série no idioma do canal - sem isso, um canal em inglês nascia
    # com selos "Direto da Fonte"/"Round-up Rápido" em português (default fixo
    # da coluna do banco), destoando do resto do vídeo.
    series_primary = series_primary or lang_defaults["default_series_primary"]
    series_fallback = series_fallback or lang_defaults["default_series_fallback"]
    with catalog.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO channels (slug, name, niche, topics_json, nasa_api_key, narration_voice, language, "
            "series_primary, series_fallback, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (slug, name, niche, json.dumps(topics, ensure_ascii=False), nasa_api_key, narration_voice, language,
             series_primary, series_fallback, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def update_channel(channel_id: int, **fields) -> None:
    if not fields:
        return
    if "topics" in fields:
        fields["topics_json"] = json.dumps(fields.pop("topics"), ensure_ascii=False)
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [channel_id]
    with catalog.get_conn() as conn:
        conn.execute(f"UPDATE channels SET {columns} WHERE id = ?", values)


def get_channel(channel_id: int) -> sqlite3.Row:
    with catalog.get_conn() as conn:
        row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if row is None:
        raise ValueError(f"Canal {channel_id} não encontrado.")
    return row


def list_channels(active_only: bool = False) -> list[sqlite3.Row]:
    query = "SELECT * FROM channels"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY id"
    with catalog.get_conn() as conn:
        return conn.execute(query).fetchall()


def _migrate_per_channel_key_to_shared() -> None:
    """Migração: antes da chave da NASA virar configuração compartilhada,
    cada canal tinha seu próprio campo. Se já existe alguma chave cadastrada
    num canal e ainda não há chave compartilhada definida, promove a
    primeira encontrada pra compartilhada (preserva o que o dono já
    cadastrou) e limpa o campo por-canal, que deixou de aparecer na
    interface."""
    if shared_nasa_api_key():
        return
    for channel in list_channels():
        if channel["nasa_api_key"]:
            set_shared_nasa_api_key(channel["nasa_api_key"])
            update_channel(channel["id"], nasa_api_key=None)
            return


def ensure_default_channel() -> sqlite3.Row:
    """Migração de projetos anteriores ao suporte multi-canal: se ainda não
    existe nenhum canal cadastrado, cria o canal "Astronomia" original e
    reaproveita as credenciais que já estavam soltas em secrets/ (formato
    de canal único usado antes desta versão)."""
    existing = list_channels()
    if existing:
        _migrate_per_channel_key_to_shared()
        return existing[0]

    if config.NASA_API_KEY != "DEMO_KEY" and not shared_nasa_api_key():
        set_shared_nasa_api_key(config.NASA_API_KEY)

    channel_id = create_channel(
        name="Astronomia",
        niche="Divulgação científica / astronomia (NASA APOD)",
        topics=DEFAULT_TOPICS,
        narration_voice=config.NARRATION_VOICE,
    )
    channel = get_channel(channel_id)

    legacy_secret = config.SECRETS_DIR / "client_secret.json"
    legacy_token = config.SECRETS_DIR / "youtube_token.json"
    if legacy_secret.exists():
        client_secret_path(channel["slug"]).write_bytes(legacy_secret.read_bytes())
    if legacy_token.exists():
        token_path(channel["slug"]).write_bytes(legacy_token.read_bytes())

    return get_channel(channel_id)
