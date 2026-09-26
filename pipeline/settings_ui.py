"""Interface local de configuração - cadastro de canais e parametrização de
tokens/credenciais (chave da NASA, client_secret.json do YouTube, voz,
temas). Roda só na máquina local (127.0.0.1), sem exposição externa.

Uso: `python -m pipeline.settings_ui` e abra http://127.0.0.1:5151 no navegador.

Existe pra separar "configurar credenciais" (tarefa manual, feita uma vez por
canal, quando o dono tiver os tokens em mãos) de "rodar o pipeline"
(automático, via agendador) - sem isso, cadastrar um canal novo exigiria
editar código/JSON na mão.
"""

import json
import threading
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for

import config
from pipeline import catalog, channels, notify, orchestrator, reports, spam_detection, youtube_analytics, youtube_upload

app = Flask(__name__)

_authorize_status: dict[int, str] = {}
_generation_status: dict[int, str] = {}
_consult_status: dict[int, str] = {}
_comment_suggestions: dict[str, str] = {}

BASE_TEMPLATE = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Content Creator - painel de controle</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0b0e17;
    --bg-glow: radial-gradient(circle at 15% -10%, #2a1f5c33, transparent 45%),
               radial-gradient(circle at 100% 0%, #0e3b5c33, transparent 40%);
    --panel: #131826;
    --panel-border: #232b40;
    --panel-hover: #171e30;
    --text: #e7ebf5;
    --text-muted: #8892ab;
    --accent: #7c6cf0;
    --accent-2: #35c7c1;
    --accent-grad: linear-gradient(135deg, #7c6cf0, #35c7c1);
    --ok-bg: #113328; --ok-fg: #4ce0a4;
    --missing-bg: #3a1c22; --missing-fg: #ff7d8a;
    --inactive-bg: #1c2233; --inactive-fg: #8892ab;
    --radius: 12px;
  }
  * { box-sizing: border-box; }
  body {
    font-family: 'Inter', system-ui, sans-serif;
    max-width: 980px; margin: 0 auto; padding: 32px 20px 80px;
    background-color: var(--bg); background-image: var(--bg-glow); background-attachment: fixed;
    color: var(--text); line-height: 1.5;
  }
  h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; font-weight: 700; letter-spacing: -0.01em; }
  h1 { font-size: 1.6rem; margin: 0; background: var(--accent-grad); -webkit-background-clip: text;
       background-clip: text; color: transparent; display: inline-block; }
  h1::before { content: "✦ "; -webkit-text-fill-color: var(--accent-2); }
  h2 { font-size: 1.2rem; margin: 2rem 0 0.75rem; color: var(--text) !important; background: var(--panel);
       padding: 10px 16px; border-radius: 8px; border: 1px solid var(--panel-border); display: inline-block; }
  h3 { font-size: 1rem; margin: 1.5rem 0 0.5rem; color: var(--text-muted); text-transform: uppercase;
       letter-spacing: 0.04em; font-size: 0.8rem; }
  a { color: var(--accent-2); text-decoration: none; }
  a:hover { text-decoration: underline; }

  nav { display: flex; gap: 4px; margin: 24px 0 28px; padding: 5px; background: var(--panel);
        border: 1px solid var(--panel-border); border-radius: 999px; width: fit-content; }
  nav a { padding: 8px 18px; border-radius: 999px; font-weight: 600; font-size: 0.9rem; color: var(--text-muted); }
  nav a:hover { text-decoration: none; color: var(--text); background: var(--panel-hover); }
  nav a.active { background: var(--accent-grad); color: #0b0e17; }

  table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; background: var(--panel);
          border: 1px solid var(--panel-border); border-radius: var(--radius); overflow: hidden; }
  th { text-align: left; padding: 12px 14px; font-size: 0.75rem; text-transform: uppercase;
       letter-spacing: 0.04em; color: var(--text-muted); background: var(--panel-hover);
       border-bottom: 1px solid var(--panel-border); }
  td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--panel-border); font-size: 0.9rem; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--panel-hover); }

  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.72rem;
           font-weight: 600; letter-spacing: 0.01em; margin: 2px 3px 2px 0; }
  .ok { background: var(--ok-bg); color: var(--ok-fg); }
  .missing { background: var(--missing-bg); color: var(--missing-fg); }
  .inactive { background: var(--inactive-bg); color: var(--inactive-fg); }

  form.inline { display: inline; }
  label { display: block; margin-top: 14px; font-weight: 600; font-size: 0.85rem; color: var(--text-muted); }
  input[type=text], input[type=password], textarea, select {
    width: 100%; padding: 10px 12px; margin-top: 6px; box-sizing: border-box; font-family: inherit;
    background: var(--panel); border: 1px solid var(--panel-border); border-radius: 8px;
    color: var(--text); font-size: 0.9rem;
  }
  input:focus, textarea:focus, select:focus { outline: none; border-color: var(--accent); }
  textarea { font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; }
  select { appearance: none; }

  button, .btn {
    margin-top: 14px; padding: 10px 20px; cursor: pointer; border: none;
    background: var(--accent-grad); color: #0b0e17; border-radius: 8px; font-weight: 700;
    font-size: 0.88rem; text-decoration: none; display: inline-block; margin-right: 8px;
    transition: filter 0.15s, transform 0.1s;
  }
  button:hover, .btn:hover { filter: brightness(1.12); text-decoration: none; }
  button:active, .btn:active { transform: scale(0.98); }
  button.secondary, .btn.secondary {
    background: transparent; color: var(--text); border: 1px solid var(--panel-border);
  }
  button.secondary:hover, .btn.secondary:hover { border-color: var(--accent); }
  button[disabled] { opacity: 0.4; cursor: not-allowed; filter: none; }

  .flash { background: #241b3d; border: 1px solid var(--accent); color: var(--text);
           padding: 12px 16px; border-radius: var(--radius); margin: 16px 0; font-size: 0.9rem; }
  .muted { color: var(--text-muted); font-size: 0.85rem; }

  video, img.preview { max-width: 100%; border-radius: var(--radius); background: #000;
                        border: 1px solid var(--panel-border); }
  .cols { display: flex; gap: 24px; flex-wrap: wrap; margin-top: 8px; }
  .cols > div { flex: 1 1 320px; }
  .script-box { white-space: pre-wrap; background: var(--panel); border: 1px solid var(--panel-border);
    border-radius: var(--radius); padding: 14px 16px; font-size: 0.88rem; max-height: 340px;
    overflow-y: auto; color: var(--text); }
  .panel { background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius);
           padding: 18px 20px; margin: 12px 0; }
  .panel.accent { border-left: 3px solid var(--accent); }
  .panel.warn { border-left: 3px solid var(--missing-fg); }
  hr.sep { border: none; border-top: 1px solid var(--panel-border); margin: 28px 0; }

  .video-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-top: 1rem; }
  .video-grid-item { cursor: pointer; background: var(--panel); border: 1px solid var(--panel-border);
    border-radius: var(--radius); overflow: hidden; transition: transform 0.15s, border-color 0.15s; }
  .video-grid-item:hover { transform: scale(1.02); border-color: var(--accent); }
  .video-grid-item img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
  .grid-thumb-placeholder { width: 100%; aspect-ratio: 16/9; display: flex; align-items: center;
    justify-content: center; color: var(--text-muted); background: var(--panel-hover); font-size: 0.8rem; text-align: center; padding: 8px; }
  .video-grid-caption { padding: 10px 12px; }
  .video-grid-title { font-weight: 600; font-size: 0.85rem; margin-bottom: 6px; line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 1000;
    align-items: center; justify-content: center; padding: 20px; }
  .modal-box { background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius);
    padding: 28px 24px 24px; max-width: 920px; width: 100%; max-height: 90vh; overflow-y: auto; position: relative; }
  .modal-close { position: absolute; top: 10px; right: 14px; background: none; border: none;
    color: var(--text); font-size: 1.4rem; cursor: pointer; line-height: 1; }
  .modal-box video { max-width: 100%; border-radius: 8px; background: #000; }
</style>
</head>
<body>
<h1>YouTube Content Creator</h1>
<nav>
  <a href="/" class="{{ 'active' if active_nav == 'channels' else '' }}">Canais e credenciais</a>
  <a href="/videos" class="{{ 'active' if active_nav == 'videos' else '' }}">Vídeos{{ ' (' + pending_count|string + ' p/ publicar no YouTube)' if pending_count else '' }}</a>
  <a href="/reports" class="{{ 'active' if active_nav == 'reports' else '' }}">📈 Relatório por série</a>
</nav>
{% with messages = get_flashed() %}
  {% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</body>
</html>
"""

_flash_messages: list[str] = []


def _flash(message: str) -> None:
    _flash_messages.append(message)


def get_flashed():
    messages = list(_flash_messages)
    _flash_messages.clear()
    return messages


def _render(body: str, active_nav: str = "channels"):
    try:
        pending_count = catalog.count_pending_review()
    except Exception:
        pending_count = 0
    return render_template_string(
        BASE_TEMPLATE, body=body, get_flashed=get_flashed, active_nav=active_nav, pending_count=pending_count
    )


def _is_valid_oauth_secret(slug: str) -> bool:
    path = channels.client_secret_path(slug)
    if not path.exists():
        return False
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return False
    return "installed" in parsed or "web" in parsed


def _channel_status_badges(channel) -> str:
    badges = []
    badges.append('<span class="badge ok">ativo</span>' if channel["active"] else '<span class="badge inactive">inativo</span>')
    has_key = channels.nasa_api_key_for(channel) != "DEMO_KEY"
    badges.append(f'<span class="badge {"ok" if has_key else "missing"}">chave NASA {"ok (compartilhada)" if has_key else "pendente (usa DEMO_KEY)"}</span>')
    has_secret = _is_valid_oauth_secret(channel["slug"])
    badges.append(f'<span class="badge {"ok" if has_secret else "missing"}">client_secret.json {"ok" if has_secret else "pendente/inválido"}</span>')
    return " ".join(badges)


def _connected_channel_cell(channel) -> str:
    if channel["connected_youtube_channel_title"]:
        thumb = (
            f'<img src="{channel["connected_youtube_channel_thumbnail"]}" style="width:24px; height:24px; border-radius:50%; vertical-align:middle; margin-right:6px;">'
            if channel["connected_youtube_channel_thumbnail"] else ""
        )
        return f'<span class="badge ok">{thumb}{channel["connected_youtube_channel_title"]}</span>'
    if channels.token_path(channel["slug"]).exists():
        return '<span class="badge missing">token salvo, identidade não confirmada - reautorize</span>'
    return '<span class="badge missing">nenhum canal conectado</span>'


@app.route("/")
def index():
    catalog.init_db()
    channels.ensure_default_channel()
    rows = channels.list_channels()

    # detecta 2+ canais do YouTube Content Creator apontando pro mesmo canal real do YouTube -
    # sinal claro de que a separação que o dono queria não deu certo
    connected_ids = [ch["connected_youtube_channel_id"] for ch in rows if ch["connected_youtube_channel_id"]]
    duplicated_ids = {cid for cid in connected_ids if connected_ids.count(cid) > 1}

    items = ""
    for ch in rows:
        row_warn = (
            ' style="border-left: 3px solid var(--missing-fg);"'
            if ch["connected_youtube_channel_id"] in duplicated_ids else ""
        )
        items += f"""
        <tr{row_warn}>
          <td><a href="{url_for('edit_channel', channel_id=ch['id'])}">{ch['name']}</a><br>
              <span class="muted">{ch['niche'] or ''}</span></td>
          <td>{_connected_channel_cell(ch)}</td>
          <td>{_channel_status_badges(ch)}</td>
          <td>
            <a class="btn secondary" href="{url_for('channel_studio', channel_id=ch['id'])}">🎬 Estúdio</a>
            <a class="btn secondary" href="{url_for('list_videos', channel_id=ch['id'])}">🎥 Vídeos</a>
            <a class="btn secondary" href="{url_for('weekly_report', channel_id=ch['id'])}">📈 Relatório</a>
          </td>
        </tr>
        """

    shared_key = channels.shared_nasa_api_key() or ""
    settings_panel = f"""
    <div class="panel accent">
      <h3 style="margin-top:0;">Chave da NASA API (compartilhada)</h3>
      <p class="muted">Uma chave só, usada por TODOS os canais - inclusive os que você ainda vai
      criar. Cadastre gratuitamente em <a href="https://api.nasa.gov/" target="_blank">api.nasa.gov</a>.
      Sem isso, todos os canais caem no DEMO_KEY (limite baixo, compartilhado com o mundo inteiro,
      não recomendado pra produção diária).</p>
      <form method="post" action="{url_for('save_shared_nasa_key')}">
        <input type="text" name="shared_nasa_api_key" value="{shared_key}" placeholder="sua chave gratuita de api.nasa.gov">
        <button type="submit">Salvar chave compartilhada</button>
      </form>
    </div>
    """

    body = settings_panel + f"""
    <p>
      <a class="btn" href="{url_for('new_channel')}">+ Novo canal</a>
      <a class="btn secondary" href="{url_for('run_health_check')}">🩺 Checar saúde dos canais agora</a>
    </p>
    <table>
      <tr><th>Canal</th><th>Conectado a (YouTube)</th><th>Status</th><th></th></tr>
      {items or '<tr><td colspan="4">Nenhum canal cadastrado ainda.</td></tr>'}
    </table>
    """
    return _render(body)


@app.route("/health_check")
def run_health_check():
    from pipeline import health
    try:
        warnings = health.check_channels_health()
    except Exception as exc:
        _flash(f"Checagem falhou: {exc}")
        return redirect(url_for("index"))

    if warnings:
        for w in warnings:
            _flash(f"⚠ {w}")
    else:
        _flash("Tudo certo - nenhuma queda de vídeo detectada nos canais autorizados.")
    return redirect(url_for("index"))


@app.route("/settings/shared_nasa_key", methods=["POST"])
def save_shared_nasa_key():
    value = request.form.get("shared_nasa_api_key", "").strip() or None
    channels.set_shared_nasa_api_key(value)
    _flash("Chave da NASA compartilhada atualizada - vale pra todos os canais, inclusive os futuros.")
    return redirect(url_for("index"))


KIT_FORM = """
<div class="panel accent">
  <h3 style="margin-top:0;">🪄 Kit de canal automático</h3>
  <p class="muted">Descreva o nicho e o Llama sugere 8-10 temas rotativos + nomes de série prontos -
  revise/edite antes de salvar. Precisa do Ollama rodando.</p>
  <form method="post" action="{{ url_for('generate_channel_kit_route') }}">
    <input type="text" name="kit_niche" value="{{ kit_niche or '' }}" placeholder="ex.: curiosidades de história antiga (Egito, Roma, Grécia)">
    <input type="hidden" name="language" value="{{ (ch.language if ch else default_language) }}">
    <button type="submit" class="secondary">Gerar sugestões</button>
  </form>
</div>
"""

CHANNEL_FORM = """
<h2>{{ title }}</h2>
<form method="post">
  <label>Nome do canal</label>
  <input type="text" name="name" value="{{ ch.name if ch else '' }}" {{ 'readonly' if ch else '' }} required>
  <label>Nicho / assunto (descrição livre, usado só como referência)</label>
  <input type="text" name="niche" value="{{ ch.niche if ch else (kit_niche or '') }}">
  <label>Temas rotativos (um por linha, formato: "rótulo | termo de busca em inglês")</label>
  <textarea name="topics" rows="8">{{ topics_text }}</textarea>
  <p class="muted">A chave da NASA API agora é compartilhada entre todos os canais - configure uma
  vez só no painel principal (<a href="/">Canais e credenciais</a>).</p>
  <label>Idioma do canal (roteiro, CTA de inscrição e legenda de crédito)</label>
  <select name="language">
    {% for code, lang in languages.items() %}
    <option value="{{ code }}" {{ 'selected' if (ch.language if ch else default_language) == code else '' }}>{{ lang.label }}</option>
    {% endfor %}
  </select>
  <label>Voz de narração (escolha uma do mesmo idioma selecionado acima)</label>
  <select name="narration_voice">
    {% for code, lang in languages.items() %}
      {% for key, voice in lang.voice_options.items() %}
      <option value="{{ voice }}" {{ 'selected' if ch and ch.narration_voice == voice else '' }}>[{{ code }}] {{ key }} ({{ voice }})</option>
      {% endfor %}
    {% endfor %}
  </select>
  <label>Selo de série - vídeos com fonte factual real do dia (ex.: APOD)</label>
  <input type="text" name="series_primary" value="{{ series_primary or (ch.series_primary if ch else '') }}">
  <label>Selo de série - vídeos de tema rotativo (sem fonte do dia)</label>
  <input type="text" name="series_fallback" value="{{ series_fallback or (ch.series_fallback if ch else '') }}">
  <button type="submit">Salvar</button>
</form>
"""


_pending_kit: dict | None = None


@app.route("/channels/new", methods=["GET", "POST"])
def new_channel():
    global _pending_kit
    import config
    if request.method == "POST":
        topics = _parse_topics(request.form.get("topics", ""))
        channel_id = channels.create_channel(
            name=request.form["name"].strip(),
            niche=request.form.get("niche", "").strip(),
            topics=topics or channels.DEFAULT_TOPICS,
            narration_voice=request.form.get("narration_voice") or None,
            language=request.form.get("language") or None,
            series_primary=request.form.get("series_primary", "").strip() or None,
            series_fallback=request.form.get("series_fallback", "").strip() or None,
        )
        _flash(f"Canal criado. Agora cadastre as credenciais do YouTube dele abaixo.")
        return redirect(url_for("edit_channel", channel_id=channel_id))

    kit = _pending_kit
    _pending_kit = None  # uso único - depois de mostrado na tela, não reaparece numa próxima visita solta

    if kit:
        topics_text = "\n".join(f"{label} | {query}" for label, query in kit["topics"])
        kit_body = render_template_string(KIT_FORM, ch=None, default_language=config.DEFAULT_LANGUAGE,
                                           kit_niche=kit.get("niche"))
        body = kit_body + render_template_string(
            CHANNEL_FORM, title="Novo canal", ch=None, topics_text=topics_text,
            languages=config.LANGUAGES, default_language=kit.get("language", config.DEFAULT_LANGUAGE),
            kit_niche=kit.get("niche"), series_primary=kit["series_primary"], series_fallback=kit["series_fallback"],
        )
        return _render(body)

    default_topics_text = "\n".join(f"{label} | {query}" for label, query in channels.DEFAULT_TOPICS)
    kit_body = render_template_string(KIT_FORM, ch=None, default_language=config.DEFAULT_LANGUAGE, kit_niche=None)
    body = kit_body + render_template_string(
        CHANNEL_FORM, title="Novo canal", ch=None, topics_text=default_topics_text,
        languages=config.LANGUAGES, default_language=config.DEFAULT_LANGUAGE,
        kit_niche=None, series_primary=None, series_fallback=None,
    )
    return _render(body)


@app.route("/channels/new/generate_kit", methods=["POST"])
def generate_channel_kit_route():
    global _pending_kit
    import config
    from pipeline import script_gen

    niche = request.form.get("kit_niche", "").strip()
    language = request.form.get("language") or config.DEFAULT_LANGUAGE
    if not niche:
        _flash("Descreva o nicho antes de gerar o kit.")
        return redirect(url_for("new_channel"))

    if not script_gen.ollama_available():
        _flash("Ollama não está respondendo - não dá pra gerar o kit automático agora (confira `ollama serve`).")
        return redirect(url_for("new_channel"))

    kit = script_gen.generate_channel_kit(niche, language)
    if not kit:
        _flash("O Llama não conseguiu gerar um kit válido dessa vez - tente descrever o nicho de outro jeito, ou preencha os temas na mão.")
        return redirect(url_for("new_channel"))

    kit["niche"] = niche
    kit["language"] = language
    _pending_kit = kit
    _flash(f"Kit gerado com {len(kit['topics'])} temas - revise abaixo antes de salvar.")
    return redirect(url_for("new_channel"))


def _parse_topics(raw: str) -> list[tuple[str, str]]:
    topics = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        label, query = line.split("|", 1)
        topics.append((label.strip(), query.strip()))
    return topics


CREDENTIALS_FORM = """
<h2>Conexão com o YouTube - {{ ch.name }}</h2>

{% if ch.connected_youtube_channel_title %}
<div class="panel accent" style="display:flex; align-items:center; gap:14px; flex-wrap:wrap;">
  {% if ch.connected_youtube_channel_thumbnail %}
  <img src="{{ ch.connected_youtube_channel_thumbnail }}" style="width:48px; height:48px; border-radius:50%;">
  {% endif %}
  <div style="flex:1; min-width:200px;">
    <div class="muted" style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em;">Conectado ao canal do YouTube</div>
    <div style="font-weight:700; font-size:1.1rem; font-family:'Space Grotesk',sans-serif;">{{ ch.connected_youtube_channel_title }}</div>
    <div class="muted" style="font-size:0.78rem;">ID: {{ ch.connected_youtube_channel_id }}</div>
  </div>
  <form method="post" action="{{ url_for('reconnect_channel', channel_id=ch.id) }}" style="margin:0;"
        onsubmit="return confirm('Isso desconecta o canal atual e abre o navegador de novo, forçando o Google a mostrar a tela de escolha de conta/canal. Continuar?');">
    <button type="submit" class="secondary">🔄 Desconectar e conectar outro canal</button>
  </form>
</div>
{% if duplicate_warning %}
<div class="panel warn">⚠ {{ duplicate_warning }}</div>
{% endif %}
{% else %}
<div class="panel warn">Nenhum canal do YouTube conectado ainda neste perfil.</div>
{% endif %}

<p class="muted">
  1. Crie um projeto no <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Console</a>,
  ative a "YouTube Data API v3".<br>
  2. Em "Tela de consentimento OAuth" → "Dados de acesso"/"Scopes", clique em "Adicionar ou remover
  escopos" e adicione o escopo <code>https://www.googleapis.com/auth/youtube</code> (não só o
  "youtube.upload") - sem isso cadastrado ali, o Google concede um acesso mais restrito mesmo que o
  app peça o escopo certo, e listar/excluir vídeos do canal falha com "insufficient scopes".<br>
  3. Gere credenciais OAuth2 do tipo "Desktop app" e baixe o client_secret.json.<br>
  4. IMPORTANTE: deixe o app OAuth em modo "In production" (não "Testing"), senão o acesso expira em 7 dias.<br>
  5. Cole o conteúdo do arquivo client_secret.json abaixo.
</p>
<form method="post" action="{{ url_for('save_client_secret', channel_id=ch.id) }}">
  <label>Conteúdo do client_secret.json</label>
  <textarea name="client_secret_json" rows="8" placeholder='{"installed": {"client_id": "...", ...}}'>{{ existing_secret }}</textarea>
  <button type="submit">Salvar credenciais</button>
</form>

<div class="panel warn">
  <b>Quer conectar um canal DIFERENTE do seu canal pessoal do YouTube?</b>
  <p class="muted" style="margin:6px 0 0;">
  Crie antes um "Brand Account" dedicado em
  <a href="https://www.youtube.com/create_channel" target="_blank">youtube.com/create_channel</a>
  (não é o mesmo que seu canal pessoal). Quando clicar em "Autorizar" abaixo, o navegador vai abrir e,
  depois de você logar, o Google mostra uma tela pra ESCOLHER qual canal/conta usar - procure
  explicitamente o Brand Account que você quer usar aqui e clique nele, em vez de aceitar o canal
  pessoal que costuma vir em destaque. Depois de autorizar, confira o card acima: ele mostra o nome
  real do canal que ficou conectado - se estiver errado, use "Desconectar e conectar outro canal".</p>
</div>

<form method="post" action="{{ url_for('authorize_channel', channel_id=ch.id) }}">
  <button type="submit" class="secondary" {{ 'disabled' if not has_secret else '' }}>
    {{ 'Reautorizar' if ch.connected_youtube_channel_title else 'Autorizar no YouTube (abre o navegador)' }}
  </button>
  <a class="btn secondary" href="{{ url_for('youtube_channel_videos', channel_id=ch.id) }}">Ver vídeos reais do canal no YouTube</a>
  <a class="btn secondary" href="{{ url_for('channel_dashboard', channel_id=ch.id) }}">📊 Painel de métricas</a>
</form>
<p class="muted">{{ authorize_status }}</p>
"""


@app.route("/channels/<int:channel_id>/edit", methods=["GET", "POST"])
def edit_channel(channel_id: int):
    import config
    ch = channels.get_channel(channel_id)
    if request.method == "POST":
        topics = _parse_topics(request.form.get("topics", ""))
        language = request.form.get("language")
        channels.update_channel(
            channel_id,
            niche=request.form.get("niche", "").strip(),
            topics=topics or channels.DEFAULT_TOPICS,
            narration_voice=request.form.get("narration_voice") or None,
            language=language if language in config.LANGUAGES else channels.get_channel(channel_id)["language"],
            series_primary=request.form.get("series_primary", "").strip() or ch["series_primary"],
            series_fallback=request.form.get("series_fallback", "").strip() or ch["series_fallback"],
        )
        _flash("Canal atualizado.")
        return redirect(url_for("edit_channel", channel_id=channel_id))

    studio_cta = f"""
    <p>
      <a class="btn" href="{url_for('channel_studio', channel_id=channel_id)}">🎬 Gerar vídeo agora / pedir tema</a>
      <a class="btn secondary" href="{url_for('list_videos', channel_id=channel_id)}">🎥 Vídeos deste canal</a>
      <a class="btn secondary" href="{url_for('weekly_report', channel_id=channel_id)}">📈 Relatório deste canal</a>
      <a class="btn secondary" href="{url_for('channel_comments', channel_id=channel_id)}">💬 Comentários</a>
    </p>
    """

    topics_text = "\n".join(f"{label} | {query}" for label, query in channels.topics_for(ch))
    form_body = studio_cta + render_template_string(
        CHANNEL_FORM, title=f"Editar canal: {ch['name']}", ch=ch, topics_text=topics_text,
        languages=config.LANGUAGES, default_language=config.DEFAULT_LANGUAGE,
    )

    secret_path = channels.client_secret_path(ch["slug"])
    existing_secret = secret_path.read_text(encoding="utf-8") if secret_path.exists() else ""

    duplicate_warning = None
    if ch["connected_youtube_channel_id"]:
        others = [
            other["name"] for other in channels.list_channels()
            if other["id"] != channel_id and other["connected_youtube_channel_id"] == ch["connected_youtube_channel_id"]
        ]
        if others:
            duplicate_warning = (
                f"Este mesmo canal do YouTube também está conectado a: {', '.join(others)}. "
                "Se a intenção era ter canais SEPARADOS, um deles está apontando pro canal errado."
            )

    creds_body = render_template_string(
        CREDENTIALS_FORM, ch=ch, existing_secret=existing_secret,
        has_secret=_is_valid_oauth_secret(ch["slug"]),
        authorize_status=_authorize_status.get(channel_id, ""),
        duplicate_warning=duplicate_warning,
    )

    toggle_label = "Desativar canal" if ch["active"] else "Ativar canal"
    delete_section = f"""
    <div class="panel warn">
      <h3 style="margin-top:0; color: var(--missing-fg);">Excluir canal</h3>
      <p class="muted">Remove o canal do YouTube Content Creator (configuração + arquivos locais). Vídeos já
      publicados no YouTube NÃO são apagados por isso - exclua-os pela aba "Vídeos gerados" ou
      diretamente no YouTube, se quiser, antes de excluir o canal aqui.</p>
      <form method="post" action="{url_for('delete_channel_route', channel_id=channel_id)}"
            onsubmit="return confirm('Excluir o canal \\'{ch['name']}\\' do YouTube Content Creator? Isso apaga a configuração e os arquivos locais (vídeos/áudio/credenciais salvas aqui). Vídeos já publicados no YouTube continuam lá. Essa ação não pode ser desfeita.');">
        <button type="submit" class="secondary">Excluir canal "{ch['name']}"</button>
      </form>
    </div>
    """
    body = form_body + creds_body + f"""
    <form method="post" action="{url_for('toggle_active', channel_id=channel_id)}">
      <button type="submit" class="secondary">{toggle_label}</button>
    </form>
    {delete_section}
    <p><a href="{url_for('index')}">&larr; Voltar</a></p>
    """
    return _render(body)


@app.route("/channels/<int:channel_id>/client_secret", methods=["POST"])
def save_client_secret(channel_id: int):
    ch = channels.get_channel(channel_id)
    raw = request.form.get("client_secret_json", "").strip()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _flash("JSON inválido - confira se colou o conteúdo completo do client_secret.json.")
        return redirect(url_for("edit_channel", channel_id=channel_id))

    if parsed.get("type") == "service_account":
        _flash(
            "Esse JSON é de uma CONTA DE SERVIÇO (Service Account), não serve pra isso. "
            "No Google Cloud Console, vá em 'APIs e serviços' → 'Credenciais' → 'Criar credenciais' → "
            "'ID do cliente OAuth' → tipo de aplicativo 'Aplicativo para computador' (Desktop app), e baixe "
            "o JSON gerado ali - ele deve ter uma chave \"installed\" ou \"web\" no topo, não \"type\": \"service_account\"."
        )
        return redirect(url_for("edit_channel", channel_id=channel_id))

    if "installed" not in parsed and "web" not in parsed:
        _flash(
            "Esse JSON não parece ser um client_secret.json de OAuth 'Desktop app' válido "
            "(esperava uma chave \"installed\" ou \"web\" no topo). Confira se baixou o arquivo certo."
        )
        return redirect(url_for("edit_channel", channel_id=channel_id))

    channels.client_secret_path(ch["slug"]).write_text(raw, encoding="utf-8")
    _flash("Credenciais salvas. Agora clique em 'Autorizar no YouTube'.")
    return redirect(url_for("edit_channel", channel_id=channel_id))


def _run_authorization(channel_id: int, force_new: bool) -> None:
    ch = channels.get_channel(channel_id)
    try:
        _authorize_status[channel_id] = "Aguardando login no navegador..."
        info = youtube_upload.authorize_and_identify(
            channels.client_secret_path(ch["slug"]), channels.token_path(ch["slug"]), force_new=force_new
        )
        if info:
            channels.set_connected_channel_info(channel_id, info)
            _authorize_status[channel_id] = f"Autorizado com sucesso - conectado ao canal \"{info['title']}\"."
        else:
            _authorize_status[channel_id] = (
                "Autorizado, mas a conta escolhida não tem nenhum canal do YouTube criado ainda "
                "- crie um em youtube.com/create_channel e reautorize."
            )
    except Exception as exc:
        _authorize_status[channel_id] = f"Falhou: {exc}"


@app.route("/channels/<int:channel_id>/authorize", methods=["POST"])
def authorize_channel(channel_id: int):
    threading.Thread(target=_run_authorization, args=(channel_id, False), daemon=True).start()
    _flash(
        "Autorização iniciada - uma janela do navegador deve abrir. Se a conta gerenciar mais de um "
        "canal, o Google vai perguntar QUAL usar - escolha com atenção. Atualize a página em alguns segundos."
    )
    return redirect(url_for("edit_channel", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/reconnect", methods=["POST"])
def reconnect_channel(channel_id: int):
    channels.disconnect_channel(channel_id)
    threading.Thread(target=_run_authorization, args=(channel_id, True), daemon=True).start()
    _flash(
        "Desconectado. Nova autorização iniciada com a tela de escolha de conta/canal forçada a "
        "aparecer de novo - escolha o canal certo no navegador que abrir."
    )
    return redirect(url_for("edit_channel", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/toggle_active", methods=["POST"])
def toggle_active(channel_id: int):
    ch = channels.get_channel(channel_id)
    channels.update_channel(channel_id, active=0 if ch["active"] else 1)
    return redirect(url_for("edit_channel", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/delete", methods=["POST"])
def delete_channel_route(channel_id: int):
    ch = channels.get_channel(channel_id)
    name = ch["name"]
    channels.delete_channel(channel_id, delete_local_files=True)
    _flash(f"Canal \"{name}\" excluído do YouTube Content Creator (configuração + arquivos locais). "
           "Vídeos já publicados no YouTube, se houver, continuam lá.")
    return redirect(url_for("index"))


_QUEUE_STATUS_LABELS = {
    "pending": "na fila",
    "running": "gerando agora",
    "done": "pronto",
    "failed": "falhou",
}
_QUEUE_STATUS_CLASS = {"pending": "inactive", "running": "missing", "done": "ok", "failed": "missing"}


def _video_grid_html(channel_id: int) -> str:
    tracks = catalog.list_tracks(channel_id=channel_id, limit=100)

    cards = ""
    modals = ""
    for t in tracks:
        has_thumb = bool(t["thumbnail_path"]) and Path(t["thumbnail_path"]).exists()
        thumb_html = (
            f'<img src="{url_for("track_file", track_id=t["id"], kind="thumbnail")}" loading="lazy">'
            if has_thumb else '<div class="grid-thumb-placeholder">⏳ gerando...</div>'
        )
        cards += f"""
        <div class="video-grid-item" onclick="openVideoModal({t['id']})">
          {thumb_html}
          <div class="video-grid-caption">
            <div class="video-grid-title">{t['title']}</div>
            {_status_badge(t['status'])} {_fact_check_badge(t['fact_check_flag'])} {_quality_badge(t)}
          </div>
        </div>
        """

        has_video = bool(t["video_path"]) and Path(t["video_path"]).exists()
        has_short = bool(t["video_vertical_path"]) and Path(t["video_vertical_path"]).exists()
        video_html = (
            f'<video controls preload="none" src="{url_for("track_file", track_id=t["id"], kind="video")}"></video>'
            if has_video else '<p class="muted">Vídeo horizontal ainda não montado.</p>'
        )
        short_html = (
            f'<video controls preload="none" src="{url_for("track_file", track_id=t["id"], kind="short")}" style="max-width:240px;"></video>'
            if has_short else ''
        )

        modal_actions = ""
        if t["status"] == "pending_review":
            modal_actions += f"""
            <form class="inline" method="post" action="{url_for('approve_video', track_id=t['id'])}" style="display:inline-flex; align-items:center;">
              <button type="submit">📤 Publicar no YouTube</button>
              {_privacy_select(f'modal_privacy_video_{t["id"]}')}
            </form>
            <form class="inline" method="post" action="{url_for('reject_video', track_id=t['id'])}">
              <button type="submit" class="secondary">Rejeitar</button>
            </form>
            """
        if has_short and not t["youtube_short_video_id"] and t["status"] in ("pending_review", "video_ready", "uploaded"):
            modal_actions += f"""
            <form class="inline" method="post" action="{url_for('approve_short', track_id=t['id'])}" style="display:inline-flex; align-items:center;">
              <button type="submit" class="secondary">📤 Publicar Short no YouTube</button>
              {_privacy_select(f'modal_privacy_short_{t["id"]}')}
            </form>
            """

        modals += f"""
        <div id="video-modal-src-{t['id']}" style="display:none;">
          <h3 style="margin-top:0;">{t['title']}</h3>
          <p>{_status_badge(t['status'])} {_fact_check_badge(t['fact_check_flag'])} {_quality_badge(t)}
             {f'<span class="badge inactive">série: {t["series"]}</span>' if t['series'] else ''}</p>
          <div class="cols">
            <div style="flex:2;">{video_html}</div>
            <div style="flex:1;">{short_html}</div>
          </div>
          <p style="margin-top:14px;">{modal_actions}</p>
          <p class="muted">{t['script'][:300]}...</p>
          <p><a href="{url_for('video_detail', track_id=t['id'])}">Ver página completa (roteiro inteiro, descrição, tags, avaliação)</a></p>
        </div>
        """

    grid = f'<div class="video-grid">{cards}</div>' if cards else '<p class="muted">Nenhum vídeo gerado ainda pra este canal.</p>'

    modal_shell = f"""
    <div id="video-modal-overlay" class="modal-overlay" onclick="if(event.target===this) closeVideoModal()">
      <div class="modal-box">
        <button class="modal-close" onclick="closeVideoModal()">✕</button>
        <div id="video-modal-body"></div>
      </div>
    </div>
    {modals}
    <script>
    function openVideoModal(id) {{
      document.getElementById('video-modal-body').innerHTML = document.getElementById('video-modal-src-' + id).innerHTML;
      document.getElementById('video-modal-overlay').style.display = 'flex';
    }}
    function closeVideoModal() {{
      document.getElementById('video-modal-overlay').style.display = 'none';
      document.getElementById('video-modal-body').innerHTML = '';
    }}
    </script>
    """
    return grid + modal_shell


@app.route("/channels/<int:channel_id>/studio")
def channel_studio(channel_id: int):
    ch = channels.get_channel(channel_id)
    tab = request.args.get("tab", "studio")

    tab_nav = f"""
    <nav style="margin-bottom:1.5rem;">
      <a href="{url_for('channel_studio', channel_id=channel_id, tab='studio')}" class="{'active' if tab == 'studio' else ''}">🎬 Estúdio</a>
      <a href="{url_for('channel_studio', channel_id=channel_id, tab='videos')}" class="{'active' if tab == 'videos' else ''}">🎥 Vídeos gerados</a>
    </nav>
    """

    if tab == "videos":
        body = f"""
        <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar pro canal</a></p>
        <h2>🎥 Vídeos gerados - {ch['name']}</h2>
        {tab_nav}
        <p class="muted">Clique numa miniatura pra assistir e decidir se aprova a postagem, sem sair
        desta página.</p>
        {_video_grid_html(channel_id)}
        """
        return _render(body, active_nav="videos")

    suggestions = catalog.get_suggested_topics(channel_id)
    suggestion_checkboxes = ""
    for i, (label, query) in enumerate(suggestions):
        suggestion_checkboxes += f"""
        <label style="display:flex; align-items:center; gap:10px; font-weight:400; margin-top:8px;">
          <input type="checkbox" name="selected" value="{i}" style="width:auto;">
          <span><b>{label}</b> <span class="muted">({query})</span></span>
        </label>
        """

    suggestions_block = ""
    if suggestions:
        suggestions_block = f"""
        <form method="post" action="{url_for('queue_topics_route', channel_id=channel_id)}">
          {suggestion_checkboxes}
          <button type="submit" class="secondary" style="margin-top:14px;">Adicionar selecionados à fila</button>
        </form>
        """
    else:
        suggestions_block = '<p class="muted">Nenhuma sugestão ainda - clique em "Sugerir temas novos".</p>'

    queue_items = catalog.list_queue_items(channel_id=channel_id, limit=20)
    queue_rows = ""
    for item in queue_items:
        cls = _QUEUE_STATUS_CLASS.get(item["status"], "inactive")
        label = _QUEUE_STATUS_LABELS.get(item["status"], item["status"])
        extra = ""
        if item["status"] == "done" and item["track_id"]:
            extra = f' - <a href="{url_for("video_detail", track_id=item["track_id"])}">ver vídeo</a>'
        elif item["status"] == "failed" and item["error"]:
            extra = f' - <span class="muted">{item["error"][:120]}</span>'
        cancel_btn = ""
        if item["status"] == "pending":
            cancel_btn = f"""
            <form class="inline" method="post" action="{url_for('cancel_queue_item_route', item_id=item['id'])}" style="margin-left:8px;">
              <button type="submit" class="secondary" style="margin:0; padding:2px 10px; font-size:0.78rem;">Cancelar</button>
            </form>
            """
        queue_rows += f"""
        <tr>
          <td>{item['topic_label']}</td>
          <td><span class="badge {cls}">{label}</span>{extra}</td>
          <td>{cancel_btn}</td>
        </tr>
        """
    queue_block = ""
    if queue_items:
        queue_block = f"""
        <h3>Fila deste canal</h3>
        <table>
          <tr><th>Tema</th><th>Status</th><th></th></tr>
          {queue_rows}
        </table>
        """

    status = _generation_status.get(channel_id, "")

    best_day_note = ""
    try:
        from pipeline import reports
        best_day = reports.best_publish_weekday(channel_id)
        if best_day:
            best_day_note = (
                f'<div class="panel accent"><p class="muted">📅 Baseado no histórico real deste canal, '
                f'<b>{best_day}</b> costuma render mais views - considere publicar os aprovados nesse '
                f"dia (informativo, não é regra).</p></div>"
            )
    except Exception:
        pass

    language = channels.language_for(ch)
    current_voice = channels.narration_voice_for(ch)
    voice_options_html = "".join(
        f'<option value="{voice}" {"selected" if voice == current_voice else ""}>{key} ({voice})</option>'
        for key, voice in language["voice_options"].items()
    )
    voice_panel = f"""
    <div class="panel">
      <h3 style="margin-top:0;">🎙 Voz da narração</h3>
      <p class="muted">Escolha e ouça a prévia antes de decidir - muda a voz usada em TODOS os próximos
      vídeos deste canal (não afeta vídeos já gerados).</p>
      <form method="post" action="{url_for('update_channel_voice', channel_id=channel_id)}"
            style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <select name="narration_voice" id="voice-select"
                onchange="document.getElementById('voice-audio').src = '/voice_preview/' + this.value + '.mp3'">
          {voice_options_html}
        </select>
        <audio id="voice-audio" controls preload="none" src="/voice_preview/{current_voice}.mp3"></audio>
        <button type="submit" class="secondary">Salvar como voz do canal</button>
      </form>
    </div>
    """

    body = f"""
    <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar pro canal</a></p>
    <h2>🎬 Estúdio de geração - {ch['name']}</h2>
    {tab_nav}
    <p class="muted">Gera vídeo fora do agendamento diário. Cada um leva alguns minutos (roteiro,
    imagens, narração, dois vídeos montados); itens na fila são processados 1 de cada vez, em segundo
    plano. Tudo cai em "Vídeos gerados" com status "aguardando revisão" - nada é publicado sozinho.</p>

    {best_day_note}
    {voice_panel}

    <div class="panel accent">
      <h3 style="margin-top:0;">Tema automático</h3>
      <p class="muted">Mesma lógica do agendamento diário: tenta a NASA APOD do dia, senão sorteia um
      tema da lista rotativa do canal (evitando repetir os últimos usados).</p>
      <form method="post" action="{url_for('generate_video_route', channel_id=channel_id)}">
        <button type="submit">Gerar vídeo agora (tema automático)</button>
      </form>
    </div>

    <div class="panel accent">
      <h3 style="margin-top:0;">💡 Sugestões de tema</h3>
      <p class="muted">O Llama sugere temas alinhados ao nicho do canal - pode ser uma variação mais
      específica dos temas que já existem, ou um assunto adjacente novo, desde que combine com a
      proposta do canal. Evita repetir o que já foi narrado recentemente. As sugestões ficam salvas
      aqui até você pedir novas - marque quantas quiser e adicione todas à fila de uma vez.</p>
      <form method="post" action="{url_for('suggest_topics_route', channel_id=channel_id)}">
        <button type="submit" class="secondary">Sugerir temas novos</button>
      </form>
      {suggestions_block}
    </div>

    <div class="panel">
      <h3 style="margin-top:0;">Ou peça um tema específico</h3>
      <form method="post" action="{url_for('generate_video_route', channel_id=channel_id)}">
        <label>Título/rótulo do tema</label>
        <input type="text" name="topic_label" placeholder="ex.: A lua de Saturno com oceano por baixo do gelo">
        <label>Termo de busca em inglês (pra achar imagens da NASA/ESA relacionadas)</label>
        <input type="text" name="topic_query" placeholder="ex.: Enceladus ice ocean">
        <button type="submit" class="secondary">Gerar vídeo com este tema</button>
      </form>
    </div>

    {queue_block}
    <p class="muted">{status}</p>
    """
    return _render(body, active_nav="videos")


@app.route("/channels/<int:channel_id>/suggest_topics", methods=["POST"])
def suggest_topics_route(channel_id: int):
    from pipeline import script_gen

    ch = channels.get_channel(channel_id)
    if not script_gen.ollama_available():
        _flash("Ollama não está respondendo - não dá pra sugerir temas agora (confira `ollama serve`).")
        return redirect(url_for("channel_studio", channel_id=channel_id))

    suggestions = script_gen.suggest_topics(ch, count=8)
    if not suggestions:
        _flash("O Llama não conseguiu sugerir temas dessa vez - as sugestões anteriores (se houver) continuam salvas.")
    else:
        catalog.save_suggested_topics(channel_id, suggestions)
        _flash(f"{len(suggestions)} sugestões geradas e salvas - marque as que quiser e adicione à fila.")
    return redirect(url_for("channel_studio", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/queue_topics", methods=["POST"])
def queue_topics_route(channel_id: int):
    from pipeline import queue_worker

    suggestions = catalog.get_suggested_topics(channel_id)
    selected_indices = {int(i) for i in request.form.getlist("selected") if i.isdigit()}
    chosen = [t for i, t in enumerate(suggestions) if i in selected_indices]

    if not chosen:
        _flash("Marque pelo menos uma sugestão antes de adicionar à fila.")
        return redirect(url_for("channel_studio", channel_id=channel_id))

    catalog.enqueue_topics(channel_id, chosen)
    queue_worker.ensure_worker_started()
    _flash(f"{len(chosen)} vídeo(s) adicionado(s) à fila - serão gerados 1 de cada vez em segundo plano.")
    return redirect(url_for("channel_studio", channel_id=channel_id))


@app.route("/queue/<int:item_id>/cancel", methods=["POST"])
def cancel_queue_item_route(item_id: int):
    catalog.delete_queue_item(item_id)
    _flash("Item removido da fila (só funciona pra itens que ainda não começaram a gerar).")
    return redirect(request.referrer or url_for("index"))


def _run_generation(channel_id: int, forced_topic: tuple[str, str] | None) -> None:
    channel = channels.get_channel(channel_id)
    try:
        _generation_status[channel_id] = "Gerando... (roteiro, imagens, narração e dois vídeos - alguns minutos)"
        track_id = orchestrator.prepare_daily_video(channel_id, forced_topic=forced_topic)
        _generation_status[channel_id] = f"Pronto! Track {track_id} está em 'Vídeos gerados', aguardando sua revisão."
        notify.notify_result(True, f"[{channel['name']}] Vídeo sob demanda pronto (track {track_id}).")
    except Exception as exc:
        _generation_status[channel_id] = f"Falhou: {exc}"
        notify.notify_result(False, f"[{channel['name']}] Geração sob demanda falhou: {exc}")


@app.route("/channels/<int:channel_id>/generate", methods=["POST"])
def generate_video_route(channel_id: int):
    label = request.form.get("topic_label", "").strip()
    query = request.form.get("topic_query", "").strip()
    forced_topic = (label, query) if label and query else None

    if request.form.get("topic_label") and not forced_topic:
        _flash("Preencha os dois campos (rótulo e termo de busca) pra pedir um tema específico, ou deixe os dois em branco pro tema automático.")
        return redirect(url_for("channel_studio", channel_id=channel_id))

    threading.Thread(target=_run_generation, args=(channel_id, forced_topic), daemon=True).start()
    _flash("Geração iniciada em segundo plano - acompanhe o status logo abaixo (atualize a página).")
    return redirect(url_for("channel_studio", channel_id=channel_id))


def _scope_error_body(channel_id: int, exc: Exception) -> str:
    scope_hint = ""
    if "insufficient" in str(exc).lower() or "scope" in str(exc).lower():
        scope_hint = """
        <p>Isso costuma acontecer quando o escopo necessário (<code>youtube</code> ou
        <code>yt-analytics.readonly</code>) não está cadastrado na <b>Tela de consentimento OAuth</b>
        do projeto no Google Cloud Console (Google concede só um acesso restrito mesmo que o app peça
        o escopo certo, se ele não estiver na lista de escopos permitidos daquele projeto). Adicione o
        escopo lá ("Tela de consentimento OAuth" → "Escopos" → "Adicionar ou remover escopos"), depois
        reautorize abaixo.</p>
        """
    return f"""
    <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar</a></p>
    <div class="panel warn">
      Não foi possível consultar o YouTube: {exc}
      {scope_hint}
      <form method="post" action="{url_for('authorize_channel', channel_id=channel_id)}">
        <button type="submit" class="secondary">Reautorizar no YouTube</button>
      </form>
    </div>
    """


@app.route("/channels/<int:channel_id>/youtube_videos")
def youtube_channel_videos(channel_id: int):
    ch = channels.get_channel(channel_id)
    secret_path = channels.client_secret_path(ch["slug"])
    token_path = channels.token_path(ch["slug"])

    if not token_path.exists():
        body = f"""
        <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar</a></p>
        <div class="panel warn">Este canal ainda não foi autorizado no YouTube - clique em
        "Autorizar no YouTube" na página do canal primeiro.</div>
        """
        return _render(body)

    try:
        info = youtube_upload.get_channel_info(secret_path, token_path)
        videos = youtube_upload.list_channel_videos(secret_path, token_path)
    except Exception as exc:
        return _render(_scope_error_body(channel_id, exc))

    if not info:
        body = f"""
        <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar</a></p>
        <div class="panel warn">
          A conta do Google autorizada não tem nenhum canal do YouTube criado ainda. Este app NÃO
          cria canal - ele só publica no canal já existente da conta autorizada. Crie um canal em
          <a href="https://www.youtube.com/create_channel" target="_blank">youtube.com/create_channel</a>
          com essa conta e depois autorize de novo.
        </div>
        """
        return _render(body)

    rows = ""
    for v in videos:
        rows += f"""
        <tr>
          <td><img src="{v['thumbnail_url']}" style="width:80px; border-radius:6px;" loading="lazy"></td>
          <td>
            <a href="https://youtube.com/watch?v={v['video_id']}" target="_blank">{v['title']}</a><br>
            <span class="muted">{v['published_at'][:10]}</span>
          </td>
          <td>
            <form method="post" action="{url_for('delete_remote_video_direct', channel_id=channel_id, video_id=v['video_id'])}"
                  onsubmit="return confirm('Excluir este vídeo diretamente do YouTube? Isso não pode ser desfeito.');">
              <button type="submit" class="secondary">Excluir do YouTube</button>
            </form>
          </td>
        </tr>
        """

    body = f"""
    <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar</a></p>
    <h2>Canal no YouTube: {info['title']}</h2>
    <p class="muted">ID: {info['id']}</p>
    <p>
      <span class="badge inactive">{info.get('subscriber_count', '?')} inscritos</span>
      <span class="badge inactive">{info.get('video_count', '?')} vídeos</span>
      <span class="badge inactive">{info.get('view_count', '?')} visualizações</span>
    </p>
    <table>
      <tr><th></th><th>Vídeo</th><th></th></tr>
      {rows or '<tr><td colspan="3">Nenhum vídeo encontrado nesse canal.</td></tr>'}
    </table>
    """
    return _render(body)


def _format_metric(key: str, value) -> str:
    if value is None:
        return "-"
    if key == "averageViewDuration":
        m, s = divmod(int(value), 60)
        return f"{m}m{s:02d}s"
    if key == "averageViewPercentage":
        return f"{value:.1f}%"
    if key == "estimatedMinutesWatched":
        return f"{int(value):,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.1f}"
    return f"{value:,}".replace(",", ".") if isinstance(value, int) else str(value)


@app.route("/channels/<int:channel_id>/comments")
def channel_comments(channel_id: int):
    ch = channels.get_channel(channel_id)
    secret_path = channels.client_secret_path(ch["slug"])
    token_path = channels.token_path(ch["slug"])

    if not token_path.exists():
        body = f"""
        <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar pro canal</a></p>
        <div class="panel warn">Canal ainda não autorizado no YouTube - autorize antes de ver comentários.</div>
        """
        return _render(body)

    try:
        comments = youtube_upload.list_recent_comments(secret_path, token_path, max_results=30)
    except Exception as exc:
        return _render(_scope_error_body(channel_id, exc))

    if not comments:
        rows_html = '<p class="muted">Nenhum comentário encontrado (ou comentários desativados nos vídeos deste canal).</p>'
    else:
        duplicate_ids = spam_detection.flag_duplicates(comments)
        scored = []
        for c in comments:
            score, reasons = spam_detection.spam_score(c["text"], c["author"])
            if c["id"] in duplicate_ids:
                score = min(score + 20, 100)
                reasons.append("mesma mensagem repetida em outro vídeo")
            scored.append((c, score, reasons))
        scored.sort(key=lambda item: item[1], reverse=True)  # mais suspeitos primeiro

        rows_html = ""
        for c, score, reasons in scored:
            suggestion = _comment_suggestions.get(c["id"], "")
            reply_disabled = "" if c["can_reply"] else "disabled"
            spam_badge = ""
            spam_actions = ""
            if score >= 40:
                spam_badge = f'<span class="badge missing">⚠ spam provável ({score}/100: {", ".join(reasons)})</span>'
                spam_actions = f"""
                <form class="inline" method="post" action="{url_for('moderate_comment_route', channel_id=channel_id, comment_id=c['id'])}">
                  <input type="hidden" name="status" value="rejected">
                  <button type="submit" class="secondary">🚫 Ocultar (spam)</button>
                </form>
                """
            rows_html += f"""
            <div class="panel" style="margin-bottom:12px;">
              <p><b>{c['author']}</b> <span class="muted">({c['published_at'][:10]})</span>
              {f'<span class="badge inactive">{c["reply_count"]} resposta(s)</span>' if c['reply_count'] else ''}
              {spam_badge}</p>
              <p>{c['text']}</p>
              {spam_actions}
              <form method="post" action="{url_for('suggest_comment_reply_route', channel_id=channel_id, comment_id=c['id'])}" class="inline">
                <input type="hidden" name="comment_text" value="{c['text'].replace(chr(34), '&quot;')}">
                <button type="submit" class="secondary">💬 Sugerir resposta com IA</button>
              </form>
              <form method="post" action="{url_for('reply_comment_route', channel_id=channel_id, comment_id=c['id'])}" style="margin-top:8px;">
                <textarea name="reply_text" rows="2" placeholder="Escreva ou peça uma sugestão acima">{suggestion}</textarea>
                <button type="submit" {reply_disabled}>Responder no YouTube</button>
              </form>
            </div>
            """

    body = f"""
    <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar pro canal</a></p>
    <h2>💬 Comentários - {ch['name']}</h2>
    <p class="muted">Comentários recentes de qualquer vídeo do canal, comentários mais suspeitos de spam
    primeiro. A sugestão de resposta e a detecção de spam são só sugestões - nada é publicado/ocultado
    sem você clicar explicitamente.</p>
    {rows_html}
    """
    return _render(body)


@app.route("/channels/<int:channel_id>/comments/<comment_id>/suggest", methods=["POST"])
def suggest_comment_reply_route(channel_id: int, comment_id: str):
    from pipeline import script_gen
    ch = channels.get_channel(channel_id)
    comment_text = request.form.get("comment_text", "")
    language = channels.language_for(ch)
    suggestion = script_gen.suggest_comment_reply(comment_text, ch["niche"] or "ciência", language["llm_language_name"])
    _comment_suggestions[comment_id] = suggestion or ""
    if not suggestion:
        _flash("O Llama não respondeu - escreva a resposta na mão.")
    return redirect(url_for("channel_comments", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/comments/<comment_id>/reply", methods=["POST"])
def reply_comment_route(channel_id: int, comment_id: str):
    ch = channels.get_channel(channel_id)
    text = request.form.get("reply_text", "").strip()
    if not text:
        _flash("Escreva algo antes de responder.")
        return redirect(url_for("channel_comments", channel_id=channel_id))
    try:
        youtube_upload.reply_to_comment(
            comment_id, text, channels.client_secret_path(ch["slug"]), channels.token_path(ch["slug"])
        )
        _comment_suggestions.pop(comment_id, None)
        _flash("Resposta publicada no YouTube.")
    except Exception as exc:
        _flash(f"Falha ao publicar resposta: {exc}")
    return redirect(url_for("channel_comments", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/comments/<comment_id>/moderate", methods=["POST"])
def moderate_comment_route(channel_id: int, comment_id: str):
    ch = channels.get_channel(channel_id)
    status = request.form.get("status", "rejected")
    try:
        youtube_upload.set_comment_moderation_status(
            comment_id, status, channels.client_secret_path(ch["slug"]), channels.token_path(ch["slug"])
        )
        _flash("Comentário ocultado no YouTube.")
    except Exception as exc:
        _flash(f"Falha ao moderar comentário: {exc}")
    return redirect(url_for("channel_comments", channel_id=channel_id))


@app.route("/channels/<int:channel_id>/dashboard")
def channel_dashboard(channel_id: int):
    ch = channels.get_channel(channel_id)
    secret_path = channels.client_secret_path(ch["slug"])
    token_path = channels.token_path(ch["slug"])
    days = request.args.get("days", default=28, type=int)

    if not token_path.exists():
        body = f"""
        <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar</a></p>
        <div class="panel warn">Este canal ainda não foi autorizado no YouTube - clique em
        "Autorizar no YouTube" na página do canal primeiro.</div>
        """
        return _render(body)

    try:
        info = youtube_upload.get_channel_info(secret_path, token_path)
        summary = youtube_analytics.channel_summary(secret_path, token_path, days=days)
        per_video = youtube_analytics.video_metrics(secret_path, token_path, days=days)
    except Exception as exc:
        return _render(_scope_error_body(channel_id, exc))

    # cruza com o catalogo local pra mostrar titulo/serie/status junto da metrica -
    # nem todo video do canal necessariamente passou por este pipeline (pode ter
    # sido publicado manualmente antes), entao usamos o titulo do YouTube como
    # fallback quando nao acha correspondencia local.
    local_by_youtube_id = {}
    for t in catalog.list_tracks(channel_id=channel_id, limit=500):
        if t["youtube_video_id"]:
            local_by_youtube_id[t["youtube_video_id"]] = t

    summary_cards = "".join(
        f"""<div class="panel" style="flex:1 1 140px; text-align:center;">
              <div class="muted" style="font-size:0.72rem; text-transform:uppercase;">{METRIC_LABEL}</div>
              <div style="font-family:'Space Grotesk',sans-serif; font-size:1.4rem; font-weight:700; margin-top:4px;">{VALUE}</div>
            </div>"""
        for METRIC_LABEL, VALUE in (
            (youtube_analytics.METRIC_LABELS[k], _format_metric(k, summary.get(k)))
            for k in youtube_analytics.METRICS.split(",")
        )
    ) if summary else '<div class="panel warn">Sem dados de métricas para o período (canal novo ou sem visualizações ainda).</div>'

    rows = ""
    # ordenado por views desc (ja vem assim da API)
    for video_id, metrics in per_video.items():
        local = local_by_youtube_id.get(video_id)
        title = local["title"] if local else video_id
        series_badge = f'<span class="badge inactive">{local["series"]}</span>' if local and local["series"] else ""
        metric_cells = "".join(f"<td>{_format_metric(k, metrics.get(k))}</td>" for k in
                                ("views", "averageViewPercentage", "averageViewDuration", "likes", "comments"))
        rows += f"""
        <tr>
          <td><a href="https://youtube.com/watch?v={video_id}" target="_blank">{title}</a> {series_badge}</td>
          {metric_cells}
        </tr>
        """

    period_links = "".join(
        f'<a class="btn secondary" href="{url_for("channel_dashboard", channel_id=channel_id, days=d)}"'
        f' style="{"filter: brightness(1.3);" if d == days else ""}">{d}d</a>'
        for d in (7, 28, 90)
    )

    body = f"""
    <p><a href="{url_for('edit_channel', channel_id=channel_id)}">&larr; Voltar</a></p>
    <h2>📊 Painel de métricas - {info.get('title', ch['name'])}</h2>
    <p>{period_links}</p>
    <div class="cols">{summary_cards}</div>

    <h3>Desempenho por vídeo (últimos {days} dias)</h3>
    <table>
      <tr><th>Vídeo</th><th>Views</th><th>% assistido</th><th>Duração média</th><th>Likes</th><th>Comentários</th></tr>
      {rows or '<tr><td colspan="6">Nenhum vídeo com dados nesse período.</td></tr>'}
    </table>
    """
    return _render(body)


@app.route("/channels/<int:channel_id>/youtube_videos/<video_id>/delete", methods=["POST"])
def delete_remote_video_direct(channel_id: int, video_id: str):
    ch = channels.get_channel(channel_id)
    try:
        youtube_upload.delete_video(video_id, channels.client_secret_path(ch["slug"]), channels.token_path(ch["slug"]))
        _flash(f"Vídeo {video_id} excluído do YouTube.")
    except Exception as exc:
        _flash(f"Falha ao excluir: {exc}")
    return redirect(url_for("youtube_channel_videos", channel_id=channel_id))


STATUS_LABELS = {
    "planned": "planejado",
    "narration_ready": "narração pronta",
    "video_ready": "vídeo montado",
    "pending_review": "🔴 pronto - publicar no YouTube",
    "uploaded": "✅ publicado no YouTube",
    "rejected": "rejeitado",
}

STATUS_CLASS = {
    "pending_review": "missing",
    "uploaded": "ok",
    "rejected": "inactive",
}


def _status_badge(status: str) -> str:
    cls = STATUS_CLASS.get(status, "inactive")
    label = STATUS_LABELS.get(status, status)
    return f'<span class="badge {cls}">{label}</span>'


def _fact_check_badge(flag: str | None) -> str:
    if not flag or flag == "sem_fonte":
        return '<span class="badge inactive">sem fonte p/ checar</span>'
    if flag == "atencao":
        return '<span class="badge missing">⚠ conferir fatos</span>'
    if flag == "ok":
        return '<span class="badge ok">fact-check ok</span>'
    return '<span class="badge inactive">fact-check indisponível</span>'


def _quality_badge(track) -> str:
    score = track["quality_score"] if "quality_score" in track.keys() else None
    if score is None:
        return ""
    cls = "ok" if score >= 75 else ("missing" if score >= 50 else "inactive")
    breakdown = track["quality_breakdown"] if "quality_breakdown" in track.keys() else ""
    title_attr = f' title="{breakdown}"' if breakdown else ""
    return f'<span class="badge {cls}"{title_attr}>⭐ qualidade {score}/100</span>'


def _privacy_select(field_id: str = "privacy_status") -> str:
    # "Visibilidade" (não "privacidade") - termo que o YouTube Studio usa pra
    # essa mesma opção, pra quem já usa o YouTube reconhecer de cara.
    return f"""
    <label for="{field_id}" class="muted" style="font-size:0.8rem; margin-left:4px;">Visibilidade:</label>
    <select name="privacy_status" id="{field_id}" style="width:auto; display:inline-block; margin:0 8px;">
      <option value="private">🔒 Privado</option>
      <option value="unlisted">🔗 Não listado</option>
      <option value="public">🌐 Público</option>
    </select>
    """


@app.route("/videos")
def list_videos():
    catalog.init_db()
    channel_id = request.args.get("channel_id", type=int)
    tracks = catalog.list_tracks(channel_id=channel_id)
    channel_map = {ch["id"]: ch["name"] for ch in channels.list_channels()}

    filter_options = "".join(
        f'<option value="{ch["id"]}" {"selected" if channel_id == ch["id"] else ""}>{ch["name"]}</option>'
        for ch in channels.list_channels()
    )

    rows = ""
    for t in tracks:
        rows += f"""
        <tr>
          <td>{t['id']}</td>
          <td>{channel_map.get(t['channel_id'], '?')}</td>
          <td><a href="{url_for('video_detail', track_id=t['id'])}">{t['title']}</a></td>
          <td>{_status_badge(t['status'])}</td>
          <td>{_fact_check_badge(t['fact_check_flag'])}</td>
          <td class="muted">{t['created_at'][:16].replace('T', ' ')}</td>
        </tr>
        """

    pending_count = sum(1 for t in tracks if t["status"] == "pending_review")
    batch_cta = (
        f'<a class="btn" href="{url_for("batch_review")}">⚡ Revisão em lote ({pending_count} aguardando)</a>'
        if pending_count else ""
    )
    studio_links = " ".join(
        f'<a class="btn secondary" href="{url_for("channel_studio", channel_id=c["id"])}">🎬 Gerar vídeo - {c["name"]}</a>'
        for c in channels.list_channels(active_only=True)
    )

    body = f"""
    <h2>Vídeos gerados</h2>
    <p>{batch_cta} {studio_links}</p>
    <form method="get" style="margin-bottom: 1rem;">
      <label style="display:inline;">Filtrar por canal:</label>
      <select name="channel_id" onchange="this.form.submit()" style="width:auto; display:inline; margin-left:8px;">
        <option value="">Todos</option>
        {filter_options}
      </select>
    </form>
    <table>
      <tr><th>ID</th><th>Canal</th><th>Título</th><th>Status</th><th>Fact-check</th><th>Criado</th></tr>
      {rows or '<tr><td colspan="6">Nenhum vídeo gerado ainda.</td></tr>'}
    </table>
    """
    return _render(body, active_nav="videos")


@app.route("/videos/review")
def batch_review():
    catalog.init_db()
    channel_id = request.args.get("channel_id", type=int)
    tracks = [t for t in catalog.list_tracks(channel_id=channel_id, limit=500) if t["status"] == "pending_review"]
    channel_map = {ch["id"]: ch["name"] for ch in channels.list_channels()}

    cards = ""
    for t in tracks:
        has_thumb = bool(t["thumbnail_path"]) and Path(t["thumbnail_path"]).exists()
        thumb = (
            f'<img class="preview" src="{url_for("track_file", track_id=t["id"], kind="thumbnail")}" style="width:160px;">'
            if has_thumb else '<div class="muted" style="width:160px;">sem thumbnail</div>'
        )
        has_short = bool(t["video_vertical_path"]) and Path(t["video_vertical_path"]).exists()
        fact_note = (
            '<p class="muted" style="color:var(--missing-fg);">⚠ fact-check pediu atenção - revise o roteiro antes de aprovar</p>'
            if t["fact_check_flag"] == "atencao" else ""
        )
        cards += f"""
        <div class="panel" style="display:flex; gap:16px; align-items:flex-start;">
          {thumb}
          <div style="flex:1;">
            <a href="{url_for('video_detail', track_id=t['id'])}"><b>{t['title']}</b></a>
            <span class="badge inactive">{channel_map.get(t['channel_id'], '?')}</span>
            {_fact_check_badge(t['fact_check_flag'])}
            {fact_note}
            <p class="muted" style="max-height:60px; overflow:hidden;">{t['script'][:220]}...</p>
            <form class="inline" method="post" action="{url_for('approve_video', track_id=t['id'])}" style="display:inline-flex; align-items:center;">
              <input type="hidden" name="return_to" value="review">
              <button type="submit">📤 Publicar no YouTube</button>
              {_privacy_select(f'privacy_video_{t["id"]}')}
            </form>
            {f'''<form class="inline" method="post" action="{url_for('approve_short', track_id=t['id'])}" style="display:inline-flex; align-items:center;">
              <input type="hidden" name="return_to" value="review">
              <button type="submit" class="secondary">📤 Publicar Short no YouTube</button>
              {_privacy_select(f'privacy_short_{t["id"]}')}
            </form>''' if has_short else ''}
            <form class="inline" method="post" action="{url_for('reject_video', track_id=t['id'])}">
              <input type="hidden" name="return_to" value="review">
              <button type="submit" class="secondary">Rejeitar</button>
            </form>
          </div>
        </div>
        """

    body = f"""
    <p><a href="{url_for('list_videos')}">&larr; Voltar pra lista completa</a></p>
    <h2>⚡ Revisão em lote ({len(tracks)} aguardando)</h2>
    <p class="muted">Thumbnail + roteiro (resumido) + ação, sem precisar abrir vídeo por vídeo. Pra
    assistir o vídeo/short inteiro ou ler o roteiro completo antes de decidir, clique no título.</p>
    {cards or '<div class="panel">Nada aguardando revisão no momento.</div>'}
    """
    return _render(body, active_nav="videos")


@app.route("/videos/<int:track_id>")
def video_detail(track_id: int):
    track = catalog.get_track(track_id)
    if track is None:
        abort(404)
    channel = channels.get_channel(track["channel_id"])

    credits = track["image_credits"].split(", ") if track["image_credits"] else ["NASA"]
    description_preview = orchestrator._build_description(track["topic"], track["script"], credits)
    tags_preview = ", ".join(orchestrator._build_tags(channel, track))

    has_video = bool(track["video_path"]) and Path(track["video_path"]).exists()
    has_short = bool(track["video_vertical_path"]) and Path(track["video_vertical_path"]).exists()
    has_thumb = bool(track["thumbnail_path"]) and Path(track["thumbnail_path"]).exists()

    video_player = (
        f'<video controls src="{url_for("track_file", track_id=track_id, kind="video")}"></video>'
        if has_video else '<p class="muted">Vídeo horizontal ainda não montado.</p>'
    )
    short_player = (
        f'<video controls src="{url_for("track_file", track_id=track_id, kind="short")}"></video>'
        if has_short else '<p class="muted">Short ainda não montado.</p>'
    )
    thumb_img = (
        f'<img class="preview" src="{url_for("track_file", track_id=track_id, kind="thumbnail")}">'
        if has_thumb else '<p class="muted">Sem thumbnail.</p>'
    )

    youtube_link = ""
    if track["youtube_video_id"]:
        youtube_link += f'<p>▶ <a href="https://youtube.com/watch?v={track["youtube_video_id"]}" target="_blank">Vídeo publicado no YouTube</a></p>'
    if track["youtube_short_video_id"]:
        youtube_link += f'<p>▶ <a href="https://youtube.com/shorts/{track["youtube_short_video_id"]}" target="_blank">Short publicado no YouTube</a></p>'

    metrics_panel = ""
    if track["youtube_video_id"] and channels.token_path(channel["slug"]).exists():
        try:
            metrics = youtube_analytics.video_metrics_single(
                channels.client_secret_path(channel["slug"]), channels.token_path(channel["slug"]),
                track["youtube_video_id"], days=28,
            )
        except Exception as exc:
            metrics = None
            metrics_panel = f'<div class="panel warn muted">Não foi possível carregar métricas: {exc}</div>'
        if metrics:
            cards = "".join(
                f"""<div class="panel" style="flex:1 1 120px; text-align:center;">
                      <div class="muted" style="font-size:0.7rem; text-transform:uppercase;">{youtube_analytics.METRIC_LABELS[k]}</div>
                      <div style="font-family:'Space Grotesk',sans-serif; font-size:1.2rem; font-weight:700;">{_format_metric(k, metrics.get(k))}</div>
                    </div>"""
                for k in youtube_analytics.METRICS.split(",")
            )
            metrics_panel = f"""
            <h3>Métricas deste vídeo (últimos 28 dias)</h3>
            <div class="cols">{cards}</div>
            """
        elif metrics == {}:
            metrics_panel = '<p class="muted">Ainda sem dados de métricas pra este vídeo (recém-publicado ou sem visualizações no período).</p>'

    actions = ""
    if track["status"] == "pending_review":
        actions += f"""
        <form class="inline" method="post" action="{url_for('approve_video', track_id=track_id)}" style="display:inline-flex; align-items:center;">
          <button type="submit">📤 Publicar no YouTube</button>
          {_privacy_select('privacy_video')}
        </form>
        <form class="inline" method="post" action="{url_for('reject_video', track_id=track_id)}">
          <button type="submit" class="secondary">Rejeitar</button>
        </form>
        """
    if has_short and not track["youtube_short_video_id"] and track["status"] in ("pending_review", "video_ready", "uploaded"):
        actions += f"""
        <form class="inline" method="post" action="{url_for('approve_short', track_id=track_id)}" style="display:inline-flex; align-items:center;">
          <button type="submit" class="secondary">📤 Publicar Short no YouTube</button>
          {_privacy_select('privacy_short')}
        </form>
        """

    fact_check_note = ""
    if track["fact_check_flag"] == "atencao":
        details = track["fact_check_details"] if "fact_check_details" in track.keys() else None
        details_html = f"<br><span style='font-size:0.85rem;'>{details}</span>" if details else ""
        fact_check_note = (
            '<div class="flash">O fact-check automático encontrou afirmação(ões) no roteiro sem '
            f"correspondência clara nos fatos-fonte. Confira o roteiro com atenção antes de aprovar.{details_html}</div>"
        )

    clarity_note = ""
    clarity_text = track["clarity_review"] if "clarity_review" in track.keys() else None
    if clarity_text and not clarity_text.lower().startswith("nenhum"):
        clarity_note = (
            '<div class="panel warn"><b>👁 Revisão de clareza (persona leigo, gerada por IA):</b><br>'
            f"{clarity_text}</div>"
        )

    feedback_badge = ""
    if track["feedback"] == "liked":
        feedback_badge = '<span class="badge ok">👍 aprovado como exemplo</span>'
    elif track["feedback"] == "disliked":
        feedback_badge = '<span class="badge missing">👎 marcado pra evitar</span>'

    ab_state = track["active_thumbnail"] if "active_thumbnail" in track.keys() else None
    ab_badge = {
        "a": "",
        None: "",
        "b": '<span class="badge inactive">🅰️🅱️ teste de thumbnail: rodando variante B</span>',
        "b_confirmed": '<span class="badge ok">🅱️ venceu o teste A/B de thumbnail</span>',
        "a_confirmed": '<span class="badge ok">🅰️ venceu o teste A/B de thumbnail (voltou pra A)</span>',
    }.get(ab_state, "")

    llm_response = ""
    consult_pending = _consult_status.get(track_id)
    if consult_pending:
        llm_response = f'<div class="panel accent muted">{consult_pending}</div>'
    elif track["feedback_action"]:
        llm_response = f"""
        <div class="panel accent">
          <h3 style="margin-top:0;">Resposta do Llama sobre sua última observação</h3>
          <div class="script-box">{track['feedback_action']}</div>
        </div>
        """

    has_local_files = has_video or has_short or has_thumb or bool(track["narration_path"])
    has_remote = bool(track["youtube_video_id"]) or bool(track["youtube_short_video_id"])

    delete_section = f"""
    <div class="panel warn">
      <h3 style="margin-top:0; color: var(--missing-fg);">Zona de exclusão</h3>
      <p class="muted">Exclusão física e irreversível - não tem lixeira. Arquivos locais somem do
      disco; exclusão remota apaga o vídeo direto do YouTube.</p>
      <form class="inline" method="post" action="{url_for('delete_local', track_id=track_id)}"
            onsubmit="return confirm('Apagar os arquivos locais deste vídeo (vídeo, short, thumbnail, narração)? Isso não pode ser desfeito.');">
        <button type="submit" class="secondary" {"disabled" if not has_local_files else ""}>Excluir arquivos locais</button>
      </form>
      <form class="inline" method="post" action="{url_for('delete_remote', track_id=track_id)}"
            onsubmit="return confirm('Excluir este vídeo diretamente do YouTube? Isso não pode ser desfeito.');">
        <button type="submit" class="secondary" {"disabled" if not has_remote else ""}>Excluir do YouTube</button>
      </form>
      <form class="inline" method="post" action="{url_for('delete_track', track_id=track_id)}"
            onsubmit="return confirm('Excluir este registro por completo (arquivos locais + linha do banco)? O vídeo no YouTube, se publicado, NÃO é apagado por este botão - use \\'Excluir do YouTube\\' antes, se quiser.');">
        <button type="submit" class="secondary">Excluir registro (mantém o que já estiver no YouTube)</button>
      </form>
    </div>
    """

    body = f"""
    <p><a href="{url_for('list_videos')}">&larr; Voltar para a lista</a></p>
    <h2>{track['title']}</h2>
    <p>{_status_badge(track['status'])} {_fact_check_badge(track['fact_check_flag'])} {_quality_badge(track)} {feedback_badge} {ab_badge}
       <span class="badge inactive">canal: {channel['name']}</span>
       {f'<span class="badge inactive">série: {track["series"]}</span>' if track['series'] else ''}
    </p>
    {fact_check_note}
    {clarity_note}
    {youtube_link}
    {metrics_panel}
    {actions}

    <div class="cols">
      <div>
        <h3>Vídeo (horizontal)</h3>
        {video_player}
        <h3>Short (vertical)</h3>
        {short_player}
      </div>
      <div>
        <h3>Thumbnail</h3>
        {thumb_img}
      </div>
    </div>

    <h3>Roteiro (o que será narrado)</h3>
    <div class="script-box">{track['script']}</div>

    <h3>Descrição a ser usada no YouTube</h3>
    <div class="script-box">{description_preview}</div>

    <h3>Tags a serem usadas</h3>
    <div class="script-box">{tags_preview}</div>

    <h3>Sua avaliação</h3>
    <p class="muted">Assista ao vídeo e leia o roteiro acima, depois avalie. 👍/👎 não publica nem
    rejeita o vídeo - é só um sinal de qualidade: os próximos roteiros gerados pelo Llama para este
    canal passam a ver os vídeos que você aprovou como exemplo de estilo, e as observações viram
    instrução de "evite isso" (few-shot a partir do seu feedback, já que não há infraestrutura de
    fine-tuning do modelo neste pipeline).</p>
    {llm_response}
    <form method="post" action="{url_for('give_feedback', track_id=track_id)}">
      <button type="submit" name="feedback" value="liked">👍 Gostei</button>
      <button type="submit" name="feedback" value="disliked" class="secondary">👎 Não gostei</button>
      <label>Observação (o que funcionou bem, ou o que evitar da próxima vez)</label>
      <p class="muted" style="font-size:0.8rem;">Motivos rápidos (clique pra preencher, depois ajuste o texto):
        <a href="#" onclick="document.getElementById('fb-notes').value='Imagens não batem com o assunto narrado.'; return false;">imagem não bate</a> ·
        <a href="#" onclick="document.getElementById('fb-notes').value='Gancho inicial fraco, não prende atenção.'; return false;">gancho fraco</a> ·
        <a href="#" onclick="document.getElementById('fb-notes').value='Tom didático demais / redundante.'; return false;">redundante</a> ·
        <a href="#" onclick="document.getElementById('fb-notes').value='Título/roteiro genérico demais.'; return false;">genérico demais</a>
      </p>
      <textarea id="fb-notes" name="notes" rows="3" placeholder="ex.: as imagens depois da primeira não batem com o assunto do vídeo">{track['feedback_notes'] or ''}</textarea>
      <button type="submit" formaction="{url_for('consult_feedback_route', track_id=track_id)}" class="secondary">
        💬 Enviar observação e pedir análise ao Llama
      </button>
    </form>

    {delete_section}
    """
    return _render(body, active_nav="videos")


@app.route("/videos/<int:track_id>/file/<kind>")
def track_file(track_id: int, kind: str):
    track = catalog.get_track(track_id)
    if track is None:
        abort(404)
    path_map = {
        "video": track["video_path"],
        "short": track["video_vertical_path"],
        "thumbnail": track["thumbnail_path"],
    }
    raw_path = path_map.get(kind)
    if not raw_path or not Path(raw_path).exists():
        abort(404)
    return send_file(Path(raw_path))


@app.route("/voice_preview/<voice>.mp3")
def voice_preview(voice: str):
    from pipeline import narration
    # A voz vem embutida no nome do arquivo (ex.: "pt-BR-AntonioNeural") -
    # acha o idioma correspondente pra usar o texto de prévia certo; cai pro
    # idioma padrão se por algum motivo a voz não bater com nenhum cadastrado
    # (não deveria acontecer, já que a lista vem sempre de config.LANGUAGES).
    language = next(
        (lang for lang in config.LANGUAGES.values() if voice in lang["voice_options"].values()),
        config.LANGUAGES[config.DEFAULT_LANGUAGE],
    )
    try:
        path = narration.get_or_build_voice_preview(voice, language["preview_text"])
    except Exception as exc:
        abort(502, description=f"Falha ao gerar prévia de voz: {exc}")
    return send_file(path)


@app.route("/channels/<int:channel_id>/voice", methods=["POST"])
def update_channel_voice(channel_id: int):
    voice = request.form.get("narration_voice", "").strip()
    if not voice:
        abort(400)
    channels.update_channel(channel_id, narration_voice=voice)
    _flash(f"Voz de narração do canal atualizada para \"{voice}\".")
    return redirect(request.referrer or url_for("channel_studio", channel_id=channel_id))


def _return_after_action(track_id: int):
    """Pra onde voltar depois de aprovar/rejeitar - a fila de revisão em lote
    (várias linhas na mesma página) ou a página de detalhe de 1 vídeo só,
    dependendo de onde a ação foi disparada."""
    if request.form.get("return_to") == "review":
        return redirect(url_for("batch_review"))
    return redirect(url_for("video_detail", track_id=track_id))


_VALID_PRIVACY_STATUSES = {"private", "unlisted", "public"}
_PRIVACY_LABELS = {"private": "privado", "unlisted": "não listado", "public": "público"}


def _privacy_from_form() -> str:
    value = request.form.get("privacy_status", "private")
    return value if value in _VALID_PRIVACY_STATUSES else "private"


@app.route("/videos/<int:track_id>/approve", methods=["POST"])
def approve_video(track_id: int):
    privacy_status = _privacy_from_form()
    try:
        track = catalog.get_track(track_id)
        video_id = orchestrator.approve_and_upload(track_id, privacy_status=privacy_status)
        catalog.log_approval_decision(track_id, track["channel_id"], "approved_video", track["quality_score"])
        _flash(f"Vídeo publicado ({_PRIVACY_LABELS[privacy_status]}): https://youtube.com/watch?v={video_id}")
    except Exception as exc:
        _flash(f"Falha ao publicar o vídeo: {exc}")
    return _return_after_action(track_id)


@app.route("/videos/<int:track_id>/approve_short", methods=["POST"])
def approve_short(track_id: int):
    privacy_status = _privacy_from_form()
    try:
        track = catalog.get_track(track_id)
        video_id = orchestrator.approve_and_upload_short(track_id, privacy_status=privacy_status)
        catalog.log_approval_decision(track_id, track["channel_id"], "approved_short", track["quality_score"])
        _flash(f"Short publicado ({_PRIVACY_LABELS[privacy_status]}): https://youtube.com/shorts/{video_id}")
    except Exception as exc:
        _flash(f"Falha ao publicar o Short: {exc}")
    return _return_after_action(track_id)


@app.route("/videos/<int:track_id>/reject", methods=["POST"])
def reject_video(track_id: int):
    track = catalog.get_track(track_id)
    catalog.update_track(track_id, status="rejected")
    catalog.log_approval_decision(track_id, track["channel_id"], "rejected", track["quality_score"])
    _flash("Vídeo marcado como rejeitado - os arquivos continuam em data/output/ se quiser recuperar.")
    return _return_after_action(track_id)


@app.route("/videos/<int:track_id>/feedback", methods=["POST"])
def give_feedback(track_id: int):
    feedback = request.form.get("feedback")
    if feedback not in ("liked", "disliked"):
        abort(400)
    notes = request.form.get("notes", "").strip() or None
    catalog.update_track(track_id, feedback=feedback, feedback_notes=notes)
    if feedback == "liked":
        _flash("Marcado como 👍 - vai entrar como exemplo de estilo nos próximos roteiros desse canal.")
    else:
        _flash("Marcado como 👎 - a observação (se preenchida) vai orientar o que evitar nos próximos roteiros.")
    return redirect(url_for("video_detail", track_id=track_id))


def _run_consult(track_id: int, notes: str) -> None:
    from pipeline import script_gen

    track = catalog.get_track(track_id)
    channel = channels.get_channel(track["channel_id"])
    result = script_gen.consult_feedback(track["title"], track["script"], notes, channel["niche"] or "ciência")

    if result["error"]:
        _consult_status[track_id] = result["error"]
    else:
        action_text = f"Entendimento: {result['understanding']}\n\nAções para os próximos vídeos: {result['actions']}"
        catalog.update_track(track_id, feedback_action=action_text)
        _consult_status.pop(track_id, None)


@app.route("/videos/<int:track_id>/consult", methods=["POST"])
def consult_feedback_route(track_id: int):
    notes = request.form.get("notes", "").strip()
    if not notes:
        _flash("Escreva uma observação antes de pedir a análise do Llama.")
        return redirect(url_for("video_detail", track_id=track_id))

    catalog.update_track(track_id, feedback_notes=notes)
    _consult_status[track_id] = "🤔 Consultando o Llama... isso pode levar até 2 minutos. Atualize a página pra ver a resposta."
    threading.Thread(target=_run_consult, args=(track_id, notes), daemon=True).start()
    _flash("Observação enviada - o Llama está processando em segundo plano (veja o status abaixo).")
    return redirect(url_for("video_detail", track_id=track_id))


def _delete_file(raw_path: str | None) -> None:
    if not raw_path:
        return
    path = Path(raw_path)
    if path.exists():
        path.unlink()


@app.route("/videos/<int:track_id>/delete_local", methods=["POST"])
def delete_local(track_id: int):
    track = catalog.get_track(track_id)
    for field in ("video_path", "video_vertical_path", "thumbnail_path", "narration_path"):
        _delete_file(track[field])
    catalog.update_track(
        track_id, video_path=None, video_vertical_path=None, thumbnail_path=None, narration_path=None,
    )
    _flash("Arquivos locais excluídos. O registro (roteiro, título, avaliações) continua no histórico.")
    return redirect(url_for("video_detail", track_id=track_id))


@app.route("/videos/<int:track_id>/delete_remote", methods=["POST"])
def delete_remote(track_id: int):
    track = catalog.get_track(track_id)
    channel = channels.get_channel(track["channel_id"])
    secret_path = channels.client_secret_path(channel["slug"])
    token_path = channels.token_path(channel["slug"])

    errors = []
    if track["youtube_video_id"]:
        try:
            youtube_upload.delete_video(track["youtube_video_id"], secret_path, token_path)
            catalog.update_track(track_id, youtube_video_id=None)
        except Exception as exc:
            errors.append(f"vídeo: {exc}")
    if track["youtube_short_video_id"]:
        try:
            youtube_upload.delete_video(track["youtube_short_video_id"], secret_path, token_path)
            catalog.update_track(track_id, youtube_short_video_id=None)
        except Exception as exc:
            errors.append(f"short: {exc}")

    if errors:
        _flash("Falha ao excluir do YouTube - " + "; ".join(errors))
    else:
        _flash("Excluído do YouTube com sucesso.")
    return redirect(url_for("video_detail", track_id=track_id))


@app.route("/videos/<int:track_id>/delete_track", methods=["POST"])
def delete_track(track_id: int):
    track = catalog.get_track(track_id)
    for field in ("video_path", "video_vertical_path", "thumbnail_path", "narration_path"):
        _delete_file(track[field])
    with catalog.get_conn() as conn:
        conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    _flash(
        "Registro excluído (arquivos locais apagados). "
        + ("O vídeo publicado no YouTube NÃO foi apagado - exclua por lá se quiser." if track["youtube_video_id"] or track["youtube_short_video_id"] else "")
    )
    return redirect(url_for("list_videos"))


@app.route("/reports")
def weekly_report():
    days = request.args.get("days", default=28, type=int)
    channel_id = request.args.get("channel_id", type=int)
    rows = reports.series_performance(days=days, channel_id=channel_id)

    channel_filter_options = "".join(
        f'<option value="{c["id"]}" {"selected" if channel_id == c["id"] else ""}>{c["name"]}</option>'
        for c in channels.list_channels()
    )

    period_links = "".join(
        f'<a class="btn secondary" href="{url_for("weekly_report", days=d, channel_id=channel_id)}"'
        f' style="{"filter: brightness(1.3);" if d == days else ""}">{d}d</a>'
        for d in (7, 28, 90)
    )

    table_rows = ""
    for r in rows:
        views_fmt = f"{r['views']:,}".replace(",", ".")
        watch_fmt = f"{int(r['watch_minutes']):,}".replace(",", ".")
        table_rows += f"""
        <tr>
          <td>{r['channel']}</td>
          <td>{r['series']}</td>
          <td>{r['videos']}</td>
          <td>{views_fmt}</td>
          <td>{r['avg_view_pct']:.1f}%</td>
          <td>{watch_fmt}</td>
          <td>{r['likes']}</td>
        </tr>
        """

    insight = ""
    if len(rows) >= 2:
        best, worst = rows[0], rows[-1]
        insight = f"""
        <div class="panel accent">
          <b>Leitura rápida:</b> "{best['series']}" ({best['channel']}) está na frente com
          {best['views']} views e {best['avg_view_pct']:.0f}% de retenção média. "{worst['series']}"
          ({worst['channel']}) é o que menos performou no período - vale considerar ajustar o molde
          de roteiro dessa série ou aposentá-la se a tendência se confirmar em relatórios futuros.
        </div>
        """

    no_data_note = "" if rows else """
        <div class="panel warn">Sem dados ainda - precisa de pelo menos 1 canal autorizado com o
        escopo de analytics (yt-analytics.readonly) e vídeos publicados com views no período.</div>
    """

    title = "📈 Relatório por série" + (" - todos os canais" if not channel_id else "")
    body = f"""
    <h2>{title}</h2>
    <p class="muted">Cruza o que cada série do pipeline produz com o desempenho real no YouTube -
    pra decidir com dado, não só com feeling, quais séries/temas merecem mais espaço.</p>
    <form method="get" style="margin-bottom: 1rem;">
      <label style="display:inline;">Canal:</label>
      <select name="channel_id" onchange="this.form.submit()" style="width:auto; display:inline; margin-left:8px;">
        <option value="">Todos os canais</option>
        {channel_filter_options}
      </select>
      <input type="hidden" name="days" value="{days}">
    </form>
    <p>{period_links} <a class="btn secondary" href="{url_for('approval_log_view', channel_id=channel_id)}">📋 Log de aprovações</a></p>
    {insight}
    {no_data_note}
    <table>
      <tr><th>Canal</th><th>Série</th><th>Vídeos</th><th>Views</th><th>% média assistida</th><th>Min. assistidos</th><th>Likes</th></tr>
      {table_rows}
    </table>
    """
    return _render(body, active_nav="reports")


@app.route("/approval_log")
def approval_log_view():
    channel_id = request.args.get("channel_id", type=int)
    entries = catalog.list_approval_log(channel_id=channel_id, limit=200)
    channel_map = {c["id"]: c["name"] for c in channels.list_channels()}

    decision_labels = {
        "approved_video": "✅ vídeo aprovado", "approved_short": "✅ Short aprovado", "rejected": "❌ rejeitado",
    }
    rows_html = "".join(
        f"<tr><td>{e['created_at'][:16].replace('T', ' ')}</td>"
        f"<td>{channel_map.get(e['channel_id'], '?')}</td>"
        f"<td><a href=\"{url_for('video_detail', track_id=e['track_id'])}\">track {e['track_id']}</a></td>"
        f"<td>{decision_labels.get(e['decision'], e['decision'])}</td>"
        f"<td>{e['quality_score'] if e['quality_score'] is not None else '-'}</td></tr>"
        for e in entries
    )
    body = f"""
    <p><a href="{url_for('weekly_report')}">&larr; Voltar pro relatório</a></p>
    <h2>📋 Log de aprovações</h2>
    <p class="muted">Registro append-only de cada decisão humana de aprovar/rejeitar um vídeo, com o
    score de qualidade automático daquele momento - evidência de revisão editorial real, útil em caso
    de contestar um flag de "conteúdo inautêntico" do YouTube.</p>
    <table>
      <tr><th>Data (UTC)</th><th>Canal</th><th>Vídeo</th><th>Decisão</th><th>Score</th></tr>
      {rows_html or '<tr><td colspan="5" class="muted">Nenhuma decisão registrada ainda.</td></tr>'}
    </table>
    """
    return _render(body, active_nav="reports")


def main():
    catalog.init_db()
    channels.ensure_default_channel()
    from pipeline import queue_worker
    queue_worker.ensure_worker_started()
    app.run(host="127.0.0.1", port=5151, debug=False)


if __name__ == "__main__":
    main()
