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
- [ ] **Inverter ordem: confirmar imagem disponível antes de narrar aquele trecho** — DEFERIDO
      deliberadamente: é uma mudança arquitetural grande (reescreve a ordem roteiro→imagem→narração)
      com risco real de quebrar o pipeline inteiro se malfeita sem revisão de design humana. Candidato
      a uma sessão própria, não a um ciclo autônomo. Esforço: L.
- [x] **Painel de confiança científica dedicado** — DONE (25/09/2026): o campo DETALHES do fact-check
      (antes descartado) agora é salvo e mostrado ao revisor junto do selo ok/atenção.
- [x] **"Revisado por IA + humano" como diferencial exposto** — já estava na descrição de upload
      (`_build_description`) desde antes; confirmado, nenhuma ação necessária.

## Próximos 2-3 trimestres
- [~] **Framework de fontes de conteúdo plugável** (APOD → notícia → rotação fixa, hoje é cascata
      hardcoded) — PARCIAL, falta abstrair como estratégias intercambiáveis. Esforço: M.
- [ ] **Gestão de comentários (moderação + resposta sugerida)** — já lemos comentários (ver acima);
      falta responder/moderar. Esforço: M. Sem API paga.
- [ ] **Upgrade opcional de LLM/TTS em nuvem** — prioridade baixa, contraria design local-first/grátis;
      só faz sentido se qualidade virar gargalo real. Esforço: S/M. **Requer API paga.**
- ~~Repurposing multi-plataforma (TikTok/Reels)~~ — fora de escopo por decisão explícita do dono.

## Mais adiante / exploratório
- [ ] Fila multi-worker (paralelizar geração entre canais). Esforço: L.
- [ ] Posts de comunidade (Community tab) automatizados. Esforço: S/M.
- [ ] Painel de conformidade de licenciamento de imagens/mídia. Esforço: M/L.
- [ ] SaaS multi-tenant — fora do escopo atual (ferramenta local single-tenant). Esforço: L.
