"""A "skill": as regras que o DeepSeek precisa seguir para o app entendê-lo.

Duas restrições moldam tudo aqui.

**O site não tem system prompt.** As regras viajam dentro da mensagem normal.
As regras Markdown vão inteiras na primeira mensagem de cada conversa e, depois,
só há um lembrete quando o parser não entender. As regras JSON/XML são enviadas
em cada turno para manter o protocolo explícito.

**Contexto pesado rouba o pedido.** Prime grande fazia o modelo responder ao
contexto em vez de fazer o que foi pedido. Por isso o layout é sempre:

    PEDIDO DO USUÁRIO
    ---
    rodapé curto: regras (só na 1ª) + mapa + arquivos anexados + habilidades

O formato dos blocos foi escolhido por experimento — ver a ADR-002 no vault.
As habilidades seguem o padrão Agent Skills (ADR-017).
"""

import re

from src import testes_tela

REGRAS_PROCESSO = """\
PROCESSO DE DESENVOLVIMENTO:

1. Levante o que precisa ser alterado e consulte o contexto relevante do
   projeto e do vault antes de propor uma solução.
2. Planeje brevemente a abordagem e os arquivos ou componentes afetados.
3. Implemente a tarefa de acordo com o plano.
4. Execute os testes pertinentes e verifique os resultados. Se algum teste
   falhar, corrija o problema e teste novamente.
5. Só considere a tarefa concluída quando as verificações pertinentes
   passarem. Depois, atualize o vault apenas se houver informação durável
   relevante, seguindo as instruções e permissões do projeto, e então passe
   para a próxima tarefa.

Não invente requisitos nem tome decisões importantes pelo usuário. Se uma
ambiguidade afetar escopo, comportamento, arquitetura, segurança, dados ou
outra escolha relevante, pause antes de implementar e solicite a decisão pela
ação `decidir`; o aplicativo apresentará as opções para o usuário escolher.
"""

REGRAS = """\
REGRAS DE RESPOSTA (o app que lê você depende delas):

1. Para CADA arquivo que você criar ou alterar, use um bloco de código cuja
   PRIMEIRA linha de dentro seja o metadado:

```python
# kitty: file=CAMINHO/RELATIVO.py acao=criar
<conteúdo completo do arquivo>
```

   `acao` é `criar`, `modificar` ou `apagar`. Use o comentário da linguagem do
   arquivo (`#`, `//`, `--`, `<!-- -->`).

2. Em `modificar`, mande o arquivo INTEIRO, do começo ao fim. Nunca só o trecho.
   Nunca "... resto igual ...". O app substitui o arquivo pelo que você mandar.

3. Use caminho RELATIVO à raiz do projeto. Só use caminho absoluto quando o
   contexto listar uma pasta autorizada ou indicar acesso amplo. Nunca use `..`.

4. Em `apagar`, o bloco vai vazio — só a linha do metadado.

5. Se for só explicar, sem mexer em arquivo, escreva normal e use bloco de código
   comum, SEM a linha `# kitty:`.

6. Não use tags XML tipo <resposta> ou <arquivo>. O site quebra a formatação e o
   app recebe tudo numa linha só."""

REGRAS_DECISAO_MARKDOWN = """\
Para solicitar uma decisão importante do usuário, use um bloco separado como
este. Apresente uma pergunta objetiva, de 2 a 5 opções concretas, o número
(a partir de 1) da opção que você recomenda e o motivo da recomendação:

```text
# kitty: acao=decidir
{"question":"Qual abordagem devo seguir?","options":["Opção A","Opção B"],"recommended":1,"reason":"por que a opção A é a melhor aqui"}
```

Sempre diga qual opção recomenda e por quê; quem decide continua sendo o
usuário. Peça uma decisão por resposta e não misture essa solicitação com ações
de arquivo ou comandos. Aguarde a escolha antes de continuar; não presuma a
opção.
"""

