# YouTube Content Creator

Fábrica automatizada de canais de YouTube: cada canal cadastrado gera, 1x/dia,
um roteiro narrado (com base em fatos reais quando disponível), narração,
vídeo horizontal + Short, thumbnail e metadados — tudo local, sem custo de
API paga (Ollama local, TTS gratuito, imagens de fonte pública). Um gate de
revisão humana obrigatório impede publicação sem aprovação manual.

Suporta **múltiplos canais/contas** de nichos diferentes rodando na mesma
máquina, cada um com credenciais, idioma, voz e temas próprios.

## Como abrir o painel

```
python -m pipeline.settings_ui
```

Abre em **http://127.0.0.1:5151** (só local, sem exposição externa). Três abas:

- **Canais e credenciais** — cadastro de canal, chave da NASA (compartilhada
  entre todos os canais), credenciais OAuth do YouTube por canal, botão de
  "Kit de canal automático" (gera temas + nomes de série a partir do nicho
  via Llama), painel de métricas por canal, lista dos vídeos reais já
  publicados no YouTube, checagem de saúde do canal.
- **Vídeos gerados** — lista todos os vídeos do pipeline (todos os canais ou
  filtrado por um), com fila de **revisão em lote** (`/videos/review`) pra
  aprovar/rejeitar vários de uma vez sem abrir um por um. Cada vídeo tem
  página própria com preview do vídeo/Short/thumbnail, roteiro completo,
  descrição e tags que serão usadas, métricas reais (se já publicado),
  avaliação 👍/👎 com consulta imediata ao Llama sobre o que melhorar, e
  botões de exclusão física (local e/ou remota no YouTube).
- **Relatório por série** (`/reports`) — cruza o catálogo local com a
  YouTube Analytics API, agregando desempenho por série/canal, pra decidir
  com dado (não só feeling) quais séries/temas merecem mais espaço.

## Rodar o pipeline manualmente

```python
from pipeline import orchestrator
orchestrator.run_all_active_channels()   # gera o vídeo do dia de todos os canais ativos
orchestrator.prepare_daily_video(channel_id=1)   # só de 1 canal
orchestrator.approve_and_upload(track_id)        # publica o vídeo horizontal (depois de revisar)
orchestrator.approve_and_upload_short(track_id)  # publica o Short
```

## Diagnóstico rápido

```
python scripts/smoke_test.py
```

Confere em segundos: Ollama rodando, chave da NASA válida, edge-tts
instalado, e status de autorização de cada canal - sem gerar vídeo nenhum.

## Agendamento automático

Já cadastrado no Windows Task Scheduler como **"artCover - Geracao Diaria"** (nome da tarefa
ainda não renomeado no sistema; rode `scripts\setup_task_scheduler.ps1` novamente e remova
a tarefa antiga manualmente se quiser o nome atualizado)
(roda 3h da manhã). Reconfigurar: `scripts\setup_task_scheduler.ps1`. Roda
`scripts/run_daily.py`, que chama `run_all_active_channels()` e notifica
(balão do Windows + log em `data/logs/`) ao final.

## ⚠️ Pendência atual

O canal "Astronomia" precisa ser **reautorizado no YouTube** (o token
anterior tinha um escopo mais restrito do que o painel de métricas e a
exclusão remota exigem agora). Na aba do canal, clique em "Autorizar no
YouTube". Confira também se o app OAuth no Google Cloud Console tem o
escopo `https://www.googleapis.com/auth/youtube` (não só `.upload`)
cadastrado na Tela de consentimento OAuth - sem isso lá, a reautorização
concede acesso restrito mesmo pedindo o escopo certo.

## Arquitetura (módulos em `pipeline/`)

| Módulo | Responsabilidade |
|---|---|
| `channels.py` | CRUD de canais, idioma, voz, chave NASA compartilhada, credenciais |
| `catalog.py` | SQLite - canais, tracks (vídeos), settings globais |
| `script_gen.py` | Roteiro (Ollama), fact-check automático, kit de canal, few-shot de feedback |
| `visual_source.py` | Busca de imagens NASA/APOD/ESA-Hubble, com retry/backoff |
| `narration.py` | TTS (edge-tts) + alinhamento de pontuação nas legendas |
| `audio_post.py` | Normalização/fade do áudio |
| `video_build.py` | Montagem do vídeo (Ken Burns, crossfade, legendas, CTA, thumbnail) |
| `thumbnail.py` | Geração de thumbnail |
| `orchestrator.py` | Pipeline completo, checkpoint/resume, upload |
| `youtube_upload.py` | OAuth, upload, exclusão, listagem de vídeos do canal |
| `youtube_analytics.py` | Métricas (views, retenção, likes) por canal/vídeo |
| `reports.py` | Agregação de desempenho por série |
| `health.py` | Detecção de vídeo removido do canal |
| `notify.py` | Log diário + notificação nativa do Windows |
| `backup.py` | Backup automático do catálogo |
| `settings_ui.py` | Interface web local (Flask) |

## Idiomas suportados

pt-BR, en-US, es-ES (configurável por canal - roteiro, voz, CTA de
inscrição e rótulo de crédito de imagem seguem o idioma escolhido).
Adicionar um novo idioma: editar `config.LANGUAGES`.
