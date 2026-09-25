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
- [ ] **Shorts cortados automaticamente do vídeo longo** (em vez de render paralelo desconectado) —
      **RECOMENDADO COMO PRÓXIMO ITEM**. Reduz risco de ser lido como "conteúdo em massa"; usa produção
      já existente. Esforço: M. Sem API paga (ffmpeg local + roteiro/transcrição já disponíveis).
- [ ] **A/B testing de título/thumbnail** — YouTube Data API já permite trocar thumbnail/título por
      período e comparar CTR/retenção. Esforço: M. Sem API paga.

## Próximos 2-3 trimestres
- [~] **Framework de fontes de conteúdo plugável** (APOD → notícia → rotação fixa, hoje é cascata
      hardcoded) — PARCIAL, falta abstrair como estratégias intercambiáveis. Esforço: M.
- [ ] **Gestão de comentários** (moderação + respostas sugeridas via YouTube Data API) — sinal de
      supervisão humana que o YouTube agora valoriza. Esforço: M. Sem API paga.
- [ ] **Upgrade opcional de LLM/TTS em nuvem** — prioridade baixa, contraria design local-first/grátis;
      só faz sentido se qualidade virar gargalo real. Esforço: S/M. **Requer API paga.**
- ~~Repurposing multi-plataforma (TikTok/Reels)~~ — fora de escopo por decisão explícita do dono.

## Mais adiante / exploratório
- [ ] Fila multi-worker (paralelizar geração entre canais). Esforço: L.
- [ ] Posts de comunidade (Community tab) automatizados. Esforço: S/M.
- [ ] Painel de conformidade de licenciamento de imagens/mídia. Esforço: M/L.
- [ ] SaaS multi-tenant — fora do escopo atual (ferramenta local single-tenant). Esforço: L.
