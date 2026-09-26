# Roadmap — YouTube Content Creator

Atualizado em 2026-09-25, com base em pesquisa de mercado (agentes especialistas) e no que já
foi implementado no mesmo dia. Foco exclusivo em YouTube por decisão do dono do canal — recursos
de outras plataformas (TikTok/Reels) estão fora de escopo por ora.

## Novidades de política que motivam prioridades (confirmadas via pesquisa, jan/2026)
- Divulgação de conteúdo sintético/alterado (`containsSyntheticMedia`) passou de "recomendada" para
  **obrigatória** — risco real de desmonetização/remoção por descumprimento.
- O YouTube encerrou 16 canais (35M inscritos, 4,7B views) por "conteúdo inautêntico" em massa. O
  algoritmo agora trata Shorts **cortados de um vídeo longo genuíno** como uso legítimo, mas penaliza
  volume sem supervisão editorial clara — reforça prioridade para Shorts cortados do longo em vez de
  gerados em paralelo sem relação editorial com ele.

## Nota operacional (25/09/2026)
Reiniciar o servidor (`pipeline.settings_ui`) enquanto a fila de geração está processando um item
pode deixar esse item preso em `running` pra sempre (a thread que o processava morre junto com o
processo). O worker agora se auto-recupera disso no próximo start (`queue_worker._recover_stale_running_items`),
mas o ideal continua sendo checar a fila/tracks ativos antes de reiniciar.

## Agora / próximo trimestre
- [x] **Divulgação de IA correta** (`containsSyntheticMedia`) — DONE (25/09/2026)
- [x] **Correção de relevância de imagens** (fallback tópico-aware, remoção de "spacecraft" genérico do
      pool de fallback, logging de quando cai no fallback) — DONE (25/09/2026)
- [x] **Loop de feedback de SEO** (retenção real do YouTube Analytics → prompt do LLM de título/gancho) — DONE (25/09/2026)
- [x] **Fallback de conteúdo via notícias reais** (Spaceflight News API, com validação de imagem antes de usar) — DONE (25/09/2026)
- [x] ~~Shorts cortados automaticamente do vídeo longo (máx 58s)~~ — **REVERTIDO (26/09/2026)**: relatado
      problema real (track 21, roteiro de 94s ficava com o fim cortado no Short). Prioridade corrigida:
      o Short agora SEMPRE cobre a narração inteira, sem limite de duração - o vídeo se adapta ao
      tamanho do conteúdo, o conteúdo nunca é cortado pra caber num tempo fixo. `max_duration` removido
      de `video_build.build_video`.
- [x] **A/B testing de thumbnail** — DONE (25/09/2026): confirmado que `videoThumbnailImpressions`/
      `videoThumbnailImpressionsClickRate` (CTR real) estão na Analytics API desde jan/2026. Todo vídeo
      novo gera 2 variantes de thumbnail; alguns dias após publicar, troca pra B, compara CTR real do
      período antes/depois, e mantém a que ganhar - tudo automático, logado, sem API paga.

## Concorrência e ideias disruptivas (pesquisa de 25/09/2026, ver histórico do commit)
- [x] **Comentários reais como fonte de pauta** (YouTube Data API → resumo de perguntas recorrentes →
      prompt de sugestão de tema) — DONE (25/09/2026)
- [x] **Revisão de clareza por persona leigo** (segunda passada do LLM local simulando espectador sem
      conhecimento prévio, sinaliza trechos confusos antes da revisão humana) — DONE (25/09/2026)
- [x] **Corte alinhado à cena** (Short não corta mais no meio de uma transição de imagem) — DONE (25/09/2026)
- [x] **Aprendizado por motivo de rejeição estruturado** — DONE (25/09/2026): tags rápidas de um clique
      (imagem não bate, gancho fraco, redundante, genérico demais) pré-preenchem o campo de observação.
