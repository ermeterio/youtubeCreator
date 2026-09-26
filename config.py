import os
from pathlib import Path

from PIL import Image

# As imagens processadas aqui vêm só de fontes confiáveis (APIs oficiais da
# NASA/ESA), nunca de upload de terceiros - desativa o limite de "bomba de
# descompressão" do Pillow (pensado pra proteger contra upload malicioso),
# que já derrubou a geração diária inteira ao encontrar uma imagem real e
# legítima da NASA maior que o limite padrão (~178 milhões de pixels).
Image.MAX_IMAGE_PIXELS = None

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = DATA_DIR / "assets"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
FONTS_DIR = ASSETS_DIR / "fonts"
IMAGE_CACHE_DIR = ASSETS_DIR / "nasa_cache"
OUTPUT_DIR = DATA_DIR / "output"
CATALOG_DB = DATA_DIR / "catalog.db"

SECRETS_DIR = BASE_DIR / "secrets"
YOUTUBE_CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"
YOUTUBE_TOKEN_FILE = SECRETS_DIR / "youtube_token.json"

# Cadastre uma chave gratuita em https://api.nasa.gov/ e defina NASA_API_KEY no
# ambiente. Sem isso, cai para DEMO_KEY (só 30 req/hora, 50/dia - ok pra testar,
# não pra produção diária real).
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

# Temas rotativos ficaram por canal (ver pipeline.channels.DEFAULT_TOPICS e a
# coluna topics_json da tabela channels) - cada canal tem sua própria lista,
# já que canais diferentes cobrem assuntos diferentes.

# Escopo "youtube" completo (não só "youtube.upload") - necessário pra listar
# os vídeos que já existem no canal e pra excluir vídeos remotamente pela
# interface de revisão, além de publicar. "yt-analytics.readonly" habilita o
# painel de métricas (views, retenção, likes, inscritos ganhos) por canal e
# por vídeo. Se você já autorizou algum canal antes dessa mudança, reautorize
# pelo botão na interface (o token antigo, com escopo mais restrito, vai ser
# rejeitado pela API nessas chamadas novas).
YOUTUBE_UPLOAD_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

VIDEO_RESOLUTION = (1920, 1080)
VIDEO_FPS = 30

# Teste A/B de thumbnail: dias de espera antes de trocar pra variante B (dar
# tempo de acumular impressões reais), mínimo de impressões pra considerar o
# CTR estatisticamente minimamente confiável, e dias de espera após a troca
# antes de comparar B contra A e decidir qual fica.
THUMBNAIL_AB_TEST_WAIT_DAYS = 3
THUMBNAIL_AB_MIN_IMPRESSIONS = 200

# Hierarquia tipográfica do canal (Space Grotesk + Inter + JetBrains Mono,
# todas Google Fonts / licença OFL - uso comercial em vídeo liberado, sem
# exigir crédito na tela). Cada papel cai para Arial Bold do Windows se o
# .ttf correspondente não existir em data/assets/fonts/.
_ARIAL_FALLBACK = r"C:\Windows\Fonts\arialbd.ttf"


def _font(filename: str) -> str:
    path = FONTS_DIR / filename
    return str(path) if path.exists() else _ARIAL_FALLBACK


FONT_TITLE = _font("SpaceGrotesk-Bold.ttf")          # título (thumbnail + abertura do vídeo)
FONT_CAPTION = _font("Inter-ExtraBold.ttf")           # legenda dinâmica sincronizada (estilo Shorts)
FONT_CREDIT = _font("Inter-Regular.ttf")              # crédito da imagem, discreto
FONT_CTA = _font("SpaceGrotesk-Bold.ttf")             # chamada "inscreva-se"
FONT_DATA = _font("JetBrainsMono-Bold.ttf")           # dados numéricos (distâncias, anos-luz), se usado

# Mantido por compatibilidade com código que ainda referencia uma fonte única.
DEFAULT_FONT = FONT_TITLE

