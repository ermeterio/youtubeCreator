"""Notificação e log diário - avisa o dono (sem precisar abrir terminal)
quando a execução agendada termina, com sucesso ou falha, e mantém um log
simples em texto por dia em data/logs/.

Notificação usa balão nativo do Windows via PowerShell/System.Windows.Forms -
não exige nenhum pacote pip extra nem serviço externo (e-mail/SMTP fica como
alternativa futura se a máquina rodar sem sessão de usuário logada, caso em
que balão de notificação não aparece)."""

import subprocess
from datetime import datetime
from pathlib import Path

import config

LOG_DIR = config.DATA_DIR / "logs"


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


def notify_result(success: bool, message: str) -> None:
    log(("OK: " if success else "FALHA: ") + message)
    toast(
        "YouTube Content Creator - pronto para revisão" if success else "YouTube Content Creator - falha na geração",
        message,
    )
