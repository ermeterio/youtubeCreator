# Pesquisa de fontes de imagens públicas (astronomia/ciência/espaço)

Histórico de execuções da rotina agendada de pesquisa de novas fontes de
imagem para o pipeline (`pipeline/visual_source.py`). Cada execução adiciona
uma seção no topo, sem apagar as anteriores.

---

## 2026-10-05 (quarta execução)

**Resultado: nenhuma fonte nova validada — bloqueio de rede confirmado pela
quarta execução consecutiva.**

Testes reais desta execução (mesma metodologia das execuções anteriores:
`WebFetch` e `Bash`/`curl` via proxy de egress, que é diferente do caminho
usado pelo `WebSearch`):
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  (fonte já em produção) → `EGRESS_BLOCKED`.
- `WebFetch` em `https://commons.wikimedia.org/w/api.php?action=query&...`
  (candidato pendente) → `EGRESS_BLOCKED`.
- `curl --cacert /root/.ccr/ca-bundle.crt` para `images-api.nasa.gov` e
  `api.si.edu` → `CONNECT tunnel failed, response 403`
  (`connect_rejected (organization policy)`, confirmado em
  `$HTTPS_PROXY/__agentproxy/status`).
- `curl` para dois domínios adicionais testados nesta execução,
  `www.sciencebase.gov` e `services.swpc.noaa.gov` (ver candidatos abaixo)
  → mesmo erro `connect_rejected (organization policy)`. Ou seja, o
  bloqueio continua sendo geral (política da organização, `selective:
  false` no status do proxy), não uma lista de domínios liberados faltando
  alguns nomes específicos.

Como o teste real (critério 1) permanece impossível para qualquer domínio,
usei `WebSearch` (que não passa pelo proxy de egress bloqueado) para
**refinar dois candidatos já pendentes**, sem poder validá-los de verdade:

### USGS ScienceBase (Astrogeology) — endpoint de busca agora confirmado por pesquisa (ainda não testado)
- Execuções anteriores não tinham confirmado um endpoint de busca textual
  equivalente ao `images-api.nasa.gov`. Pesquisa desta execução (WebSearch,
  incluindo a documentação oficial `usgs.gov/sciencebase-instructions-and-
  documentation/building-search-queries`) confirma que existe, de fato:
  `https://www.sciencebase.gov/catalog/items?q=<query>&format=json`
  (REST, sem chave, resultado JSON, parâmetros `max`/`offset` em
  incrementos de 5, máximo de 1000 por página).
- Licença: produtos de missões planetárias da USGS/Astrogeology são
  domínio público (produto do governo dos EUA), na linha do que já é usado
  para a NASA Images API.
- Integração esperada (ainda sem poder confirmar o formato exato de um
  item de imagem retornado, já que não consegui executar a chamada):
  `fetch_usgs_astrogeology_images_for_topic(query, count)` fazendo GET no
  endpoint acima, iterando os itens, extraindo a URL do arquivo/thumbnail
  de cada item e montando `VisualAsset(local_path=..., credit="USGS
  Astrogeology", title=item["title"])`.
- **Segue pendente**: não é possível confirmar se a busca por palavra-chave
  (`q=mars`/`q=moon`) retorna itens com URL de imagem direta e em volume
  relevante, ou só metadados de dataset sem imagem anexada — isso só é
  visível testando a chamada de verdade, o que o bloqueio de rede impediu
  novamente.

### NOAA SWPC (aurora) — candidato revisado, baixa prioridade
- Pesquisa desta execução localizou o serviço real: Space Weather
  Prediction Center, subdomínio `services.swpc.noaa.gov`, com imagens do
  mapa de probabilidade de aurora (hemisfério norte/sul) geradas
  periodicamente (ex. `.../images/aurora-forecast-northern-hemisphere.jpg`).