# Termos genéricos usados só como ÚLTIMO recurso, se a busca pelo tema
# específico do dia não trouxer imagens suficientes nas APIs da NASA/ESA.
# Preferir sempre imagens relacionadas ao tema real do roteiro; isso aqui é
# só para o vídeo não ficar com imagem repetida quando a busca específica
# falha.
GENERIC_IMAGE_QUERIES = [
    "galaxy", "nebula", "black hole", "solar system",
    "stars", "hubble telescope", "james webb telescope", "supernova", "star cluster",
]
# "spacecraft" foi removido de propósito: a busca da NASA devolve fotos de
# engenharia/sala limpa (sonda sendo montada no chão) pra esse termo, não
# imagens de espaço - destoa completamente de roteiros sobre nebulosas,
# estrelas etc. e foi a causa raiz de um relato real de imagem sem relação
# nenhuma com a narração.

# Vozes disponíveis no edge-tts (`edge-tts --list-voices` pra ver todas).
# ThalitaMultilingualNeural/AvaMultilingualNeural usam o modelo multilíngue
# mais novo da Microsoft, tende a soar mais natural que as vozes "clássicas".
NARRATION_VOICE_OPTIONS = {
    "antonio": "pt-BR-AntonioNeural",       # masculina, modelo clássico
    "francisca": "pt-BR-FranciscaNeural",   # feminina, modelo clássico
    "thalita": "pt-BR-ThalitaMultilingualNeural",  # feminina, modelo multilíngue (mais natural)
}
NARRATION_VOICE = NARRATION_VOICE_OPTIONS["thalita"]

# Suporte multi-idioma por canal (roteiro gerado pelo LLM, voz, texto do CTA
# de inscrição e rótulo de crédito de imagem). `llm_language_name` é usado
# literalmente na instrução do prompt do roteirista ("escreva em ..."), então
# precisa ser um nome de idioma que o Llama reconheça bem.
LANGUAGES = {
    "pt-BR": {
        "label": "Português (Brasil)",
        "llm_language_name": "português do Brasil",
        "credit_label": "Crédito",
        "cta_text": "Inscreva-se no canal →",
        "default_series_primary": "Direto da Fonte",
        "default_series_fallback": "Round-up Rápido",
        "preview_text": "Esta é uma prévia da voz de narração deste canal, usada pra ler o roteiro dos vídeos.",
        "voice_options": {
            "antonio": "pt-BR-AntonioNeural",
            "francisca": "pt-BR-FranciscaNeural",
            "thalita": "pt-BR-ThalitaMultilingualNeural",
        },
        "default_voice": "pt-BR-ThalitaMultilingualNeural",
    },
    "en-US": {
        "label": "English (US)",
        "llm_language_name": "American English",
        "credit_label": "Credit",
        "cta_text": "Subscribe to the channel →",
        "default_series_primary": "Straight From The Source",
        "default_series_fallback": "Quick Roundup",
        "preview_text": "This is a preview of this channel's narration voice, used to read the video scripts.",
        "voice_options": {
            "guy": "en-US-GuyNeural",
            "jenny": "en-US-JennyNeural",
            "ava": "en-US-AvaMultilingualNeural",
        },
        "default_voice": "en-US-AvaMultilingualNeural",
    },
    "es-ES": {
        "label": "Español (España)",
        "llm_language_name": "español",
        "credit_label": "Crédito",
        "cta_text": "Suscríbete al canal →",
        "default_series_primary": "Directo De La Fuente",
        "default_series_fallback": "Resumen Rápido",
        "preview_text": "Esta es una vista previa de la voz de narración de este canal.",
        "voice_options": {
            "alvaro": "es-ES-AlvaroNeural",
            "elvira": "es-ES-ElviraNeural",
        },
        "default_voice": "es-ES-ElviraNeural",
    },
}
DEFAULT_LANGUAGE = "pt-BR"
