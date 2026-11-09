# Pesquisa de fontes de imagens públicas (astronomia/ciência/espaço)

Histórico de execuções da rotina agendada de pesquisa de novas fontes de
imagem para o pipeline (`pipeline/visual_source.py`). Cada execução adiciona
uma seção no topo, sem apagar as anteriores.

---

## 2026-11-09 (nona execução)

**Resultado: nenhuma fonte nova validada por teste real (critério 1 segue
impossível) — bloqueio de rede confirmado pela nona execução consecutiva.
Mas esta execução encontra o mecanismo exato do bloqueio (não só "política
geral da organização") e tenta corrigi-lo diretamente.**

### Causa-raiz do bloqueio identificada com precisão nesta execução
Execuções anteriores só tinham o sintoma (403 no CONNECT, DNS não resolve,
`"selective": false` no status do proxy). Nesta execução, `get_environment`
(ferramenta do host, não parte do pipeline) foi consultada e mostra a causa
exata: o ambiente cloud desta rotina ("Default", pessoal, é o ambiente padrão
de todas as sessões) está com `network.type = "limited"` e
**`allowed_hosts: []` — lista vazia**. Só `allow_package_managers` e
`allow_mcp_servers` estão ligados. Ou seja, nenhum host de API arbitrário
está liberado, **incluindo os domínios já em produção**
(`images-api.nasa.gov`, `api.nasa.gov`, `esahubble.org`, `esawebb.org`,
`www.eso.org`, `noirlab.edu`, `api.spaceflightnewsapi.net` — confirmados no
código-fonte de `pipeline/visual_source.py`). Testes reais desta execução:
- `curl --cacert /root/.ccr/ca-bundle.crt` para `images-api.nasa.gov`,
  `commons.wikimedia.org`, `api.openverse.org`, `api.si.edu` → todos
  `CONNECT tunnel failed, response 403`.
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  → `getaddrinfo ENOTFOUND images-api.nasa.gov`, com a mensagem do harness
  confirmando que o host "falha a resolver assim quando está fora dos
  domínios permitidos da sessão" — ou seja, a própria ferramenta confirma
  que é allowlist, não falha de rede genérica.

### Tentativa de correção nesta execução (bloqueada por falta de aprovação humana síncrona)
Como o ambiente é editável por este usuário e não está salvo pra nenhum
repositório específico (`saved_for_session_repositories: []`), a ação
correta (por instrução do próprio host) é propor um ambiente pessoal novo
dedicado a este repositório, não editar o "Default" (que afeta todas as
sessões do usuário). Chamei `create_environment` propondo um ambiente
"youtubeCreator" com os 7 domínios já em produção + os principais candidatos
pendentes (`commons.wikimedia.org`, `upload.wikimedia.org`, `api.si.edu`,
`api.openverse.org`, `www.sciencebase.gov`, `cxc.harvard.edu`,
`svs.gsfc.nasa.gov`) e pedindo para esta sessão trocar de rede
imediatamente. **Resultado: recusado** — a chamada exige aprovação humana
síncrona ("a person's approval"), e esta é uma execução agendada automática,
sem ninguém presente para aprovar. A ferramenta instruiu explicitamente a
não tentar de novo e a registrar o bloqueio em vez de contornar.

**Ação necessária do usuário (a mais concreta já registrada nas nove
execuções)**: abrir esta rotina manualmente ("Run now" / executar agora) em
uma sessão interativa e aprovar o prompt de criação/troca de ambiente — ou,
de forma equivalente, ir em Settings do ambiente cloud e adicionar os hosts
acima à allowlist do ambiente "Default" (ou de um ambiente pessoal dedicado
a este repositório). Qualquer uma das duas resolve o bloqueio que já dura 9
execuções (mais de 2 meses).

### NASA Mars Rover Photos API + NASA EPIC API — candidato novo, forte, sem necessidade de domínio/chave novos
Pesquisa via `WebSearch` (não dá pra confirmar com teste real pelo motivo
acima) encontra dois recursos adicionais da própria família de APIs já em
produção sob `api.nasa.gov` (mesma chave gratuita já obtida pro APOD,
mesmo domínio já na allowlist de produção quando o bloqueio for resolvido):
- **Mars Rover Photos**: `GET https://api.nasa.gov/mars-photos/api/v1/rovers/<rover>/photos?sol=<n>&api_key=<key>`
  (ou `earth_date=YYYY-MM-DD` em vez de `sol`; também existe
  `/latest_photos`). Resposta JSON com array `photos[]`, cada item com
  `img_src` (URL direta da imagem), `earth_date`, `rover`, `camera`. Fotos
  reais dos rovers (Curiosity, Perseverance, Opportunity, Spirit) —
  altamente relevante pro nicho (exploração de Marte).
- **EPIC (Earth Polychromatic Imaging Camera, satélite DSCOVR)**: via o
  espelho já dentro do domínio de produção,
  `GET https://api.nasa.gov/EPIC/api/natural/images?api_key=<key>` (lista
  imagens disponíveis, cada item com campo `image`, ex.
  `epic_1b_20151031074844`) e a URL do arquivo é montada como
  `https://api.nasa.gov/EPIC/archive/natural/<yyyy>/<mm>/<dd>/png/<image>.png?api_key=<key>`.
  Imagens reais do disco completo da Terra — relevante pro nicho em vídeos
  sobre observação da Terra/clima espacial, menos central que Marte mas
  ainda dentro do escopo "ciência espacial".
- **Licença**: mesma política geral da NASA já aceita para `images-api.nasa.gov`
  e para a APOD já em produção (conteúdo da NASA geralmente não tem
  copyright nos EUA, ressalvas já conhecidas pelo pipeline — pessoas
  identificáveis e conteúdo de terceiros marcado à parte). Não encontrei
  texto de licença específico por coleção (Mars Photos/EPIC não têm página
  de termos própria), mas é o mesmo domínio/guarda-chuva de uso já
  aceito — não é uma licença nova a avaliar.
- **Por que isto muda a prioridade da fila**: diferente de Openverse,
  Wikimedia Commons, Smithsonian etc. (que precisam de domínio novo na
  allowlist), Mars Rover Photos e EPIC usam o domínio e a chave que **já
  estão em produção**. Assim que o bloqueio de rede acima for resolvido por
  qualquer domínio (mesmo sem liberar os domínios novos pendentes), estas
  duas já ficam testáveis e integráveis sem nenhuma mudança de ambiente
  adicional. **Promovido ao topo da fila de candidatos**, acima do
  Openverse.
- **Integração esperada** (ainda não testada de verdade): duas funções novas
  no padrão já usado, `fetch_nasa_mars_photos_for_topic(query, count)` e
  `fetch_nasa_epic_images_for_topic(query, count)`, retornando
  `VisualAsset(local_path=..., credit="NASA/JPL-Caltech" ou "NASA EPIC Team",
  title=...)` — análogas à função já existente pra `images-api.nasa.gov`.
- **DONKI (Database Of Notifications, Knowledge, Information)**, terceiro
  recurso notável do mesmo domínio `api.nasa.gov`, **investigado e
  descartado para este propósito**: é um banco de eventos de clima espacial
  (CME, erupções solares, tempestades geomagnéticas) — a resposta JSON é
  metadado do evento (velocidade, tipo, horário, instrumento), não uma URL
  de imagem direta na maioria dos tipos de evento. Não encaixa no padrão
  `fetch_*_images_for_topic` (que precisa devolver uma imagem, não um
  registro textual).

### USGS Astrogeology Science Center — refinamento, mesma objeção do PDS Imaging Atlas
Pesquisa confirma uma API real e pública, `stac.astrogeology.usgs.gov/api`
(protocolo STAC — SpatioTemporal Asset Catalog), com busca GET/POST e
catálogo completo de dados planetários já carregado. Licença: uma página de
mídia da USGS sobre essa API está marcada "Public Domain"; a galeria de
imagens da Astrogeology diz que as imagens podem ser baixadas livremente
(com ressalva de que imagens de terceiros, quando presentes, são marcadas e
sujeitas a copyright). Não encontrei texto de licença específico cobrindo os
registros da API STAC em si. **Mesma objeção já registrada pro PDS Imaging
Atlas**: é dado científico bruto (rasters de análise, não fotos de
divulgação prontas), exigiria navegar metadados STAC/PDS4 complexos pra
extrair um arquivo de imagem útil — mantido como candidato de baixíssima
prioridade, mesmo nível do PDS Imaging Atlas, não vale o esforço antes de
esgotar os candidatos mais simples da fila.

### Helioviewer API (SDO/SOHO, imagens solares) — candidato novo, pendente de confirmação de licença
API real e documentada em `api.helioviewer.org/docs/v2/`, sem chave: `GET
/v2/takeScreenshot/` gera uma imagem/captura customizada (retorna JSON com
URL do arquivo quando `display` não é `true`) a partir de instrumentos como
SDO/AIA e SOHO — relevante pro nicho (fenômenos solares, uma categoria
frequente de vídeo do canal). **Mas a licença dos dados de imagem em si não
foi confirmada**: só encontrei a licença do código-fonte do projeto
(Mozilla Public License, em um espelho de terceiro do repositório, não a
fonte oficial) e nenhuma página de termos de uso do conteúdo de imagem.
Dados de instrumentos como SDO são geralmente domínio público (NASA/ESA),
mas isso precisa ser confirmado na documentação oficial antes de integrar —
**mantido como pendente, prioridade média**, atrás de Mars Rover
Photos/EPIC (sem ambiguidade de licença) mas na frente de USGS
Astrogeology/PDS (sem o problema de dado bruto não-fotográfico).

Candidatos pendentes sem mudança nesta execução: Openverse, Wikimedia
Commons, Smithsonian Open Access, Chandra (rebaixado), NOAA/aurora (baixa
prioridade), Europeana (baixa prioridade). Candidatos já descartados em
execuções anteriores (JAXA, Flickr direto, Unsplash, Pexels, DLR, Library of
Congress, Rubin Observatory, ESA JUICE/Solar Orbiter, NASA SVS) seguem
descartados.

**Nenhuma fonte nova encontrada em 2026-11-09** no sentido estrito do
critério 1 da tarefa (teste real) — bloqueio de rede confirmado pela nona
vez consecutiva, agora com a causa-raiz exata identificada
(`allowed_hosts: []` no ambiente cloud) e uma tentativa real de correção
feita (`create_environment`), recusada só por falta de aprovação humana
síncrona numa execução automática. Avanço bibliográfico desta execução:
Mars Rover Photos e EPIC identificados como o candidato mais forte de todas
as nove execuções (zero infraestrutura nova — mesmo domínio/chave já em
produção), Helioviewer API investigado como candidato novo de prioridade
média (licença de imagem pendente de confirmação), e USGS Astrogeology
refinado com a mesma objeção já aplicada ao PDS Imaging Atlas.

---

## 2026-11-02 (oitava execução)

**Resultado: nenhuma fonte nova validada — bloqueio de rede confirmado pela
oitava execução consecutiva.**

Testes reais desta execução:
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  (fonte já em produção) → `getaddrinfo ENOTFOUND images-api.nasa.gov`.
- `curl --cacert /root/.ccr/ca-bundle.crt` (via Bash, mesmo proxy de egress)
  para `https://commons.wikimedia.org/w/api.php?...` (candidato pendente) →
  `CONNECT tunnel failed, response 403`.
- `$HTTPS_PROXY/__agentproxy/status` consultado antes e depois dos testes:
  antes, `recentRelayFailures: []` (log limpo, mesmo padrão de não persistir
  entre sessões já notado na 7ª execução); depois do teste real, populado
  com `commons.wikimedia.org:443` → `connect_rejected` / "gateway answered
  403 to CONNECT (policy denial or upstream failure)". `"selective": false`
  confirma de novo que é bloqueio geral da organização, não allowlist
  incompleta — mesmo padrão das oito execuções, agora com mais de um mês.

Como o teste real (critério 1) permanece impossível, usei `WebSearch` para
refinar candidatos pendentes e investigar uma pista nova (ESA JUICE/Solar
Orbiter), sem conseguir validar nada de verdade:

### Openverse — refinamento de rate limit, ainda contraditório, pendente de teste real
- Pesquisa desta execução não encontrou a doc oficial atualizada (resultados
  deram só posts antigos e espelhos de terceiros). A única fonte oficial
  encontrada (post do blog do projeto, 2022) diz que requisição anônima com
  `page_size` acima do padrão (20) passou a devolver 401, após abuso com
  `page_size=500`; o mesmo post cita throttle de 1 req/s pra usuário anônimo.
  Um pacote npm de terceiros (servidor MCP não-oficial) contradiz isso,
  listando `page_size` máximo de 500 e limites de 100/dia + 5/hora — os
  mesmos números já citados em execuções anteriores, mas sem confirmação
  oficial. **Sem mudança de prioridade**: continua candidato mais promissor
  da fila, mas os números de limite seguem não confirmados contra a doc
  oficial (`api.openverse.org/v1/#tag/auth`), só testável com rede liberada.

### Smithsonian Open Access — DEMO_KEY e tier de chave registrada refinados
- Pesquisa desta execução (espelhos de terceiros da doc oficial, que
  continua inacessível sem rede) confirma: `DEMO_KEY` é explicitamente
  descrito como "sem cadastro, só para teste/avaliação inicial", com limite
  por IP (número exato não confirmado); chave registrada via api.data.gov
  tem tier padrão de 1000 requisições/hora, resetando de forma contínua
  (rolling); excesso retorna HTTP 429. Também existe um bucket S3 de dados
  em massa que não conta contra os limites de API (não relevante pro padrão
  de busca por tópico do pipeline, mas registrado). **Sem mudança de
  prioridade ou conclusão**: licença CC0 e chave gratuita já confirmadas em
  execuções anteriores, só os números de rate limit foram refinados — ainda
  pendente de teste real do endpoint de busca.

### ESA JUICE / Solar Orbiter (portal esa.int, fora da plataforma AVM) — investigado, descartado
- Pista nova desta execução: as galerias de imagens das missões JUICE e
  Solar Orbiter em `esa.int`/`sci.esa.int` são páginas HTML tradicionais
  (listagem com paginação por `offset`), sem endpoint JSON encontrado —
  diferente da plataforma AVM compartilhada por ESA/Hubble, ESA/Webb, ESO e
  NOIRLab (já em produção/validada), que é operada por um sistema de
  divulgação científica distinto do portal institucional geral da ESA.
- Licença também diferente: material dessas galerias aparece como CC BY-SA
  3.0 IGO (ou "ESA Standard Licence" como alternativa) — CC BY-SA exige
  compartilhamento pela mesma licença (share-alike), não é um problema para
  uso comercial com atribuição em si (atende ao critério 3), mas é uma
  licença diferente da CC BY 4.0 "limpa" já usada para os créditos das
  fontes AVM, então exigiria lógica de crédito/aviso de licença separada se
  fosse integrado.
- **Descartado**: sem API JSON própria (mesmo padrão de portal HTML já
  descartado para Chandra/Rubin), a plataforma AVM já cobre o conteúdo mais
  relevante da ESA em produção. Não vale o esforço de scraping de HTML para
  cobrir só mais duas missões específicas.

### NASA SVS (Scientific Visualization Studio) — reconfirmado sem endpoint de busca
- Pesquisa desta execução encontra evidência de que `svs.gsfc.nasa.gov/api/<id>`
  existe de fato (ex. `/api/40400`, `/api/13533`, aparecendo indexado em
  resultados de busca) — mas é uma API de **detalhe por ID** (GET de um
  item já conhecido), não uma busca por palavra-chave equivalente ao
  `images-api.nasa.gov/search?q=...`. Nenhuma pesquisa desta execução (duas
  tentativas, incluindo busca direta por "svs api search endpoint") encontra
  um endpoint de busca textual documentado para o SVS.
- **Não é uma fonte nova, reconfirma a conclusão da 7ª execução**: sem busca
  por palavra-chave, não dá pra integrar no padrão `fetch_*_images_for_topic`
  (que recebe um tópico/tema do roteiro, não um ID de item já conhecido).
  Registrado só para não reinvestigar do zero: se o SVS um dia expuser um
  endpoint de busca, revisar.

Candidatos pendentes sem mudança nesta execução (continuam bloqueados por
falta de rede para teste real): Wikimedia Commons API, Smithsonian Open
Access API, USGS ScienceBase, PDS Imaging Atlas (baixa prioridade), Chandra
(rebaixado), NOAA/aurora (baixa prioridade), Europeana (baixa prioridade,
relevância ao nicho incerta). Candidatos já descartados em execuções
anteriores (JAXA, Flickr direto, Unsplash, Pexels, DLR, Library of Congress,
Rubin Observatory, agora também ESA JUICE/Solar Orbiter) seguem descartados.

Ação recomendada: igual às sete execuções anteriores, agora com mais de um
mês de bloqueio ininterrupto (8 execuções seguidas sem conseguir validar
nada de verdade por bloqueio de rede de política da organização). Liberar
"Network access" do ambiente cloud desta rotina (allowlist incluindo os
domínios já em produção + `commons.wikimedia.org`, `api.si.edu`,
`www.sciencebase.gov`, `api.openverse.org`, ou um nível de acesso mais
amplo) continua sendo o único jeito de esta rotina conseguir cumprir o
critério de teste real pedido pela tarefa.

**Nenhuma fonte nova encontrada em 2026-11-02** (nenhuma validada por teste
real — bloqueio de rede confirmado pela oitava vez consecutiva, mais de um
mês seguido); avanço desta execução foi só bibliográfico: rate limits do
Openverse e do Smithsonian Open Access refinados (ainda sem confirmação
oficial no caso do Openverse), ESA JUICE/Solar Orbiter investigado e
descartado (sem API JSON, licença CC BY-SA 3.0 IGO diferente da AVM), e
NASA SVS reconfirmado sem endpoint de busca por palavra-chave (só API de
detalhe por ID).

---

## 2026-10-26 (sétima execução)

**Resultado: nenhuma fonte nova validada — bloqueio de rede confirmado pela
sétima execução consecutiva.**

Testes reais desta execução:
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  (fonte já em produção) → `getaddrinfo ENOTFOUND images-api.nasa.gov`.
- `curl --cacert /root/.ccr/ca-bundle.crt` (via Bash, mesmo proxy de egress)
  para `images-api.nasa.gov`, `commons.wikimedia.org`, `api.si.edu`,
  `www.sciencebase.gov` e `api.openverse.org` → todos com
  `CONNECT tunnel failed, response 403`. `$HTTPS_PROXY/__agentproxy/status`
  confirma `"selective": false` e registra os cinco domínios em
  `recentRelayFailures` como `connect_rejected` / "gateway answered 403 to
  CONNECT (policy denial or upstream failure)" — mesmo padrão geral das seis
  execuções anteriores. Diferença notada: o status consultado ANTES dos
  testes desta execução veio com `recentRelayFailures: []` (vazio, log
  provavelmente limpo entre execuções/containers), mas voltou a popular
  imediatamente com os mesmos erros assim que as chamadas reais foram
  tentadas — ou seja, não é sinal de que o bloqueio tenha sido removido,
  só que o log de falhas recentes não persiste entre sessões.

Como o teste real (critério 1) permanece impossível, usei `WebSearch` para
investigar candidatos adicionais além dos já pendentes, sem conseguir
validar nenhum de verdade:

### DLR (German Aerospace Center) — investigado, descartado
- Não existe API de galeria de imagens documentada. Os termos do portal
  (`dlr.de`) afirmam copyright do DLR sobre o conteúdo público por padrão,
  exigindo permissão prévia do titular pra uso. A única exceção encontrada
  (página do Institute of Future Fuels) usa CC BY-NC-ND 3.0 — license que
  proíbe uso comercial E derivados, não atende ao critério 3 de forma
  alguma. **Descartado**: sem API testável e sem licença compatível.

### Europeana API — investigado, baixa prioridade (não descartado, mas atrás da fila)
- API real e documentada (`api.europeana.eu/api/v2/search.json`), precisa
  de chave gratuita via cadastro simples (atende ao critério 2). Suporta
  filtro `reusability=open` (Domínio Público/CC0/CC BY/CC BY-SA) combinado
  com `qf=TYPE:IMAGE` — resolveria o problema de licença variável igual ao
  Openverse.
- Relevância ao nicho é a maior dúvida: é um agregador de patrimônio
  cultural europeu (museus, bibliotecas, arquivos) — não encontrei
  confirmação de que indexe acervo relevante de astronomia/ciência espacial
  em volume, só a garantia genérica de filtro por tipo/licença. Diferente
  do Openverse (que indexa Wikimedia Commons e Flickr Commons, fontes já
  conhecidas por ter bom acervo de astronomia), o conteúdo típico da
  Europeana é mais voltado a arte/história.
- **Mantido como candidato de baixa prioridade**, atrás de Openverse,
  Wikimedia Commons e Smithsonian Open Access — só vale testar de verdade
  se essas fontes mais prováveis continuarem bloqueadas por muitas
  execuções mais, e mesmo assim precisaria confirmar volume relevante de
  resultados pra `query=astronomy`/`query=nebula` antes de integrar.

### NASA SVS (Scientific Visualization Studio) — investigado, sem evidência de API própria
- Pesquisa não encontrou endpoint de busca JSON dedicado ao SVS
  (`svs.gsfc.nasa.gov`) — só a galeria HTML tradicional e uma entrada no
  catálogo data.gov sem API associada. Não há confirmação de que o
  conteúdo do SVS seja indexado pela `images-api.nasa.gov` (já em produção)
  separadamente do acervo geral. **Não é uma fonte nova**: fica registrado
  aqui só pra não precisar reinvestigar nas próximas execuções; se o SVS
  for coberto pela NASA Images API já em produção, não há ganho adicional
  em integrá-lo separadamente.

### Library of Congress API — investigado, descartado por falta de filtro de licença e de foco no nicho
- Existe API JSON real (`loc.gov/pictures/api?fo=json`, parte de
  `loc.gov/apis/json-and-yaml`), sem chave. Mas a pesquisa não encontrou um
  parâmetro de filtro por status de direitos (equivalente ao
  `reusability=open` da Europeana ou ao filtro de licença do Openverse) —
  cada item precisaria ter os direitos verificados manualmente, e o acervo
  é de fotografia histórica americana em geral, não astronomia/ciência
  espacial. **Descartado**: falta tanto filtro de licença automatizável
  quanto relevância ao nicho do canal.

### Openverse — refinamento (ainda pendente de teste real)
- Pesquisa desta execução encontra números de limite de taxa anônimo
  diferentes dos citados na execução anterior (100/dia + 5/hora, vs. uma
  fonte terceira agora citando os mesmos números mas também uma paginação
  anônima capada em ~240 resultados/12 páginas de 20) — ainda não confirmado
  contra a doc oficial (`api.openverse.org/v1/#tag/auth`), que não foi
  possível abrir por causa do bloqueio de rede. Os Termos de Serviço do
  Openverse proíbem "scraping" — não deve afetar o uso normal da API
  pública como já planejado (consumir o endpoint de busca documentado, não
  baixar o site via scraping), mas vale ter em mente ao implementar.
- Continua candidato mais promissor da fila (resolve o problema de licença
  variável e já indexa Wikimedia/Flickr Commons), sem mudança de prioridade.

Candidatos pendentes sem mudança nesta execução (continuam bloqueados por
falta de rede para teste real): Wikimedia Commons API, Smithsonian Open
Access API, USGS ScienceBase, PDS Imaging Atlas (baixa prioridade por
complexidade de parsing PDS4), Rubin Observatory (descartado por falta de
endpoint estruturado), Chandra (rebaixado, feed sem URL de imagem
estruturada), NOAA/aurora (baixa prioridade, mapa de previsão não é foto
real). Candidatos já descartados em execuções anteriores (JAXA, Flickr
direto, Unsplash, Pexels) seguem descartados.

Ação recomendada: igual às seis execuções anteriores, agora com mais
urgência ainda (7 execuções seguidas, quase 3 semanas, sem conseguir
validar nada de verdade por bloqueio de rede de política da organização).
Liberar "Network access" do ambiente cloud desta rotina (allowlist incluindo
os domínios já em produção + `commons.wikimedia.org`, `api.si.edu`,
`www.sciencebase.gov`, `api.openverse.org`, ou um nível de acesso mais
amplo) continua sendo o único jeito de esta rotina conseguir cumprir o
critério de teste real pedido pela tarefa.

**Nenhuma fonte nova encontrada em 2026-10-26** (nenhuma validada por teste
real — bloqueio de rede confirmado pela sétima vez consecutiva); avanço
desta execução foi só bibliográfico: DLR investigado e descartado (sem API,
licença CC BY-NC-ND não comercial), Europeana investigado como candidato de
baixa prioridade (API real com filtro de licença, mas relevância ao nicho
incerta), NASA SVS e Library of Congress investigados e descartados/sem
ganho adicional, e refinamento dos números de rate limit do Openverse
(ainda não confirmados contra a doc oficial).

---

## 2026-10-19 (sexta execução)

**Resultado: nenhuma fonte nova validada — bloqueio de rede confirmado pela
sexta execução consecutiva.**

Testes reais desta execução:
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  (fonte já em produção) → `getaddrinfo ENOTFOUND images-api.nasa.gov`.
- `curl --cacert /root/.ccr/ca-bundle.crt` para `images-api.nasa.gov` →
  `CONNECT tunnel failed, response 403`. `$HTTPS_PROXY/__agentproxy/status`
  confirma `"selective": false` e registra a falha em
  `recentRelayFailures` como `connect_rejected` / "gateway answered 403 to
  CONNECT (policy denial or upstream failure)" — mesmo padrão geral das
  cinco execuções anteriores, não específico de um domínio.
- `WebFetch` em `https://api.openverse.org/v1/images/?q=nebula&license=cc0,by,by-sa&page_size=5`
  (candidato novo desta execução, ver abaixo) → mesmo erro
  (`getaddrinfo ENOTFOUND api.openverse.org`), confirmando que o bloqueio
  também vale para domínios nunca testados antes nesta rotina, não só os
  já conhecidos.

Como o teste real (critério 1) permanece impossível, usei `WebSearch` para
levantar candidatos **genuinamente novos** (além de revisar o estado dos
pendentes), já que repetir só os mesmos quatro pendentes sem conseguir
testá-los não agregaria informação:

### Openverse API — candidato novo, promissor, pendente de teste real
- URL base: `https://api.openverse.org/v1/`. Endpoint principal:
  `GET /images/?q=<query>&license=cc0,by,by-sa&page_size=<n>` (também existe
  `/images/{identifier}/` para detalhe de um item e, segundo fontes
  terceiras, `/rate_limit/` para checar cota restante).
- Sem chave para uso anônimo básico (fontes terceiras, não a doc oficial —
  não consegui abrir `api.openverse.org` por causa do bloqueio de rede —
  divergem sobre o limite exato: uma cita 100 req/dia + 5/hora por IP,
  outra cita só "limite menor que usuário autenticado"; um post oficial do
  blog do projeto, de 2022, menciona cap de 20 resultados por página sem
  chave após um pico de tráfego). Chave gratuita opcional existe via
  cadastro simples, levantando o limite — mesmo padrão aceitável já usado
  pela NASA APOD.
- Relevância: não é um acervo próprio de astronomia, é um **agregador** de
  conteúdo com licença aberta que já indexa Wikimedia Commons e Flickr
  Commons (incluindo a conta oficial "NASA on The Commons", já descartada
  nesta pesquisa como fonte direta por exigir conta paga da Flickr — o
  Openverse contornaria isso, pois ele mesmo faz a raspagem e reindexação,
  o consumidor da API não precisa de chave da Flickr) além de museus/
  bibliotecas com material científico. Também herda o problema já
  registrado para o Wikimedia Commons: licença varia por item, então
  qualquer integração precisa filtrar pelo campo de licença por resultado
  (o parâmetro `license=cc0,by,by-sa` já faz isso na query, mas vale
  reconfirmar o campo de licença de cada item na resposta antes de baixar,
  e não só confiar no filtro de busca).
- Integração esperada (ainda não testada de verdade): uma
  `fetch_openverse_images_for_topic(query, count)` que faz o GET acima,
  itera `results[]`, pega `url`/`thumbnail` e monta
  `VisualAsset(local_path=..., credit=item["attribution"] ou item["creator"],
  title=item["title"])`.
- **Pendente**: confirmar endpoint, formato de resposta, licença exata por
  item e limite de taxa anônimo reais (nada disso foi confirmado contra a
  doc oficial, só contra espelhos/wrappers de terceiros, pela mesma razão
  de bloqueio de rede). Candidato forte para a próxima execução com rede
  liberada, por resolver de uma vez o problema de licença variável que já
  trava o candidato Wikimedia Commons sozinho.

### NASA PDS Imaging Atlas API (`pds-imaging.jpl.nasa.gov/tools/atlas/api`) — investigado, rebaixado por complexidade
- Pesquisa desta execução confirma uma API real e documentada
  (`pds-imaging.jpl.nasa.gov/tools/atlas/documentation/docs/api/search`),
  parte do PDS Search Protocol sobre Apache Solr/Lucene, com JSON como
  saída padrão. Aceita parâmetros como `identifier`, `product_id`,
  `instrument`, `instrument_host`, `spacecraft`, `investigation`,
  `mission` — cobre bem o nicho (imagens reais de instrumentos de
  espaçonaves planetárias: Cassini, Mars rovers, etc., já há um "Cassini
  Users Guide ImageAtlas" oficial).
- Mas a chamada de exemplo encontrada na documentação é um `POST` ao
  endpoint `_search` com uma query estilo Lucene (`bool`/`match` sobre
  `lidvid`), devolvendo o rótulo PDS4 completo do produto
  (`_source`) — não uma URL de imagem direta por busca simples de
  palavra-chave como `images-api.nasa.gov`. Extrair a URL do arquivo de
  imagem de fato exigiria navegar os campos do rótulo PDS4 (formato de
  metadados científico, não pensado para consumo simples tipo "pegue a
  imagem"), um padrão de integração bem mais pesado que as fontes já no
  pipeline.
- Licença: não encontrei (nem na pesquisa desta execução, nem antes)
  uma página de termos específica deste serviço — por analogia seria
  domínio público (produto do governo dos EUA, mesma linha do
  `images-api.nasa.gov`), mas isso não foi confirmado para este serviço
  especificamente.
- **Rebaixado a baixíssima prioridade**: mantém-se pendente mas atrás de
  Openverse, Wikimedia Commons e Smithsonian Open Access na fila — a
  complexidade de parsing de rótulo PDS4 só valeria o esforço se as fontes
  mais simples já pendentes continuarem bloqueadas por bloqueio de rede
  por muitas execuções mais.

### Vera Rubin Observatory — investigado, descartado por falta de API estruturada
- Rubin Observatory (NSF/DOE, "first light" em 2025, relevante para o
  nicho) tem uma galeria pública de imagens
  (`rubinobservatory.org/gallery/collections/main-gallery`) com crédito,
  data, tamanhos de download por item — mas são páginas HTML tradicionais,
  sem endpoint JSON encontrado.
- As APIs reais do Rubin Science Platform (`data.lsst.cloud` — HiPS,
  Simple Image Access, TAP, cutouts) são para **dados científicos brutos**
  (não fotos processadas para divulgação) e exigem token de acesso
  (ligado a conta aprovada), não é acesso público simples.
- **Descartado** nesta rodada pelo mesmo motivo já usado para Chandra e
  JAXA: sem endpoint estruturado público e sem chave simples para o
  conteúdo de divulgação (a galeria), só para dados científicos com token.
  Poderia ser reavaliado se a galeria de divulgação um dia expuser um
  endpoint JSON (como ESA/Hubble/Webb/ESO/NOIRLab fazem).

### JPL Photojournal — não é fonte nova, é refinamento de fonte já em produção
- Não encontrei endpoint JSON próprio do Photojournal
  (`photojournal.jpl.nasa.gov`). Mas a pesquisa confirma que a própria
  `images-api.nasa.gov` (já em produção) aceita um parâmetro `center`
  (código de 3 letras, maiúsculo, ex. `JPL`, `JSC`, `KSC`, `GSFC`) que
  filtra resultados por centro da NASA responsável — útil para quem for
  ajustar `search_nasa_images()` para priorizar imagens do JPL
  (missões planetárias) quando o tópico do roteiro for sobre Marte/sondas/
  etc. Não é uma fonte nova, é uma nota de ajuste fino de uma fonte
  existente; registrado aqui para não se perder.

Candidatos pendentes sem mudança nesta execução (continuam bloqueados por
falta de rede para teste real): Wikimedia Commons API, Smithsonian Open
Access API (`category/science_technology/search`), USGS ScienceBase.
Chandra segue rebaixado (feed sem URL de imagem estruturada) e NOAA/aurora
como baixa prioridade (mapa de previsão, não foto real). Candidatos já
descartados em execuções anteriores (JAXA, Flickr direto, Unsplash,
Pexels) seguem descartados.

Ação recomendada: igual às cinco execuções anteriores, agora com mais
urgência ainda (6 execuções seguidas, ~2.5 semanas, sem conseguir validar
nada de verdade por bloqueio de rede de política da organização, incluindo
agora um domínio nunca antes testado — `api.openverse.org` — confirmando
que não é uma allowlist incompleta e sim bloqueio geral). Liberar "Network
access" do ambiente cloud desta rotina (allowlist incluindo os domínios já
em produção + `commons.wikimedia.org`, `api.si.edu`, `www.sciencebase.gov`,
`api.openverse.org`, ou um nível de acesso mais amplo) é o único jeito de
esta rotina conseguir cumprir o critério de teste real pedido pela tarefa.

**Nenhuma fonte nova encontrada em 2026-10-19** (nenhuma validada por teste
real — bloqueio de rede confirmado pela sexta vez consecutiva, agora
também contra um domínio novo); avanço desta execução foi só
bibliográfico: Openverse API identificado como candidato novo e promissor
(agregador de licença aberta, resolveria o problema de licença variável do
Wikimedia Commons), PDS Imaging Atlas da NASA/JPL investigado e rebaixado
por complexidade de parsing, Rubin Observatory investigado e descartado
por falta de endpoint estruturado, e uma nota de refinamento (parâmetro
`center=JPL`) registrada para a fonte NASA Images API já em produção.

---

## 2026-10-12 (quinta execução)

**Resultado: nenhuma fonte nova validada — bloqueio de rede confirmado pela
quinta execução consecutiva.**

Testes reais desta execução:
- `WebFetch` em `https://images-api.nasa.gov/search?q=nebula&media_type=image`
  (fonte já em produção) → erro `getaddrinfo ENOTFOUND images-api.nasa.gov`
  (resolução DNS falhou, variação do bloqueio já visto nas execuções
  anteriores como `EGRESS_BLOCKED`).
- `curl --cacert /root/.ccr/ca-bundle.crt` para `images-api.nasa.gov`,
  `commons.wikimedia.org` e `api.si.edu` → os três com
  `CONNECT tunnel failed, response 403`. O log do proxy
  (`$HTTPS_PROXY/__agentproxy/status`, campo `recentRelayFailures`) registra
  os três com `connect_rejected` / "gateway answered 403 to CONNECT (policy
  denial or upstream failure)", mesmo padrão das quatro execuções anteriores
  (02/10 x3, 05/10). `"selective": false` no status do proxy confirma de
  novo que é bloqueio geral da organização, não uma allowlist incompleta.

Como o teste real (critério 1) permanece impossível, usei `WebSearch` (que
não passa pelo mesmo proxy) para revisar dois candidatos já pendentes:

### Chandra X-ray Observatory (chandra.harvard.edu/photo) — investigado mais a fundo, rebaixado
- Execuções anteriores concluíram que não havia evidência de API/endpoint
  JSON (diferente da plataforma AVM compartilhada por ESA/Hubble/Webb/ESO/
  NOIRLab). Pesquisa desta execução encontra, de fato, um feed público real:
  `https://chandra.harvard.edu/photo/xml/` (RSS 2.0, também em
  `chandra.cfa.harvard.edu/photo/xml/` e `chandra.si.edu/...`), sem chave.
- Mas o feed só traz `title`, `link`, `guid`, `pubDate`, `description` por
  item — **sem URL de imagem direta nem enclosure**. O `link` aponta pra
  uma página HTML do item, não pro arquivo de imagem; pegar a imagem de
  verdade exigiria fazer scraping de HTML por item (buscar `<img>`/padrão de
  URL na página), não só consumir um feed estruturado — um padrão de
  integração bem mais frágil e fora do que as outras fontes já no pipeline
  oferecem (JSON direto com URL do arquivo).
- Licença também mais ambígua que as fontes AVM (CC BY 4.0 limpo): a
  política de imagens do Chandra/SAO (`chandra.si.edu/photo/image_use.html`)
  é "sem reivindicação de copyright, seguir diretrizes da NASA", mas avisa
  que parte do material combina dados de terceiros com direitos próprios, e
  que uso comercial pode envolver direito de imagem de pessoas reconhecíveis
  nas fotos — mais caso-a-caso que um CC BY/CC0 direto. (Uma página separada
  do Center for Astrophysics menciona CC0 pra ativos digitais do CfA em
  geral, mas não é claro se cobre especificamente o acervo do Photo Album do
  Chandra, com esse aviso específico ao lado.)
- **Rebaixado**: sem URL de imagem estruturada no feed e com licença menos
  clara que os candidatos já pendentes (Wikimedia/Smithsonian/USGS), não
  compensa priorizar sobre eles. Mantido como candidato de baixíssima
  prioridade, não descartado por completo (o feed existe e é real, não é
  invenção) mas improvável de valer o esforço de scraping que exigiria.

### Smithsonian Open Access API — endpoint específico de categoria encontrado
- Pesquisa desta execução (documentação de terceiros que espelha a doc
  oficial, já que a doc oficial em `edan.si.edu/openaccess/docs/` não foi
  acessível sem rede) encontra um endpoint de busca **por categoria**, mais
  específico do que o `/search` genérico já registrado:
  `https://api.si.edu/openaccess/api/v1.0/category/:cat/search`, com
  `:cat` podendo ser `science_technology` (a categoria mais provável de
  conter o acervo de astronomia do Center for Astrophysics | Harvard &
  Smithsonian, já mencionado nas execuções anteriores). Parâmetros: `q`
  (aceita operadores booleanos `AND`/`OR` e busca por campo, ex.
  `topic:Gastropoda`), `rows` (default 10, 0–1000).
- Não muda a conclusão já registrada (licença CC0, chave gratuita via
  api.data.gov, `DEMO_KEY` funciona sem cadastro pra teste rápido) — só
  refina qual endpoint testar primeiro na próxima execução com rede
  liberada: tentar `category/science_technology/search?q=nebula` antes do
  `/search?q=nebula` genérico, pra ver se a categoria já filtra ruído de
  outras coleções do Smithsonian (arte, história) que não interessam ao
  canal.
- Também não foi possível confirmar nesta execução (mesma limitação de
  rede) se esse endpoint retorna URL de imagem direta por item e em volume
  suficiente — segue pendente de teste real.

Candidatos pendentes sem mudança nesta execução: Wikimedia Commons API,
USGS ScienceBase (`sciencebase.gov/catalog/items?q=...&format=json`), NOAA
SWPC (mapa de previsão de aurora, baixa prioridade, não é foto real).
Candidatos já descartados em execuções anteriores (JAXA, Flickr, Unsplash,
Pexels) seguem descartados, sem novidade que mude a conclusão.

Ação recomendada: igual às quatro execuções anteriores, agora mais urgente
(5 execuções seguidas, ~1 semana, sem conseguir validar nada de verdade por
bloqueio de rede de política da organização). Liberar "Network access" do
ambiente cloud desta rotina (modo Custom com allowlist dos domínios já em
produção + `commons.wikimedia.org`, `api.si.edu`, `www.sciencebase.gov`,
ou um nível de acesso mais amplo) é o único jeito de esta rotina conseguir
cumprir o critério de teste real pedido pela tarefa. Reportado ao usuário
por notificação nesta execução.

**Nenhuma fonte nova encontrada em 2026-10-12** — bloqueio de rede
confirmado pela quinta vez consecutiva; avanço desta execução foi só
bibliográfico (feed real do Chandra encontrado e rebaixado por falta de URL
de imagem estruturada e licença mais ambígua; endpoint de categoria do
Smithsonian Open Access refinado).

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