REGRAS_AGENTE = """\
7. Você pode pedir informação antes de responder. Um bloco por pedido:

```
# kitty: acao=ler file=src/app.py
```
```
# kitty: acao=listar dir=src/models
```
```
# kitty: acao=buscar termo=calcularTotal
```

   `buscar` procura o texto dentro dos arquivos e devolve `arquivo:linha`. É por
   onde começar num projeto grande: busque o nome da função ou da classe, depois
   leia só os arquivos que apareceram. `ext=py` limita a extensão e `em=src/`
   limita a pasta.

   Pode pedir vários blocos de uma vez — todos são atendidos na ordem, numa
   resposta só. Cada rodada custa dezenas de segundos, então peça em lote em vez
   de um de cada vez.

8. Para rodar comando, use o bloco da linguagem do shell:

```bash
# kitty: acao=rodar
pytest -q
```

   É um shell completo do sistema (cmd.exe no Windows), começando na raiz do
   projeto: pipes, redirecionamento, `&&`, `cd` e várias linhas valem. Comando
   comum pode levar até 5 minutos e a entrada padrão é fechada — não rode nada
   interativo. A execução segue o perfil de acesso do app e pode exigir
   confirmação.

   Comando que não termina sozinho (servidor de desenvolvimento como
   `npm run dev`, `uvicorn`, `python -m http.server`, qualquer `--watch`) roda
   em segundo plano: o app espera ele ficar pronto, devolve a saída inicial e
   segue, com o processo vivo. Os mais comuns são reconhecidos sozinhos; para
   pedir explicitamente, use `# kitty: acao=rodar fundo=sim`. Para acompanhar,
   rode como comando: `@processos` (lista), `@saida N` (últimas linhas do
   processo N) e `@parar N` (encerra o processo N).

9. Quando a tarefa estiver completa, termine a mensagem com:

```
# kitty: acao=fim
```

   Sem isso o app fica esperando você continuar."""

LEMBRETE = """\
Sua última resposta não seguiu o formato: não achei a linha `# kitty:` em nenhum
bloco. Reenvie a MESMA resposta, agora com a primeira linha de dentro de cada
bloco de código assim:

# kitty: file=caminho/relativo.ext acao=criar

Arquivo inteiro em cada bloco, caminho relativo."""

REGRAS_JSON = """\
PROTOCOLO JSON DE RESPOSTA:

Responda com exatamente um bloco de código com rótulo json, como numa API. Não
escreva JSON cru fora da cerca. A cerca deve usar pelo menos 3 crases e ser uma
crase mais longa que qualquer sequência de crases no JSON; feche com a mesma
cerca. O objeto raiz contém exatamente "response" (texto para a pessoa) e
"actions" (lista de operações para o aplicativo). O aplicativo mostra
"response" como texto normal e o código de cada ação em um bloco de código.
Cada item de "actions" usa "action" como discriminador e somente os campos
definidos abaixo:

- {"action":"create"|"modify","path":"caminho","code":"arquivo inteiro"}
- {"action":"delete"|"read","path":"caminho"}
- {"action":"list"} ou {"action":"list","path":"pasta"}
- {"action":"search","term":"texto"}; "path" e "extension" são opcionais
- {"action":"run","command":"comando"}; acrescente "background":true para
  comando que não termina sozinho (servidor de desenvolvimento, watch)
- {"action":"decision","question":"pergunta objetiva","options":["opção A","opção B"],"recommended":1,"reason":"motivo da recomendação"}
- {"action":"done"}

Use caminhos relativos à raiz, sem "..", exceto quando o contexto autorizar
caminho absoluto. Para create/modify, "code" contém o arquivo inteiro como
string JSON válida, com aspas e quebras de linha escapadas. Use uma ação por
objeto; para múltiplas operações, adicione objetos à lista. Sem operações, use
"actions": []. Read/list/search/run só funcionam quando o modo Agente está
ligado. No modo de resposta única, limite-se a create/modify/delete/decision.
Não misture uma ação decision com outras ações; aguarde a escolha do usuário
antes de continuar. Em toda decision, "recommended" é o número (a partir de 1)
da opção que você recomenda e "reason" explica por quê; quem decide é o
usuário. Em dúvidas relevantes, prefira pedir essa decisão a
presumir requisitos ou comportamento. O processo de desenvolvimento é: levantar
o que precisa mudar, planejar, implementar, testar e corrigir até os testes
pertinentes passarem; só então concluir e atualizar o vault se houver informação
durável que mereça registro. Não afirme que o vault foi atualizado sem
confirmação do aplicativo.

Não inclua chaves extras, comentários, vírgula final ou outro bloco de código."""