- Diferença importante em relação aos outros candidatos: isso não é uma
  fotografia real do fenômeno, e sim um **mapa/gráfico de previsão gerado
  por modelo** (visualização de dados, não imagem de câmera/telescópio).
  Rebaixa a relevância para o nicho do canal (o padrão do pipeline hoje é
  sempre imagem real do fenômeno/objeto, não infográfico de previsão).
- Licença: dados e produtos da NOAA/SWPC são trabalho do governo dos EUA,
  presumivelmente domínio público, mas não encontrei uma página de termos
  de uso explícita para este produto específico nesta pesquisa.
- Não encontrei nesta execução uma API da NOAA para **fotografias reais**
  de aurora (ex. do observatório ou de satélite) — só o mapa de previsão.
  **Mantido como candidato de baixa prioridade**, pendente de teste real e
  de achar (se existir) um acervo de fotos reais da NOAA, não só o mapa de
  previsão.

Candidatos ainda pendentes de teste real, sem mudança nesta execução:
Wikimedia Commons API (filtro de licença por item) e Smithsonian Open
Access API (`api.si.edu/openaccess`, CC0, chave gratuita via
api.data.gov — reconfirmado por pesquisa nesta execução, mesmos detalhes
já registrados nas execuções anteriores).

Ação recomendada continua a mesma, agora com mais urgência (4 execuções
seguidas sem conseguir validar nada de verdade por bloqueio de rede): mudar
"Network access" do ambiente cloud desta rotina para incluir pelo menos os
domínios já usados em produção (`images-api.nasa.gov`, `api.nasa.gov`,
`esahubble.org`, `eso.org`, `noirlab.edu`, `api.spaceflightnewsapi.net`)
mais os domínios dos candidatos pendentes (`commons.wikimedia.org`,
`api.si.edu`, `www.sciencebase.gov`), ou um nível de acesso mais amplo.
Sem isso, esta rotina continuará apenas revisando bibliografia via
`WebSearch`, sem conseguir cumprir o critério de teste real pedido.

**Nenhuma fonte nova encontrada em 2026-10-05** — bloqueio de rede
confirmado pela quarta vez consecutiva (agora também testado em dois
domínios adicionais, `sciencebase.gov` e `swpc.noaa.gov`, com o mesmo
resultado `connect_rejected (organization policy)`); avanço desta execução
foi só bibliográfico: endpoint de busca do USGS ScienceBase confirmado por
pesquisa (antes não localizado) e candidato NOAA/aurora revisado e
rebaixado por não ser fotografia real do fenômeno.

---

## 2026-10-02 (terceira execução, 21:46 UTC)

**Resultado: nenhuma fonte nova validada — bloqueio de rede confirmado pela
terceira vez consecutiva (20:53, 21:11 e agora 21:46 UTC).**

Testes reais desta execução:
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  → `EGRESS_BLOCKED`.
- `WebFetch` em `https://api.si.edu/openaccess/api/v1.0/search?q=astronomy...`
  → `EGRESS_BLOCKED`.
- `curl --cacert /root/.ccr/ca-bundle.crt https://images-api.nasa.gov/...`
  (via Bash, mesmo proxy de egress) → `CONNECT tunnel failed, response 403`,
  motivo reportado pelo proxy: `connect_rejected (organization policy)`.
  Confirma que é bloqueio de política da organização no proxy de egress, não
  uma falha de rede comum nem limitação só do WebFetch — nem Bash/curl passam.

Como o teste real (critério 1) continua impossível para qualquer domínio,
não investiguei candidatos 100% novos nesta execução (seria só bibliografia
sem validação, repetindo o problema das execuções anteriores). Em vez disso,
usei o `WebSearch` (que não passa pelo proxy de egress bloqueado) para
**revisar e corrigir** um candidato já levantado, já que isso é verificável
sem a rede de egress:

### Correção: Flickr API ("NASA on The Commons") — rebaixado de "promissor" para "descartado"
- A pesquisa anterior (ver seção de 2026-10-02, execução original) registrou
  a Flickr API como candidato promissor, assumindo "chave gratuita simples".
