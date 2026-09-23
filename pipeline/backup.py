"""Backup leve do catálogo (SQLite) - copiado antes de cada execução
agendada, pra sobreviver a corrupção do arquivo ou a uma migração de schema
que dê errado. É só cópia de arquivo (o catálogo é pequeno), sem
infraestrutura extra - mantém as últimas N cópias por idade."""

import shutil
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
    shutil.copy2(config.CATALOG_DB, dest)

    backups = sorted(BACKUP_DIR.glob("catalog_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[KEEP_LAST:]:
        old.unlink(missing_ok=True)