REGRAS_XML = """\
PROTOCOLO XML DE RESPOSTA:

Responda com exatamente um bloco de código com rótulo xml, como numa API. Não
escreva XML cru fora da cerca. A cerca deve usar pelo menos 3 crases e ser uma
crase mais longa que qualquer sequência de crases no XML; feche com a mesma
cerca. A raiz <response> contém <text>texto para a pessoa</text> e
<actions>...</actions>. O aplicativo mostra o texto como texto normal e o código
de cada ação em um bloco de código. Cada operação é um elemento
<action type="...">:

- create/modify: atributo path e filho <code><![CDATA[arquivo inteiro]]></code>
- delete/read: atributo path, sem filho
- list: atributo path opcional, sem filho
- search: atributo term obrigatório; path e extension são opcionais
- run: filho <command><![CDATA[comando]]></command>; atributo opcional
  background="true" para comando que não termina sozinho (servidor, watch)
- decision: atributos question, recommended (número, a partir de 1, da opção
  que você recomenda) e reason (motivo da recomendação), e filho <options> com
  2 a 5 elementos <option>texto da opção</option>
- done: sem atributos além de type e sem filho

Use caminhos relativos à raiz, sem "..", exceto quando o contexto autorizar
caminho absoluto. Não indente nem acrescente texto ao redor do conteúdo de
<code> ou <command>. Se o conteúdo tiver o terminador CDATA, divida-o como
]]]]><![CDATA[>. Sem ações, use <actions />. Read/list/search/run só funcionam
quando o modo Agente está ligado. No modo de resposta única, limite-se a
create/modify/delete/decision. Não misture uma ação decision com outras ações; aguarde a
escolha do usuário antes de continuar. Em dúvidas relevantes, prefira pedir
essa decisão a presumir requisitos ou comportamento. O processo de
desenvolvimento é: levantar o que precisa mudar, planejar, implementar, testar
e corrigir até os testes pertinentes passarem; só então concluir e atualizar o
vault se houver informação durável que mereça registro. Não afirme que o vault
foi atualizado sem confirmação do aplicativo. Não inclua elementos ou
atributos extras nem outros blocos de código."""

REGRAS_AGENTE_ESTRUTURADAS = """\
NO MODO AGENTE: peça uma leitura de arquivo por resposta e aguarde o conteúdo
antes de decidir se precisa ler outro; o app devolverá o resultado numa nova
rodada. Faça pedidos de list/search separadamente também. A ação run executa
o comando num shell completo do sistema (cmd.exe no Windows), começando na raiz
do projeto: pipes, redirecionamento, && e várias linhas valem; comando comum
tem até 5 minutos e não há entrada interativa (stdin fechado). Comando que não
termina sozinho (servidor de desenvolvimento, watch) roda em segundo plano: o
app espera ficar pronto, devolve a saída inicial e segue; os comuns são
reconhecidos sozinhos e background=true pede explicitamente. Para acompanhar,
use run com os comandos internos @processos, @saida N e @parar N. Depende da
autorização configurada pelo usuário. Use done somente quando a tarefa estiver
concluída."""

_REGRAS_VAULT_MODELO = """\
VAULT DO PROJETO:

- Há um vault Obsidian em `vault/`; a nota central é `vault/{indice}`.{passagem}
  Leia a nota central e as notas relacionadas quando forem úteis à tarefa;
  no modo Agente, solicite leituras com as ações normais do app.
- Em cada pedido novo, avalie se existe informação durável que mereça registro:
  decisões, arquitetura, riscos, planos, procedimentos ou estado validado.
  Mudanças rotineiras, detalhes transitórios e hipóteses não verificadas não
  merecem nota.
- Se uma atualização for útil, inclua a ação de criar/editar a nota no mesmo
  plano de alterações. Explique na resposta o contexto, por que vale registrar
  e quais notas serão afetadas. A aplicação segue o perfil de permissão ativo:
  pode exigir confirmação ou ser automática. Não afirme que uma nota foi salva
  antes do resultado real do app.
- Use Markdown, frontmatter YAML com `tipo`, `criado`, `atualizado` (ISO
  `YYYY-MM-DD`) e `tags`, títulos claros, uma ideia principal por nota e links
  internos `[[...]]`. Ao criar/mover uma nota, mantenha `{indice}` e os
  links relacionados consistentes. Siga `vault/AGENTS.md` e
  `vault/{padrao}`; valide fatos no projeto e não invente campos."""

