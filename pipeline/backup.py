"""Backup leve do catálogo (SQLite) + credenciais OAuth - copiado antes de
cada execução agendada, pra sobreviver a corrupção do arquivo, uma migração
de schema que dê errado, ou perda de disco. Mantém as últimas N cópias por
idade.

Usa a API de backup online do próprio sqlite3 (Connection.backup), NÃO cópia
de arquivo crua - o banco roda em modo WAL (ver catalog.get_conn), onde
escritas recentes ficam num arquivo -wal à parte até um checkpoint; uma
cópia crua do .db sozinho poderia silenciosamente sair sem as transações
mais recentes. A API de backup do sqlite3 lida com isso corretamente.

IMPORTANTE - isto é só a METADE "local" da regra 3-2-1 de backup (3 cópias,
2 mídias, 1 fora do local). Pra ter uma cópia de verdade fora desta máquina
sem precisar de orçamento/infra nova, aponte o cliente de sync que você já
usa (OneDrive, Google Drive, Dropbox) pra esta pasta (`data/backups/`) nas
configurações dele - o pipeline só garante que tudo que importa pra
recuperar o canal do zero esteja reunido aqui num snapshot consistente."""

import shutil
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


def backup_secrets() -> None:
    """Backup das credenciais OAuth de cada canal (client_secret.json +
    youtube_token.json, por slug, em secrets/<slug>/) - lacuna real
    encontrada por pesquisa (07/10/2026): sem isso, perder o disco não
    perde histórico (isso o catalog já cobre), mas exige reautorizar
    MANUALMENTE cada canal, fricção real num pipeline pensado pra rodar
    "sem operador diário". Zipado num arquivo só por snapshot (não cópia
    solta de arquivo), mesmo padrão de retenção do catalog_*.db."""
    if not config.SECRETS_DIR.exists() or not any(config.SECRETS_DIR.iterdir()):
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_base = BACKUP_DIR / f"secrets_{stamp}"
    shutil.make_archive(str(dest_base), "zip", root_dir=config.SECRETS_DIR)

    backups = sorted(BACKUP_DIR.glob("secrets_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[KEEP_LAST:]:
        old.unlink(missing_ok=True)


def run_all() -> None:
    """Backup completo (catálogo + segredos) numa chamada só - usado no
    início de cada execução agendada (ver orchestrator.run_all_active_
    channels)."""
    backup_catalog()
    backup_secrets()
