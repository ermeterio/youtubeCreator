"""Notificação e log diário - avisa o dono (sem precisar abrir terminal)
quando a execução agendada termina, com sucesso ou falha, e mantém um log
simples em texto por dia em data/logs/.

Notificação usa balão nativo do Windows via PowerShell/System.Windows.Forms -
não exige nenhum pacote pip extra nem serviço externo (e-mail/SMTP fica como
alternativa futura se a máquina rodar sem sessão de usuário logada, caso em
que balão de notificação não aparece)."""

import json
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import config

LOG_DIR = config.DATA_DIR / "logs"
STAGE_LOG_PATH = LOG_DIR / "stages.jsonl"


def log(message: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%H:%M:%S")
    log_path = LOG_DIR / f"{day}.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")
    return log_path


def _ps_escape(text: str) -> str:
    return text.replace("'", "''")


def toast(title: str, message: str) -> None:
    """Balão de notificação nativo do Windows. Best-effort: se falhar (ex.:
    rodando sem sessão gráfica), não deve derrubar o pipeline - o log em
    arquivo já registrou o resultado de qualquer forma."""
    script = (
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "Add-Type -AssemblyName System.Drawing\n"
        "$notify = New-Object System.Windows.Forms.NotifyIcon\n"
        "$notify.Icon = [System.Drawing.SystemIcons]::Information\n"
        "$notify.Visible = $true\n"
        f"$notify.ShowBalloonTip(12000, '{_ps_escape(title)}', '{_ps_escape(message)}', "
        "[System.Windows.Forms.ToolTipIcon]::Info)\n"
        "Start-Sleep -Seconds 13\n"
        "$notify.Dispose()\n"
    )
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def log_stage(channel: str, track_id: int | None, stage: str, status: str,
              duration_s: float | None = None, error: str | None = None) -> None:
    """Uma linha JSON por estágio do pipeline, em data/logs/stages.jsonl -
    sem infra nova (Prometheus/Grafana não fazem sentido pra um processo
    local de 1 usuário), só um arquivo somável/filtrável depois (jq, pandas)
    pra achar qual estágio é o gargalo real ao longo do tempo, em vez de
    adivinhar olhando o log de texto livre."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "channel": channel,
        "track_id": track_id,
        "stage": stage,
        "status": status,
    }
    if duration_s is not None:
        entry["duration_s"] = round(duration_s, 2)
    if error:
        entry["error"] = str(error)[:300]
    with open(STAGE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@contextmanager
def stage_timer(channel: str, track_id: int | None, stage: str):
    """Mede e registra (via log_stage) quanto tempo um estágio do pipeline
    levou e se terminou OK ou lançou exceção - propaga a exceção normalmente
    (isso aqui só observa, nunca engole erro nem muda comportamento)."""
    start = time.monotonic()
    try:
        yield
    except Exception as exc:
        log_stage(channel, track_id, stage, "failed", time.monotonic() - start, error=str(exc))
        raise
    else:
        log_stage(channel, track_id, stage, "ok", time.monotonic() - start)


def notify_result(success: bool, message: str) -> None:
    log(("OK: " if success else "FALHA: ") + message)
    toast(
        "YouTube Content Creator - pronto para revisão" if success else "YouTube Content Creator - falha na geração",
        message,
    )
