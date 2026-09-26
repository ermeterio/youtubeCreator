"""Backup leve do catálogo (SQLite) - copiado antes de cada execução
agendada, pra sobreviver a corrupção do arquivo ou a uma migração de schema
que dê errado. Mantém as últimas N cópias por idade.

Usa a API de backup online do próprio sqlite3 (Connection.backup), NÃO cópia
de arquivo crua - o banco roda em modo WAL (ver catalog.get_conn), onde
escritas recentes ficam num arquivo -wal à parte até um checkpoint; uma
cópia crua do .db sozinho poderia silenciosamente sair sem as transações
mais recentes. A API de backup do sqlite3 lida com isso corretamente."""

import sqlite3
from datetime import datetime

import config

BACKUP_DIR = config.DATA_DIR / "backups"
KEEP_LAST = 30


def backup_catalog() -> None:
    if not config.CATALOG_DB.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"catalog_{stamp}.db"

    source_conn = sqlite3.connect(config.CATALOG_DB)
    dest_conn = sqlite3.connect(dest)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    backups = sorted(BACKUP_DIR.glob("catalog_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[KEEP_LAST:]:
        old.unlink(missing_ok=True)