INDICE_PADRAO = "00 - Índice.md"
PADRAO_NOTAS_PADRAO = "Padrão de notas.md"


def cabecalho_agents(texto: str) -> dict:
    """Campos simples (`chave: valor`) do cabeçalho YAML do `vault/AGENTS.md`.

    É o padrão de cadastro de vaults (`vault_id`, `indice`, `padrao`,
    `passagem`…). Sem cabeçalho, devolve `{}` e valem os nomes padrão.
    """
    linhas = (texto or "").lstrip("\ufeff").splitlines()
    if not linhas or linhas[0].strip() != "---":
        return {}
    campos = {}
    for linha in linhas[1:80]:
        if linha.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", linha)
        if m:
            valor = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip('"').strip("'")
            campos[m.group(1)] = valor
    return campos


def _nota_vault(valor, padrao: str) -> str:
    """Nome de nota seguro: relativo ao vault, sem `..` nem caminho absoluto."""
    valor = (valor or "").replace("\\", "/").strip().lstrip("/")
    if not valor or ".." in valor.split("/") or ":" in valor:
        return padrao
    return valor


def regras_vault(instrucoes: str = "") -> str:
    """Regras do vault com índice, padrão e passagem do `AGENTS.md`, se houver."""
    cab = cabecalho_agents(instrucoes)
    indice = _nota_vault(cab.get("indice"), INDICE_PADRAO)
    padrao = _nota_vault(cab.get("padrao"), PADRAO_NOTAS_PADRAO)
    passagem = _nota_vault(cab.get("passagem"), "")
    linha_passagem = (
        f"\n- Antes de começar, leia `vault/{passagem}` (registro entre agentes, o mais"
        "\n  recente no topo); ao terminar algo durável, registre no topo dela."
        if passagem else "")
    return _REGRAS_VAULT_MODELO.format(indice=indice, padrao=padrao, passagem=linha_passagem)


REGRAS_VAULT = regras_vault()

SONDA_CAMINHO = "__deepseek_format_probe__.txt"
SONDA_CONTEUDO = "deepseek-format-probe-v1"

# Limite de skills injetadas por turno. Duas SKILL.md completas já chegam
# perto do orçamento prático; o README do Claude recomenda 1–2 por turno.
LIMITE_SKILLS_POR_TURNO = 2


def regras_protocolo(formato: str) -> str:
    """Devolve as instruções do protocolo estruturado selecionado."""
    regras = {"json": REGRAS_JSON, "xml": REGRAS_XML}
    try:
        return regras[formato]
    except KeyError as erro:
        raise ValueError(f"formato de resposta desconhecido: {formato}") from erro


def prompt_sonda(formato: str) -> str:
    """Pede resposta e ação de teste; o app valida, mas nunca a executa."""
    regras = regras_protocolo(formato)
    return (
        "SONDA DE FORMATO: não execute nem altere nada. Devolva uma resposta "
        "estruturada com response/text igual a 'Teste de formato recebido.' e "
        "exatamente uma ação create para o caminho "
        f"'{SONDA_CAMINHO}', com code exatamente '{SONDA_CONTEUDO}'. "
        "O aplicativo deve mostrar a resposta como texto, o conteúdo como bloco "
        "de código e interceptará a ação sem aplicá-la.\n\n"
        + regras
    )


def _rodape(partes: list[str]) -> str:
    conteudo = "\n\n".join(p for p in partes if p)
    return f"\n\n---\n\n{conteudo}" if conteudo else ""


def cerca(conteudo: str, lang: str = "") -> str:
    """Bloco de código que não fecha antes da hora.

    A cerca é uma crase mais longa que a maior sequência de crases do conteúdo:
    um README com ``` dentro fecharia uma cerca de 3 no meio, e o resto do
    arquivo chegaria ao modelo como texto solto.
    """
    maior = max((len(m) for m in re.findall(r"`+", conteudo or "")), default=0)
    marca = "`" * max(3, maior + 1)
    return f"{marca}{lang}\n{conteudo}\n{marca}"


