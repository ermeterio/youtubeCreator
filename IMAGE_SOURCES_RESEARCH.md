# Pesquisa de fontes de imagens públicas (astronomia/ciência/espaço)

Histórico de execuções da rotina agendada de pesquisa de novas fontes de
imagem para o pipeline (`pipeline/visual_source.py`). Cada execução adiciona
uma seção no topo, sem apagar as anteriores.

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
