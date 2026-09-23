"""Ponto de entrada usado pelo agendador (Windows Task Scheduler) - roda o
pipeline de todos os canais ativos e notifica o dono ao final (balão do
Windows + log em data/logs/), sem exigir que ele abra terminal nenhum.

Cadastro no Task Scheduler (uma vez, ou via scripts/setup_task_scheduler.ps1):
  Programa: <caminho do .venv>\\Scripts\\python.exe
  Argumentos: scripts\\run_daily.py
  Iniciar em: <pasta do projeto>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import notify, orchestrator  # noqa: E402


def main() -> None:
    try:
        track_ids = orchestrator.run_all_active_channels()
    except Exception as exc:
        notify.notify_result(False, f"Erro inesperado no pipeline: {exc}")
        raise

    if track_ids:
        notify.notify_result(
            True, f"{len(track_ids)} vídeo(s) gerado(s) (tracks {track_ids}). Aguardando revisão."
        )
    else:
        notify.notify_result(
            False, "Nenhum vídeo foi gerado hoje - nenhum canal ativo ou todos falharam. Veja o log em data/logs/."
        )


if __name__ == "__main__":
    main()