def anexo(rel: str, conteudo: str) -> str:
    """Um arquivo colado no rodapé, marcado para o modelo saber o caminho."""
    return f"Arquivo `{rel}`:\n\n{cerca(conteudo)}"


def bloco_habilidades(skills, limite: int = LIMITE_SKILLS_POR_TURNO) -> str:
    """Renderiza o bloco de habilidades no formato Agent Skills.

    ``skills`` é uma lista de objetos com ``slug``, ``name``, ``description``,
    ``conteudo`` e ``habilitada`` (como :class:`Skill` do ``src/skills.py``).
    Duck-typed, para os testes não montarem o dataclass inteiro.

    **Corte por limite.** Só as ``limite`` primeiras habilitadas (ordem
    alfabética por slug) recebem o conteúdo completo. As demais — inclusive
    habilitadas além do corte — entram apenas como índice ``name`` +
    ``description``, com aviso de que estão fora do limite.

    **Portões 🛑.** O bloco instrui o modelo a usar a ação ``decision`` do
    protocolo quando a skill habilitada pedir pausa para aprovação — em vez de
    continuar sozinho.

    Devolve ``""`` se a lista for vazia/None.
    """
    if not skills:
        return ""

    habilitadas_todas = sorted(
        (s for s in skills if getattr(s, "habilitada", False)),
        key=lambda s: getattr(s, "slug", ""),
    )
    habilitadas_completas = habilitadas_todas[:limite]
    habilitadas_excedentes = habilitadas_todas[limite:]
    desabilitadas = sorted(
        (s for s in skills if not getattr(s, "habilitada", False)),
        key=lambda s: getattr(s, "slug", ""),
    )

    partes: list[str] = [
        "HABILIDADES (contexto opcional — use só o que fizer sentido para a "
        "tarefa atual; não misture assuntos diferentes sem motivo).",
    ]

    # Conteúdo completo das habilitadas dentro do limite
    if habilitadas_completas:
        partes.append("## Habilidades habilitadas (conteúdo completo)")
        for s in habilitadas_completas:
            corpo = (getattr(s, "conteudo", "") or "").strip()
            nome = getattr(s, "name", getattr(s, "slug", ""))
            if corpo:
                partes.append(f"### {nome}\n\n{corpo}")
            else:
                partes.append(f"### {nome}\n\n_(sem conteúdo)_")

    # Índice do que sobrou (habilitadas excedentes + desabilitadas)
    indexaveis = habilitadas_excedentes + desabilitadas
    if indexaveis:
        partes.append("## Outras habilidades disponíveis (só nome e descrição)")
        if habilitadas_excedentes:
            partes.append(
                f"O limite é {limite} skills completas por turno. As abaixo "
                "estão **habilitadas mas fora do limite**: o usuário pode "
                "desabilitar outra para dar lugar, ou simplesmente não usar "
                "agora."
            )
        partes.append(
            "O usuário pode pedir um levantamento das habilidades para uma "
            "tarefa específica. Nesse caso, considere TODAS listadas abaixo "
            "(mesmo as desabilitadas) e sugira quais ativar."
        )
        for s in indexaveis:
            nome = getattr(s, "name", getattr(s, "slug", ""))
            desc = (getattr(s, "description", "") or "").strip()
            desc_uma_linha = " ".join(desc.split())
            if len(desc_uma_linha) > 240:
                desc_uma_linha = desc_uma_linha[:239].rstrip() + "…"
            marcador = " _(habilitada, fora do limite)_" if s in habilitadas_excedentes else ""
            partes.append(f"- **{nome}**{marcador} — {desc_uma_linha}")

    # Instrução sobre portões 🛑
    partes.append(
        "## Portões 🛑\n\n"
        "As habilidades seguem o padrão Agent Skills e costumam marcar portões "
        "com 🛑 (ex.: *\"🛑 Aprova o design?\"*). Quando a skill habilitada "
        "chegar a um portão, **pare e use a ação `decision` do protocolo** "
        "para pedir aprovação ao usuário. Nunca siga por conta própria quando a "
        "skill disser para parar."
    )

    return "\n\n".join(partes)


