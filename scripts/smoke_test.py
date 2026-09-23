"""Diagnóstico rápido das dependências externas do pipeline - roda em
segundos, sem gerar vídeo nenhum. Útil antes de uma sessão de mudança no
código, ou quando algo falhou e não está claro por quê.

Uso: python scripts/smoke_test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import config  # noqa: E402
from pipeline import catalog, channels, script_gen  # noqa: E402

OK = "OK"
FALHOU = "FALHOU"

_results: list[tuple[str, str, str]] = []  # (check, status, detail)


def _check(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status, detail))


def check_ollama() -> None:
    if script_gen.ollama_available():
        _check("Ollama (localhost:11434)", OK)
    else:
        _check("Ollama (localhost:11434)", FALHOU, "não respondeu - rode `ollama serve` antes do pipeline.")


def check_nasa_key() -> None:
    key = channels.shared_nasa_api_key() or config.NASA_API_KEY
    try:
        response = requests.get(
            "https://api.nasa.gov/planetary/apod", params={"api_key": key}, timeout=10
        )
        if response.status_code == 200:
            note = "usando DEMO_KEY (limite baixo)" if key == "DEMO_KEY" else "chave própria"
            _check("NASA API (APOD)", OK, note)
        elif response.status_code == 429:
            _check("NASA API (APOD)", FALHOU, "limite de requisições excedido (rate limit) - " +
                   ("troque o DEMO_KEY por uma chave própria em api.nasa.gov." if key == "DEMO_KEY" else
                    "aguarde ou verifique o uso da sua chave."))
        else:
            _check("NASA API (APOD)", FALHOU, f"HTTP {response.status_code}")
    except Exception as exc:
        _check("NASA API (APOD)", FALHOU, str(exc))


def check_edge_tts() -> None:
    try:
        import edge_tts  # noqa: F401
        _check("edge-tts (pacote instalado)", OK)
    except Exception as exc:
        _check("edge-tts (pacote instalado)", FALHOU, str(exc))


def check_channels() -> None:
    rows = channels.list_channels()
    if not rows:
        _check("Canais cadastrados", FALHOU, "nenhum canal no banco - rode a interface pra criar um.")
        return
    _check("Canais cadastrados", OK, f"{len(rows)} canal(is)")

    for ch in rows:
        label = f"Canal '{ch['name']}'"
        if not ch["active"]:
            _check(label, OK, "inativo (não roda no agendador)")
            continue

        secret_path = channels.client_secret_path(ch["slug"])
        token_path = channels.token_path(ch["slug"])
        if not secret_path.exists():
            _check(label, FALHOU, "sem client_secret.json - cadastre na interface.")
            continue
        if not token_path.exists():
            _check(label, FALHOU, "credenciais salvas mas ainda não autorizado - clique em 'Autorizar no YouTube'.")
            continue

        try:
            from pipeline import youtube_upload
            info = youtube_upload.get_channel_info(secret_path, token_path)
            if info:
                _check(label, OK, f"conectado a '{info.get('title')}'")
            else:
                _check(label, FALHOU, "autorizado, mas a conta não tem canal do YouTube criado ainda.")
        except Exception as exc:
            msg = str(exc)
            if "insufficient" in msg.lower() or "scope" in msg.lower():
                _check(label, FALHOU, "escopo insuficiente - reautorize (e confira os escopos na Tela de "
                       "consentimento OAuth do Google Cloud Console).")
            else:
                _check(label, FALHOU, msg[:200])


def main() -> int:
    catalog.init_db()
    channels.ensure_default_channel()

    check_ollama()
    check_nasa_key()
    check_edge_tts()
    check_channels()

    print("\n=== Diagnóstico YouTube Content Creator ===\n")
    any_fail = False
    for name, status, detail in _results:
        mark = "[OK]  " if status == OK else "[FALHOU]"
        print(f"{mark} {name}" + (f" - {detail}" if detail else ""))
        if status == FALHOU:
            any_fail = True

    print()
    if any_fail:
        print("Há pendência(s) acima - resolva antes de contar com a geração automática.")
        return 1
    print("Tudo certo - o pipeline deve rodar sem travar em dependência externa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
