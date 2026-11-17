"""Resposta do DeepSeek → lista de ações.

O formato foi decidido por experimento, não por gosto: ver a ADR-002 no vault.
Resumo do que sobrevive ao renderizador do site:

  • **primário** — comentário na 1ª linha DENTRO do bloco (fica no `<pre>`,
    a parte mais estável do DOM):

        ```python
        # kitty: file=src/calc.py acao=criar
        def somar(a, b): ...
        ```

  • **secundário** — token único na cerca, sem espaço nenhum (o DeepSeek corta a
    info string no primeiro espaço, mas o primeiro token vem inteiro):

        ```python:src/calc.py:criar

O protocolo legado não aceita XML cru: isso faz o site cair em modo HTML cru,
onde nenhum bloco é renderizado e toda quebra de linha vira espaço. JSON/XML
estruturados são analisados separadamente e só dentro de fences rotuladas.

Este módulo não toca em disco e não valida caminho — isso é do `sandbox.py`.
"""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# Cerca com info string. A última pode estar aberta (streaming ainda rodando),
# daí o \Z — mas quem aplica só usa a resposta FINAL.
FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)(?:```|\Z)", re.DOTALL)
STRUCTURED_FENCE_RE = re.compile(
    r"(?P<fence>`{3,})(?P<info>[^\n`]*)\n(?P<body>.*?)"
    r"(?:\n)?(?P=fence)[ \t]*(?=\n|$)",
    re.DOTALL,
)

# Comentário de metadado. Aceita os prefixos de comentário mais comuns porque o
# modelo escolhe pela linguagem do arquivo; e aceita nenhum, porque às vezes ele
# esquece. O fechamento (--> ou */) é opcional.
KITTY_RE = re.compile(
    r"^[ \t]*(?://|#|--|;|%|<!--|/\*|\*)?[ \t]*kitty[ \t]*:[ \t]*(?P<resto>.*?)"
    r"[ \t]*(?:-->|\*/)?[ \t]*$",
    re.IGNORECASE,
)

# chave=valor, com ou sem aspas
PAR_RE = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))""")

# Sinônimos que o modelo usa na prática. A chave é o verbo canônico.
VERBOS = {
    "criar": {"criar", "create", "novo", "new", "add", "adicionar"},
    "modificar": {"modificar", "modify", "editar", "edit", "update", "atualizar",
                  "escrever", "write", "substituir", "replace"},
    "apagar": {"apagar", "delete", "deletar", "remover", "remove", "rm"},
    "ler": {"ler", "read", "abrir", "open", "cat"},
    "listar": {"listar", "list", "ls", "tree", "arvore"},
    "rodar": {"rodar", "run", "executar", "exec", "shell", "cmd"},
    "buscar": {"buscar", "procurar", "search", "grep", "find", "localizar"},
    "fim": {"fim", "done", "end", "terminado", "pronto", "finish"},
    "decidir": {"decidir", "decision", "ask", "perguntar"},
}
_CANON = {alias: canon for canon, aliases in VERBOS.items() for alias in aliases}

# Linguagens que são comando de shell, não arquivo-fonte.
LANGS_SHELL = {"sh", "bash", "zsh", "shell", "console", "terminal",
               "powershell", "ps1", "ps", "pwsh", "cmd", "bat", "batch", "dos"}


def canonico(palavra: str) -> str | None:
    return _CANON.get((palavra or "").strip().lower())


@dataclass
class Acao:
    """Uma coisa que o modelo pediu para fazer."""

    verbo: str                       # criar|modificar|apagar|ler|listar|rodar|fim|decidir
    caminho: str | None = None       # relativo à raiz; None em rodar/fim
    conteudo: str | None = None      # corpo do bloco, já sem a linha de metadado
    lang: str = ""
    origem: str = ""                 # 'comentario' | 'cerca' | 'inferido'
    bruto: str = ""                  # bloco original, para o modo degradado
    extras: dict = field(default_factory=dict)   # termo=, ext=, … da busca

    @property
    def escreve(self) -> bool:
        return self.verbo in ("criar", "modificar")


@dataclass
class Resposta:
    resumo: str = ""
    acoes: list[Acao] = field(default_factory=list)
    blocos_soltos: int = 0           # cercas sem metadado nenhum
    valida: bool = True
    erro: str = ""

    @property
    def tem_acao(self) -> bool:
        return bool(self.acoes)

    @property
    def suspeita(self) -> bool:
        """Tem código mas nenhuma ação: provável desobediência de formato."""
        return not self.acoes and self.blocos_soltos > 0


def _pares(texto: str) -> dict:
    out = {}
    for m in PAR_RE.finditer(texto or ""):
        chave = m.group(1).lower()
        out[chave] = m.group(2) or m.group(3) or m.group(4) or ""
    return out


def _do_comentario(corpo: str):
    """Lê a 1ª linha do bloco. Devolve (info, corpo_sem_a_linha) ou (None, corpo)."""
    if not corpo:
        return None, corpo
    linhas = corpo.split("\n")
    m = KITTY_RE.match(linhas[0])
    if not m:
        return None, corpo
    info = _pares(m.group("resto"))
    if not info:
        return None, corpo
    # A linha de metadado sai do conteúdo: ela não pertence ao arquivo.
    return info, "\n".join(linhas[1:])


def _da_cerca(info_string: str):
    """`python:src/a.py:criar` → {'lang':..., 'file':..., 'acao':...}."""
    token = (info_string or "").strip()
    if not token or ":" not in token:
        return None
    partes = [p for p in token.split(":") if p != ""]
    if len(partes) < 2:
        return None
    lang, resto = partes[0], partes[1:]
    # O caminho é a parte que parece caminho; o verbo, a que é verbo conhecido.
    caminho = verbo = None
    for p in resto:
        if canonico(p) and not verbo:
            verbo = p
        elif caminho is None:
            caminho = p
    if not caminho:
        return None
    return {"lang": lang, "file": caminho, "acao": verbo or ""}


def _bloco_estruturado(texto: str, formato: str) -> str:
    cercas = [
        m.group("body") for m in STRUCTURED_FENCE_RE.finditer(texto or "")
        if m.group("info").strip().lower() == formato
    ]
    if len(cercas) != 1:
        if not cercas:
            raise ValueError(f"resposta sem um bloco ```{formato}``` fechado")
        raise ValueError(f"resposta contém {len(cercas)} blocos ```{formato}```")
    return cercas[0].strip()


def _acao_estruturada(campos: dict) -> Acao:
    permitidos = {
        "action", "path", "code", "command", "term", "extension",
        "question", "options", "recommended", "reason", "background",
    }
    extras = set(campos) - permitidos
    if extras:
        raise ValueError("ação contém campo(s) desconhecido(s): "
                         + ", ".join(sorted(extras)))

    verbo = canonico(campos.get("action", ""))
    if not verbo:
        raise ValueError("ação sem tipo conhecido")

    def texto(chave: str, obrigatorio: bool = False) -> str | None:
        if chave not in campos and not obrigatorio:
            return None
        valor = campos.get(chave)
        if not isinstance(valor, str) or (obrigatorio and not valor.strip()):
            raise ValueError(f"campo '{chave}' precisa ser texto"
                             + (" não vazio" if obrigatorio else ""))
        try:
            valor.encode("utf-8")
        except UnicodeEncodeError as erro:
            raise ValueError(f"campo '{chave}' contém Unicode inválido") from erro
        return valor

    def campos_exatos(*esperados: str) -> None:
        atuais = set(campos) - {"action"}
        if atuais != set(esperados):
            faltando = set(esperados) - atuais
            a_mais = atuais - set(esperados)
            detalhes = []
            if faltando:
                detalhes.append("faltando " + ", ".join(sorted(faltando)))
            if a_mais:
                detalhes.append("inesperado(s) " + ", ".join(sorted(a_mais)))
            raise ValueError("campos inválidos para ação " + verbo + ": "
                             + "; ".join(detalhes))

    if verbo in ("criar", "modificar"):
        campos_exatos("path", "code")
        caminho = texto("path", True)
        conteudo = texto("code", True)
        return Acao(verbo, caminho=caminho, conteudo=conteudo, origem="estruturado")
    if verbo in ("apagar", "ler"):
        campos_exatos("path")
        return Acao(verbo, caminho=texto("path", True), origem="estruturado")
    if verbo == "listar":
        campos_exatos() if "path" not in campos else campos_exatos("path")
        return Acao(verbo, caminho=texto("path"), origem="estruturado")
    if verbo == "buscar":
        esperados = ["term"]
        if "path" in campos:
            esperados.append("path")
        if "extension" in campos:
            esperados.append("extension")
        campos_exatos(*esperados)
        termo = texto("term", True)
        caminho = texto("path")
        extensao = texto("extension")
        return Acao(
            verbo, caminho=caminho, origem="estruturado",
            extras={"termo": termo, **({"ext": extensao} if extensao else {})})
    if verbo == "rodar":
        campos_exatos("command", *(("background",) if "background" in campos else ()))
        comando = texto("command", True)
        fundo = campos.get("background")
        if fundo is not None and not isinstance(fundo, (bool, str)):
            raise ValueError("campo 'background' precisa ser true/false")
        ligado = fundo is True or (isinstance(fundo, str)
                                   and fundo.strip().lower() in ("true", "sim", "1", "yes"))
        return Acao(verbo, conteudo=comando, origem="estruturado",
                    extras={"fundo": True} if ligado else {})
    if verbo == "fim":
        campos_exatos()
        return Acao(verbo, origem="estruturado")
    if verbo == "decidir":
        campos_exatos("question", "options",
                      *(c for c in ("recommended", "reason") if c in campos))
        return _acao_decisao(
            texto("question", True), campos.get("options"), "estruturado",
            recomendada=campos.get("recommended"), motivo=campos.get("reason"))
    raise ValueError(f"ação não suportada: {verbo}")


def _recomendacao(valor, opcoes: list[str]) -> int | None:
    """Número (a partir de 1) da opção recomendada pelo modelo, ou None.

    Aceita o número ou o próprio texto da opção: os dois aparecem na prática.
    """
    if valor is None:
        return None
    if isinstance(valor, str):
        bruto = valor.strip()
        if bruto.isdigit():
            valor = int(bruto)
        else:
            iguais = [i for i, opcao in enumerate(opcoes, 1)
                      if opcao.casefold() == bruto.casefold()]
            if iguais:
                return iguais[0]
            raise ValueError(
                "campo 'recommended' precisa ser o número de uma das opções")
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError("campo 'recommended' precisa ser o número de uma das opções")
    if not 1 <= valor <= len(opcoes):
        raise ValueError(
            f"campo 'recommended' fora das opções: {valor} (há {len(opcoes)})")
    return valor


def _acao_decisao(pergunta, opcoes, origem: str, bruto: str = "",
                  recomendada=None, motivo=None) -> Acao:
    if not isinstance(pergunta, str) or not pergunta.strip():
        raise ValueError("campo 'question' precisa ser texto não vazio")
    if not isinstance(opcoes, list) or not 2 <= len(opcoes) <= 5:
        raise ValueError("campo 'options' precisa conter de 2 a 5 opções")
    for valor in [pergunta, *opcoes]:
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError("pergunta e opções precisam ser textos não vazios")
        try:
            valor.encode("utf-8")
        except UnicodeEncodeError as erro:
            raise ValueError("pergunta ou opção contém Unicode inválido") from erro
    opcoes_limpas = [opcao.strip() for opcao in opcoes]
    if len({opcao.casefold() for opcao in opcoes_limpas}) != len(opcoes):
        raise ValueError("as opções da decisão precisam ser distintas")
    extras = {"pergunta": pergunta.strip(), "opcoes": opcoes_limpas}
    numero = _recomendacao(recomendada, opcoes_limpas)
    if numero is not None:
        extras["recomendada"] = numero
    if motivo is not None:
        if not isinstance(motivo, str):
            raise ValueError("campo 'reason' precisa ser texto")
        if motivo.strip():
            extras["motivo"] = motivo.strip()
    return Acao("decidir", origem=origem, bruto=bruto, extras=extras)


def _acao_decisao_markdown(corpo: str, bruto: str) -> Acao:
    dados = json.loads(corpo, object_pairs_hook=_objeto_json_sem_duplicatas)
    if (not isinstance(dados, dict)
            or not {"question", "options"} <= set(dados)
            or not set(dados) <= {"question", "options", "recommended", "reason"}):
        raise ValueError(
            "o corpo da ação decidir deve conter 'question' e 'options', e "
            "opcionalmente 'recommended' e 'reason'")
    return _acao_decisao(
        dados["question"], dados["options"], "comentario", bruto,
        recomendada=dados.get("recommended"), motivo=dados.get("reason"))


def _objeto_json_sem_duplicatas(pares: list[tuple[str, object]]) -> dict:
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            raise ValueError(f"chave JSON duplicada: {chave}")
        objeto[chave] = valor
    return objeto


def _resposta_estruturada(texto: str, formato: str) -> Resposta:
    resposta = Resposta()
    try:
        bloco = _bloco_estruturado(texto, formato)
        if formato == "json":
            dados = json.loads(bloco, object_pairs_hook=_objeto_json_sem_duplicatas)
        else:
            fora_cdata = re.sub(
                r"<!\[CDATA\[.*?\]\]>", "", bloco, flags=re.DOTALL | re.IGNORECASE)
            if re.search(r"<!DOCTYPE\b|<!ENTITY\b", fora_cdata, re.IGNORECASE):
                raise ValueError("declarações DTD e ENTITY não são permitidas")
            raiz = ET.fromstring(bloco)
            if raiz.tag != "response" or raiz.attrib:
                raise ValueError("raiz XML deve ser <response> sem atributos")
            if (raiz.text or "").strip():
                raise ValueError("<response> não aceita texto fora dos elementos")
            if [filho.tag for filho in raiz] != ["text", "actions"]:
                raise ValueError(
                    "XML deve conter <text> seguido de <actions>")
            if any((filho.tail or "").strip() for filho in raiz):
                raise ValueError("<response> não aceita texto entre os elementos")
            texto_resposta, acoes_xml = list(raiz)
            if texto_resposta.attrib or list(texto_resposta):
                raise ValueError("<text> deve conter somente texto")
            if acoes_xml.attrib:
                raise ValueError("<actions> não aceita atributos")
            if (acoes_xml.text or "").strip():
                raise ValueError("<actions> aceita somente elementos <action>")
            acoes = []
            for elemento in acoes_xml:
                if elemento.tag != "action":
                    raise ValueError("<actions> aceita somente <action>")
                if (elemento.tail or "").strip():
                    raise ValueError("<actions> não aceita texto entre ações")
                atributos_inesperados = (
                    set(elemento.attrib)
                    - {"type", "path", "term", "extension", "question",
                       "recommended", "reason", "background"})
                if atributos_inesperados:
                    raise ValueError(
                        "<action> contém atributo(s) desconhecido(s): "
                        + ", ".join(sorted(atributos_inesperados)))
                campos = {"action": elemento.attrib.get("type")}
                for chave in ("path", "term", "extension", "question",
                              "recommended", "reason", "background"):
                    if chave in elemento.attrib:
                        campos[chave] = elemento.attrib[chave]
                if "type" not in elemento.attrib:
                    raise ValueError("<action> precisa do atributo type")
                tipo_acao = canonico(campos["action"] or "")
                if tipo_acao == "decidir":
                    if len(elemento) != 1 or elemento[0].tag != "options":
                        raise ValueError(
                            "ação decision precisa de um elemento <options>")
                    if (elemento.text or "").strip():
                        raise ValueError("<action> não aceita texto fora de <options>")
                    opcoes_xml = elemento[0]
                    if (opcoes_xml.attrib or (opcoes_xml.text or "").strip()
                            or (opcoes_xml.tail or "").strip()):
                        raise ValueError("<options> aceita somente elementos <option>")
                    opcoes = []
                    for opcao in opcoes_xml:
                        if (opcao.tag != "option" or opcao.attrib
                                or list(opcao) or (opcao.tail or "").strip()):
                            raise ValueError(
                                "<options> aceita somente elementos <option> textuais")
                        opcoes.append(opcao.text or "")
                    campos["options"] = opcoes
                elif len(elemento) > 1:
                    raise ValueError("<action> aceita no máximo um elemento de conteúdo")
                elif elemento:
                    if (elemento.text or "").strip():
                        raise ValueError("<action> não aceita texto fora do conteúdo")
                    corpo = elemento[0]
                    if corpo.tag not in ("code", "command") or corpo.attrib or list(corpo):
                        raise ValueError(
                            "<action> aceita somente <code> ou <command> textual")
                    campos[corpo.tag] = corpo.text or ""
                    if (corpo.tail or "").strip():
                        raise ValueError("<action> não aceita texto após o conteúdo")
                elif (elemento.text or "").strip():
                    raise ValueError("<action> não aceita texto fora de <code>")
                acoes.append(campos)
            dados = {
                "response": texto_resposta.text or "",
                "actions": acoes,
            }

        if not isinstance(dados, dict) or set(dados) != {"response", "actions"}:
            raise ValueError("resposta deve conter somente 'response' e 'actions'")
        if not isinstance(dados["response"], str):
            raise ValueError("'response' precisa ser texto")
        try:
            dados["response"].encode("utf-8")
        except UnicodeEncodeError as erro:
            raise ValueError("'response' contém Unicode inválido") from erro
        if not isinstance(dados["actions"], list):
            raise ValueError("'actions' precisa ser uma lista")
        resposta.resumo = dados["response"]
        resposta.acoes = []
        for campos in dados["actions"]:
            if not isinstance(campos, dict):
                raise ValueError("cada item de 'actions' precisa ser um objeto")
            resposta.acoes.append(_acao_estruturada(campos))
        decisoes = [acao for acao in resposta.acoes if acao.verbo == "decidir"]
        if decisoes and len(resposta.acoes) != 1:
            raise ValueError(
                "a ação decision deve ser a única ação da resposta")
    except (json.JSONDecodeError, ET.ParseError, RecursionError, ValueError) as erro:
        resposta.valida = False
        resposta.erro = str(erro)
        resposta.acoes.clear()
        resposta.resumo = f"Resposta {formato.upper()} inválida: {erro}"
    return resposta


def parse(texto: str, formato: str = "markdown") -> Resposta:
    """Quebra a resposta em prosa + ações."""
    formato = (formato or "markdown").strip().lower()
    if formato in ("json", "xml"):
        return _resposta_estruturada(texto, formato)
    if formato != "markdown":
        raise ValueError(f"formato de resposta desconhecido: {formato}")

    resposta = Resposta()
    prosa = []
    pos = 0

    for m in FENCE_RE.finditer(texto or ""):
        antes = (texto[pos:m.start()] or "").strip()
        if antes:
            prosa.append(antes)
        pos = m.end()

        info_string = (m.group(1) or "").strip()
        corpo = (m.group(2) or "").rstrip()

        info, corpo_limpo = _do_comentario(corpo)
        origem = "comentario"
        if info is None:
            info = _da_cerca(info_string)
            origem = "cerca"
            corpo_limpo = corpo

        if not info:
            # Bloco de código comum: sem alvo, não vira ação.
            resposta.blocos_soltos += 1
            continue

        lang = (info.get("lang") or info_string.split(":")[0] or "").strip()
        # `dir=` conta como caminho: é assim que o modelo pede para listar ou
        # limitar a busca a uma subpasta.
        caminho = (info.get("file") or info.get("path") or info.get("arquivo")
                   or info.get("dir") or info.get("em") or info.get("pasta"))
        verbo = canonico(info.get("acao") or info.get("action") or "")

        if not verbo:
            # Sem verbo explícito: shell vira comando, o resto vira arquivo.
            verbo = "rodar" if lang.lower() in LANGS_SHELL else (
                "modificar" if caminho else None)
            if verbo:
                origem = "inferido"
        if verbo == "buscar" and not (info.get("termo") or info.get("term")
                                     or info.get("q")):
            resposta.blocos_soltos += 1
            continue
        if verbo in ("criar", "modificar", "apagar", "ler") and not caminho:
            resposta.blocos_soltos += 1
            continue
        if not verbo:
            resposta.blocos_soltos += 1
            continue
        if verbo == "decidir":
            try:
                acao = _acao_decisao_markdown(corpo_limpo, m.group(0))
            except (json.JSONDecodeError, RecursionError, ValueError) as erro:
                resposta.valida = False
                resposta.erro = str(erro)
                resposta.acoes.clear()
                resposta.resumo = "Solicitação de decisão inválida: " + str(erro)
                return resposta
            resposta.acoes.append(acao)
            continue

        resposta.acoes.append(Acao(
            verbo=verbo,
            caminho=caminho,
            conteudo=None if verbo in ("apagar", "buscar") else corpo_limpo,
            lang=lang,
            origem=origem,
            bruto=m.group(0),
            extras=info,
        ))

    cauda = (texto or "")[pos:].strip()
    if cauda:
        prosa.append(cauda)

    # Ações que vivem só na prosa: "acao=fim", "acao=listar dir=src/"
    for linha in "\n".join(prosa).split("\n"):
        m = KITTY_RE.match(linha)
        if not m:
            continue
        info = _pares(m.group("resto"))
        verbo = canonico(info.get("acao") or info.get("action") or "")
        if not verbo:
            continue
        if verbo == "decidir":
            resposta.valida = False
            resposta.erro = (
                "a ação decidir precisa de um bloco Markdown com pergunta e opções")
            resposta.resumo = "Solicitação de decisão inválida: " + resposta.erro
            resposta.acoes.clear()
            return resposta
        resposta.acoes.append(Acao(
            verbo=verbo,
            caminho=(info.get("file") or info.get("path") or info.get("dir")
                     or info.get("em") or info.get("pasta")),
            origem="comentario",
            bruto=linha.strip(),
            extras=info,
        ))

    resposta.resumo = "\n\n".join(prosa).strip()
    decisoes = [acao for acao in resposta.acoes if acao.verbo == "decidir"]
    if decisoes and len(resposta.acoes) != 1:
        resposta.valida = False
        resposta.erro = "a ação decidir deve ser a única ação da resposta"
        resposta.acoes.clear()
    return resposta