def montar(pedido: str, project=None, primeira: bool = False,
           anexos: list[tuple[str, str]] | None = None,
           agente: bool = False, mapa_limite: int | None = None,
           instrucoes: str = "", formato: str = "markdown",
           incluir_mapa: bool = True, habilidades=None) -> str:
    """Monta a mensagem que vai para o DeepSeek.

    `pedido` vem primeiro, sempre. Tudo que é contexto vai depois do separador.
    `primeira` liga as regras Markdown completas (usar na 1ª mensagem).
    JSON/XML sempre recebem as regras do protocolo selecionado.
    `agente` acrescenta o vocabulário de ler/listar/rodar/fim.
    `habilidades` (opcional) é a lista de habilidades; o bloco delas é
    injetado no rodapé depois das instruções do AGENTS e antes dos anexos,
    sempre que preenchido, para refletir ativações/desativações entre turnos.
    """
    partes = []

    if formato == "markdown" and primeira:
        regras = REGRAS + "\n\n" + REGRAS_DECISAO_MARKDOWN
        if agente:
            regras += "\n\n" + REGRAS_AGENTE
        regras += "\n\n" + REGRAS_PROCESSO
        partes.append(regras)
    elif formato in ("json", "xml"):
        partes.append(regras_protocolo(formato))
        if agente:
            partes.append(REGRAS_AGENTE_ESTRUTURADAS)
    elif formato != "markdown":
        raise ValueError(f"formato de resposta desconhecido: {formato}")

    if (primeira and project is not None
            and getattr(project, "vault_root", None) is not None):
        partes.append(regras_vault(instrucoes))

    if primeira and agente:
        bloco_tela = testes_tela.regras()
        if bloco_tela:
            partes.append(bloco_tela)

    if project is not None:
        if incluir_mapa:
            try:
                partes.append(f"Projeto `{project.nome}` — arquivos:\n\n"
                              + cerca(project.mapa(limite=mapa_limite)))
            except OSError:
                pass
            partes.append(project.contexto_permissoes())
            indice = _nota_vault(cabecalho_agents(instrucoes).get("indice"), INDICE_PADRAO)
            if (primeira and getattr(project, "vault_root", None) is not None
                    and project.existe(f"vault/{indice}")):
                partes.append(
                    "Índice do vault para orientar esta conversa:\n\n"
                    + project.ler(f"vault/{indice}"))
        else:
            partes.append(
                "A estrutura de arquivos e os caminhos autorizados deste projeto "
                "não foram compartilhados nesta mensagem. Não presuma nomes ou "
                "caminhos; peça ao usuário o contexto de que precisar.")

    if instrucoes.strip():
        partes.append("Instruções do projeto (AGENTS.md no vault):\n\n"
                      + instrucoes.strip())

    bloco_sk = bloco_habilidades(habilidades)
    if bloco_sk:
        partes.append(bloco_sk)

    for rel, conteudo in (anexos or []):
        partes.append(anexo(rel, conteudo))

    return (pedido or "").strip() + _rodape(partes)


def realimentar(relatorio_texto: str, leituras: list[tuple[str, str]] | None = None,
                formato: str = "markdown", agente: bool = False) -> str:
    """Mensagem que devolve ao modelo o resultado do que ele pediu (Fase 4).

    Não reenvia o contexto do projeto (mapa, skills, vault): na 1ª mensagem do
    turno ele já foi junto. Se o usuário ativar uma habilidade no meio do loop,
    o efeito só aparece no próximo ``montar``.
    """
    partes = []
    if relatorio_texto:
        partes.append(f"Resultado do que você pediu:\n\n{cerca(relatorio_texto)}")
    for rel, conteudo in (leituras or []):
        partes.append(anexo(rel, conteudo))
    if formato in ("json", "xml"):
        partes.append(regras_protocolo(formato))
        if agente:
            partes.append(REGRAS_AGENTE_ESTRUTURADAS)
        partes.append("Continue. Se a tarefa acabou, inclua uma ação done.")
    else:
        partes.append(REGRAS_DECISAO_MARKDOWN)
        partes.append(REGRAS_PROCESSO)
        partes.append("Continue. Se a tarefa acabou, responda `# kitty: acao=fim`.")
    return "\n\n".join(partes)