- [x] **Matching de imagem por embeddings semânticos locais** — DONE (26/09/2026), aprovado pelo dono.
      `fastembed` (BAAI/bge-small-en-v1.5, ONNX, sem PyTorch, ~65MB, cacheado em
      `data/assets/embedding_model/`). Toda imagem que a busca por palavra-chave (NASA/ESA) retorna
      agora passa por uma checagem de relevância semântica (threshold 0.60, calibrado com pares
      reais bons/ruins) antes de ser aceita - imagens sem relação real com o tema são rejeitadas em
      vez de aceitas cegamente. Testado reproduzindo o bug original de verdade: busca por "Dawn
      spacecraft" contra um roteiro de nebulosa - as 6 imagens (todas "Dawn Spacecraft Processing")
      foram corretamente rejeitadas pelo filtro. Falha aberta (não bloqueia geração) se o modelo não
      carregar por qualquer motivo.
      **Validado em produção (26/09/2026, track 23):** geração real via fallback de notícia (Starliner/
      Boeing) escolheu imagens genuinamente relacionadas ("Boeing's Starliner CST-100", "International
      Space Station Update") - sem nenhuma imagem de "spacecraft processing" ou afins.
- [x] **Score de qualidade agregado** — DONE (26/09/2026): cruza fact-check + revisão de clareza +
      relevância média de imagem num badge único (0-100) visível no grid, modal e página do vídeo.
      Track 23 (validação) tirou 70/100 - detalhamento: fatos 35/35 (ok), clareza 15/35 (revisão
      apontou trecho redundante), imagens 20/30 (relevância média 0.67).
- [x] **Checador de repetição de hook/título** — DONE (26/09/2026), pesquisa de mercado confirmou que
      o YouTube passou a penalizar reciclagem de hook/formato entre uploads do mesmo canal em 2026.
      Reaproveita o fastembed já integrado: compara título/gancho do vídeo novo contra os últimos 20
      títulos do canal (`semantic.max_similarity`, threshold 0.85 calibrado com pares reais). Vira o
      4º componente do score de qualidade ("Diversidade", pesos rebalanceados pra fatos 30/clareza
      30/imagens 25/diversidade 15 = 100). Validado com um par real já existente no histórico do canal
      (dois títulos sobre "velocidade da luz" de gerações repetidas) - similaridade 0.853, corretamente
      no limite de detecção.
- [ ] **Inverter ordem: confirmar imagem disponível antes de narrar aquele trecho** — DEFERIDO
      deliberadamente: é uma mudança arquitetural grande (reescreve a ordem roteiro→imagem→narração)
      com risco real de quebrar o pipeline inteiro se malfeita sem revisão de design humana. Candidato
      a uma sessão própria, não a um ciclo autônomo. Esforço: L.
- [x] **Painel de confiança científica dedicado** — DONE (25/09/2026): o campo DETALHES do fact-check
      (antes descartado) agora é salvo e mostrado ao revisor junto do selo ok/atenção.
- [x] **"Revisado por IA + humano" como diferencial exposto** — já estava na descrição de upload
      (`_build_description`) desde antes; confirmado, nenhuma ação necessária.

## Próximos 2-3 trimestres
- [x] **Framework de fontes de conteúdo plugável** — DONE (26/09/2026). APOD/notícia/rotação viraram
      funções no formato `(channel, api_key) -> dict | None` numa lista `CONTENT_SOURCES` (`script_gen.
      py`) - adicionar uma fonte nova (ex.: RSS de outro nicho) é só escrever a função e colocar na
      lista, sem tocar na cascata. Testado ponta a ponta sem regressão (mesmo comportamento de antes,
      fonte de notícia escolhida corretamente, série/fact-check consistentes).
- [x] **Gestão de comentários (moderação + resposta sugerida)** — DONE (26/09/2026). Pesquisa de
      mercado confirmou spam de bot (com substituição de caracteres Unicode pra escapar de filtro) é
      dor real e crescente em 2026. Heurística local (`pipeline/spam_detection.py`, sem LLM/API paga):
      link, frases-gatilho, excesso de emoji, mistura de alfabetos (homóglifos), mensagem duplicada do
      mesmo autor em vídeos diferentes. Comentários com score ≥40 aparecem primeiro na tela, com botão
      "Ocultar (spam)" (`comments.setModerationStatus`) - sempre um clique explícito, nunca automático.
- [x] **Robustez de token OAuth** — DONE (26/09/2026). Pesquisa de mercado (rodada 3) apontou
      expiração silenciosa de token como a falha mais citada em automações solo do YouTube em 2026.
      Achado real no código: quando o refresh do token falhava (revogado, ou app em modo "Testing"),
      o pipeline caía silenciosamente pro fluxo interativo de login por navegador - que TRAVA pra
      sempre num contexto sem tela (worker da fila, tarefa agendada às 3h). Corrigido: falha de
      refresh agora levanta erro claro e imediato ("reautorize esse canal") em vez de travar. Health
      check diário também ganhou alerta destacado (toast) específico pra esse caso. Testado com um
      token forjado (refresh_token inválido) - confirma erro claro em vez de travamento.
- [ ] **Feedback de retenção com corte de 70% em Shorts** — pesquisa (rodada 3) achou que a
      distribuição de Shorts depende de bater ~70% de retenção nos primeiros 30-60min. Estender o
      few-shot já existente pra marcar vídeos abaixo desse corte como exemplo negativo explícito
      ("hook fraco"), usando dados já coletados da Analytics API. Esforço: S. Sem API nova.
- [ ] **Aviso de janela crítica de publicação** — sugerir automaticamente o horário de publicação com
      maior chance de engajamento nos primeiros 30-60min, usando dados históricos já acessíveis via
      Analytics API por canal. Puramente informativo. Esforço: S/M.
- [ ] **Upgrade opcional de LLM/TTS em nuvem** — prioridade baixa, contraria design local-first/grátis;
      só faz sentido se qualidade virar gargalo real. Esforço: S/M. **Requer API paga.**
- ~~Repurposing multi-plataforma (TikTok/Reels)~~ — fora de escopo por decisão explícita do dono.

## Mais adiante / exploratório
- [ ] Fila multi-worker (paralelizar geração entre canais). Esforço: L.
- ~~Posts de comunidade (Community tab) automatizados~~ — INVIÁVEL (verificado 26/09/2026 via
  pesquisa): a YouTube Data API v3 não expõe NENHUM endpoint pra criar post na Community tab, é recurso
  exclusivo do Studio. Só existiria via scraper não-oficial/serviço terceiro, o que contraria o
  princípio do projeto (só API oficial, sem risco de ToS). Removido da fila até o Google abrir a API.
- [ ] Painel de conformidade de licenciamento de imagens/mídia — reavaliado (26/09/2026): valor baixo
  no momento, porque as únicas fontes de imagem hoje (NASA Images API e ESA/Hubble) já são
  consistentemente domínio público / CC BY 4.0 - não há ambiguidade real de licença pra um painel
  resolver ainda. Voltaria a fazer sentido só se uma fonte de imagem com licença mista for adicionada
  no futuro. Esforço: M/L, baixa prioridade por ora.
- [ ] SaaS multi-tenant — fora do escopo atual (ferramenta local single-tenant). Esforço: L.
