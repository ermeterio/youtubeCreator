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

## Agora / próximo trimestre
- [x] **Divulgação de IA correta** (`containsSyntheticMedia`) — DONE (25/09/2026)
- [x] **Correção de relevância de imagens** (fallback tópico-aware, remoção de "spacecraft" genérico do
      pool de fallback, logging de quando cai no fallback) — DONE (25/09/2026)
- [x] **Loop de feedback de SEO** (retenção real do YouTube Analytics → prompt do LLM de título/gancho) — DONE (25/09/2026)
- [x] **Fallback de conteúdo via notícias reais** (Spaceflight News API, com validação de imagem antes de usar) — DONE (25/09/2026)
- [x] **Shorts cortados automaticamente do vídeo longo** (mesmo Ken Burns/narração até o ponto de
      corte, corte alinhado à troca de imagem mais próxima, não meio de crossfade) — DONE (25/09/2026)
- [ ] **A/B testing de título/thumbnail** — DEFERIDO por incerteza real: não confirmei se a YouTube
      Analytics API v2 expõe impressões/CTR verdadeiros (métrica que sustentaria a comparação) pra
      apps de terceiros, só retenção/views/likes. Implementar às cegas arriscava um recurso que
      parece funcionar mas mede a coisa errada. Precisa de uma sessão dedicada de verificação contra
      a documentação oficial antes de codar. Esforço: M. Sem API paga (se a métrica existir).

## Concorrência e ideias disruptivas (pesquisa de 25/09/2026, ver histórico do commit)
- [x] **Comentários reais como fonte de pauta** (YouTube Data API → resumo de perguntas recorrentes →
      prompt de sugestão de tema) — DONE (25/09/2026)
- [x] **Revisão de clareza por persona leigo** (segunda passada do LLM local simulando espectador sem
      conhecimento prévio, sinaliza trechos confusos antes da revisão humana) — DONE (25/09/2026)
- [x] **Corte alinhado à cena** (Short não corta mais no meio de uma transição de imagem) — DONE (25/09/2026)
- [x] **Aprendizado por motivo de rejeição estruturado** — DONE (25/09/2026): tags rápidas de um clique
      (imagem não bate, gancho fraco, redundante, genérico demais) pré-preenchem o campo de observação.
- [ ] **Matching de imagem por embeddings semânticos locais** (sentence-transformers, roteiro→imagem por
      similaridade em vez de keyword) — DEFERIDO: exige instalar uma dependência de ML pesada nova no
      ambiente local, decisão que merece confirmação explícita antes de baixar/instalar algo grande
      sem supervisão. Esforço: M, 100% local se aprovado.
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