- Pesquisa desta execução (WebSearch, múltiplas fontes incluindo o próprio
  Help Center da Flickr) mostra que isso **mudou**: a possibilidade de
  solicitar uma API key agora é **exclusiva de assinantes Flickr Pro**
  (conta paga) — contas gratuitas não conseguem mais gerar chave de API.
  Contas gratuitas também têm download de imagens originais/grandes
  (>1024px) restrito via API.
- Isso viola diretamente o critério 2 da pesquisa (chave gratuita com
  cadastro simples é aceitável; chave paga não é). **Candidato descartado.**
- Ação: não vale a pena testar o endpoint real do Flickr em uma próxima
  execução com rede liberada, a menos que a política da Flickr mude de
  novo — not pending anymore, encerrado.

Candidatos ainda pendentes de teste real (sem mudança desde a execução
anterior, ver seções abaixo): Wikimedia Commons API, Smithsonian Open
Access API, USGS Astrogeology/ScienceBase (endpoint de busca por
palavra-chave ainda não confirmado via WebSearch nesta execução — resultados
mostraram apenas itens de catálogo individuais e serviços WMS/WCS, não um
endpoint JSON de busca textual equivalente ao `images-api.nasa.gov`).

Ação recomendada continua igual, agora com mais urgência (3 execuções
seguidas sem conseguir validar nada de verdade): mudar "Network access" do
ambiente cloud desta rotina para incluir pelo menos os domínios já usados em
produção (`images-api.nasa.gov`, `api.nasa.gov`, `esahubble.org`, `eso.org`,
`noirlab.edu`, `api.spaceflightnewsapi.net`) mais os domínios dos candidatos
pendentes (`commons.wikimedia.org`, `api.si.edu`, `www.sciencebase.gov`), ou
um nível de acesso mais amplo. Sem isso, esta rotina continuará apenas
revisando bibliografia via WebSearch, sem conseguir cumprir o critério de
teste real.

Durante esta execução, chegou uma mensagem dizendo que o "egress" teria
sido habilitado. Re-testei imediatamente após a mensagem, com os mesmos
métodos (WebFetch e curl/Bash via proxy) e também em um domínio adicional
(`commons.wikimedia.org`, não testado antes nesta execução): os três
domínios (`images-api.nasa.gov`, `api.si.edu`, `commons.wikimedia.org`)
continuaram retornando `EGRESS_BLOCKED` / `403 connect_rejected (organization
policy)`. Ou seja, o bloqueio persiste mesmo após o aviso — possivelmente a
mudança de configuração do ambiente precisa de uma sessão/container novo
para valer (este container já estava rodando), ou a mudança ainda não foi
aplicada do lado do proxy. Reportado ao usuário para verificação, já que não
dá pra confirmar liberação de rede só por uma mensagem — é preciso o teste
real continuar passando.

**Nenhuma fonte nova encontrada em 2026-10-02 (21:46 UTC)** — bloqueio de
rede confirmado novamente (agora também via Bash/curl, não só WebFetch, e
reconfirmado após aviso de que o egress teria sido habilitado); único
resultado concreto desta execução foi a correção do candidato Flickr
(rebaixado para descartado por exigir conta paga).

---

## 2026-10-02 (segunda execução, 21:11 UTC)

**Resultado: nenhuma fonte nova validada — mesmo bloqueio de rede da
execução anterior (20:53 UTC), ainda em vigor ~18 min depois.**

Re-testei via WebFetch nesta execução (não apenas repeti a conclusão
anterior):
- `https://images-api.nasa.gov/search?q=nebula` → `EGRESS_BLOCKED`
- `https://commons.wikimedia.org/w/api.php?...` → `EGRESS_BLOCKED`
- `https://api.si.edu/openaccess/api/v1.0/search?...` → `EGRESS_BLOCKED`

Os três domínios acima falharam da mesma forma (erro `EGRESS_BLOCKED` do
proxy de egress da organização, não um erro específico de cada API), o que
confirma que é um bloqueio geral de rede do ambiente desta sessão, e não
um problema pontual de um domínio. `WebSearch` (que não passa pelo mesmo
proxy de egress) continua funcionando normalmente, então a pesquisa por
candidatos (não o teste real exigido) ainda é possível — ver candidatos já
levantados na seção anterior abaixo, que seguem válidos e pendentes de
teste real.

Não investiguei candidatos adicionais à lista já existente nesta execução
porque, sem conseguir validar nem os endpoints já em produção, não haveria
como cumprir o critério 1 (teste real) para nenhum candidato novo — repetir
a mesma pesquisa bibliográfica sem poder testar nada não agregaria
informação nova. Ação recomendada continua a mesma da execução anterior:
ajustar "Network access" do ambiente cloud (Custom + allowlist dos domínios
usados pelo pipeline, ou um nível de acesso mais amplo) para que a próxima
execução consiga de fato validar algum endpoint.

**Nenhuma fonte nova encontrada em 2026-10-02 (21:11 UTC)** — bloqueio de
rede confirmado novamente, candidatos pendentes inalterados (ver seção
anterior).

---

## 2026-10-02

**Resultado desta execução: nenhuma fonte nova validada.** O ambiente de
execução desta rotina (sessão cloud) bloqueia egress de rede para qualquer
domínio externo não listado na allowlist da organização — isso foi
confirmado tentando buscar `https://images-api.nasa.gov/search?q=nebula`
(fonte que **já está em produção** no pipeline) via WebFetch, que retornou
`EGRESS_BLOCKED`. Ou seja, nem os endpoints já integrados e funcionando
puderam ser re-testados nesta sessão, então não é seguro afirmar que algum
endpoint novo "funciona de verdade" — o critério de validação pedido
(teste real, não só citar que existe) não pôde ser cumprido para nenhum
candidato.

Isso é uma limitação do ambiente desta execução específica, não uma
conclusão sobre as fontes em si. Ação recomendada para quem configura a
rotina: no menu do ambiente cloud, em "Network access", mudar para acesso
mais amplo ou adicionar os domínios abaixo (e os já usados pelo pipeline)
à lista "Allowed domains" em modo Custom, para que a próxima execução
consiga validar endpoints de verdade.

Candidatos levantados via pesquisa (WebSearch, não via WebFetch/teste real)
nesta execução, para validação na próxima vez que o ambiente tiver rede
liberada:

### Wikimedia Commons API — candidato promissor, falta validar
- URL base: `https://commons.wikimedia.org/w/api.php`
- Chamada esperada (não testada nesta sessão): `?action=query&format=json&generator=search&gsrnamespace=6&gsrsearch=nebula&gsrlimit=8&prop=imageinfo&iiprop=url|extmetadata|size&iiurlwidth=1280`
- Sem chave, público.
- Licença: **variável por arquivo** — a maior parte da categoria
  astronomia é CC BY/CC BY-SA/domínio público/NASA, mas o Commons também
  hospeda material com licença não permissiva ou "fair use" em alguns
  casos raros. Qualquer integração precisaria filtrar
  `extmetadata.LicenseShortName` / `UsageTerms` por item e descartar
  qualquer coisa que não seja CC0/CC BY/CC BY-SA/PD antes de baixar.
- Integração esperada: uma `fetch_wikimedia_commons_images_for_topic(query, count)`
  que faz o GET acima, filtra por licença permissiva no loop de itens, baixa
  a `imageinfo[0].url` e monta `VisualAsset(local_path=..., credit=extmetadata.Artist/Credit, title=...)`.
- **Pendente**: confirmar no próximo ciclo com rede liberada que o endpoint
  responde e que o filtro de licença captura corretamente o essencial.

### Flickr API (conta "NASA on The Commons") — candidato promissor, falta validar
- URL base: `https://api.flickr.com/services/rest/`
- Precisa de chave gratuita (cadastro simples em flickr.com/services/apps/create/).
- Licença: fotos do NASA on The Commons são publicadas sem restrição de
  copyright (compromisso do programa Flickr Commons), compatível com uso
  comercial com crédito.
- Integração esperada: `flickr.photos.search` filtrando `user_id` da conta
  oficial da NASA no Commons, baixando a maior URL disponível (`url_o`/`url_l`).
- **Pendente**: validar chamada real e formato de resposta; confirmar que a
  chave gratuita realmente não exige cartão/aprovação manual demorada.

### USGS Astrogeology Science Center (ScienceBase) — candidato a investigar melhor
- Imagens (fotojornal de missões planetárias) são domínio público (produto
  do governo dos EUA), hospedadas via catálogo ScienceBase
  (`https://www.sciencebase.gov/catalog/...`), que tem API REST própria.
- Não foi possível nesta execução confirmar um endpoint de busca por
  palavra-chave equivalente ao `images-api.nasa.gov` (a navegação encontrada
  foi via itens de catálogo individuais, não uma busca textual simples).
- **Pendente**: pesquisar a API de busca do ScienceBase
  (`https://www.sciencebase.gov/catalog/items?q=...&format=json`) e testar
  se cobre bem o nicho (Marte, Lua, outros corpos planetários).

### Candidatos descartados nesta execução

- **JAXA** (agência espacial japonesa): tem arquivo digital de imagens, mas
  a política de uso permite apenas fins não-comerciais/educacionais com
  crédito — uso comercial exige permissão prévia do titular dos direitos.
  Não atende ao requisito de licença (uso comercial com atribuição), então
  não dá para integrar sem contato manual caso a caso. Descartado.
- **Chandra X-ray Observatory (chandra.harvard.edu/photo)**: não foi
  encontrada evidência de uma API/endpoint JSON de busca (diferente de
  ESA/Hubble/ESO/NOIRLab, que compartilham a mesma plataforma AVM). Parece
  ser só página HTML tradicional. Sem um endpoint real e testável, não
  atende ao critério 1. Poderia valer re-checar manualmente (talvez exista
  endpoint não documentado, como no caso do ESA/ESO/NOIRLab), mas não nesta
  execução.
- **Unsplash API / Pexels API**: descartados por baixa relevância ao nicho
  (bancos de fotos genéricos, não teriam cobertura consistente de
  astronomia/fenômenos cósmicos específicos) e por licença de atribuição
  diferente do padrão CC já usado no pipeline (Unsplash License / Pexels
  License são permissivas para uso comercial, mas não são CC propriamente
  ditas — exigiria lógica de crédito separada). Não investigados a fundo
  por não serem prioridade dado o foco do canal.
- **NOAA (aurora/fenômenos espaciais vistos da Terra)**: não investigado a
  fundo nesta execução por falta de acesso de rede para confirmar
  endpoint/licença; ficou de fora do escopo desta rodada.
- **Smithsonian Open Access API**: confirmado por pesquisa (não por teste
  direto) que existe API real (`api.si.edu/openaccess`, chave gratuita via
  api.data.gov) com licença CC0 explícita, incluindo acervo do
  Center for Astrophysics | Harvard & Smithsonian. É um candidato forte
  para a próxima execução, mas fica pendente de teste real do endpoint
  (não pôde ser feito nesta sessão por bloqueio de rede) e de confirmar que
  a busca por palavra-chave (`q=astronomy`/`q=nebula`) retorna resultados
  relevantes em volume suficiente.

**Nenhuma fonte nova encontrada/validada em 2026-10-02** (bloqueio de rede
impediu o teste real exigido; candidatos documentados acima para retomar
na próxima execução).
