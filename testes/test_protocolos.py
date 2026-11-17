"""Valida os formatos estruturados e a sonda sem executar sua ação de teste."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DEEPSEEK_UI_CONFIG"] = str(
    Path(tempfile.gettempdir()) / "deepseek_ui_protocolos_test.json")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
reconfigure_stdout = getattr(sys.stdout, "reconfigure", None)
if callable(reconfigure_stdout):
    reconfigure_stdout(encoding="utf-8")

from PyQt6.QtWidgets import QApplication, QLabel, QToolButton

from src.agent import Agente, Callbacks
from src.chat import AgentMessage, ChatPanel, CodeCard, DecisionCard
from src.parser import parse
from src.prompts import SONDA_CAMINHO, SONDA_CONTEUDO, montar, prompt_sonda, realimentar
from src.project import Project
from src.session import ProjectSession
from src.theme import Color, stylesheet
from src.window import MainWindow

ok = fail = 0


def checa(nome: str, condicao: bool, detalhe: object = ""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


def _formato_invalido_rejeitado(session):
    try:
        session.salvar_formato_resposta("yaml")
    except ValueError:
        return True
    return False


print("-- 1. JSON estrito e conteúdo completo --")
json_resposta = """```json
{
  "response": "Arquivo preparado.",
  "actions": [
    {"action": "create", "path": "src/a.py", "code": "def soma(a, b):\\n    return a + b\\n"},
    {"action": "search", "term": "soma", "path": "src", "extension": "py"},
    {"action": "run", "command": "pytest -q"},
    {"action": "done"}
  ]
}
```"""
r = parse(json_resposta, "json")
checa("JSON válido", r.valida, r.erro)
checa("texto de resposta extraído", r.resumo == "Arquivo preparado.", r.resumo)
checa("quatro ações extraídas", len(r.acoes) == 4, len(r.acoes))
if len(r.acoes) == 4:
    criar, buscar, rodar, fim = r.acoes
    checa("arquivo e newline preservados",
          criar.verbo == "criar" and criar.caminho == "src/a.py"
          and criar.conteudo == "def soma(a, b):\n    return a + b\n",
          repr(criar.conteudo))
    checa("busca mapeada", buscar.verbo == "buscar"
          and buscar.extras == {"termo": "soma", "ext": "py"}
          and buscar.caminho == "src", buscar)
    checa("comando mapeado", rodar.verbo == "rodar"
          and rodar.conteudo == "pytest -q", rodar)
    checa("done mapeado", fim.verbo == "fim", fim.verbo)
ticks = parse(
    '````json\n{"response":"teste","actions":[{"action":"create",'
    '"path":"a.md","code":"texto ``` interno"}]}\n````',
    "json")
checa("cerca longa permite crases no arquivo",
      bool(ticks.valida and ticks.acoes
           and ticks.acoes[0].conteudo == "texto ``` interno"),
      ticks.erro)
json_decisao = parse(
    '```json\n{"response":"Preciso da sua escolha.","actions":[{"action":'
    '"decision","question":"Qual opção?","options":["A","B"]}]}\n```',
    "json")
checa("JSON reconhece a ação decision",
      json_decisao.valida and len(json_decisao.acoes) == 1
      and json_decisao.acoes[0].extras["opcoes"] == ["A", "B"],
      json_decisao.erro)

print("\n-- 2. JSON inválido não produz ações aplicáveis --")
for nome, resposta in [
    ("sem fence", '{"response":"x","actions":[]}'),
    ("JSON quebrado", '```json\n{"response":\n```'),
    ("quebra de linha literal dentro de string JSON",
     '```json\n{"response":"linha 1\nlinha 2","actions":[]}\n```'),
    ("chave duplicada", '```json\n{"response":"x","response":"y","actions":[]}\n```'),
    ("campo extra", '```json\n{"response":"x","actions":[],"extra":1}\n```'),
    ("chave antiga não aceita", '```json\n{"message":"x","actions":[]}\n```'),
    ("ação extra", '```json\n{"response":"x","actions":[{"action":"delete","path":"a","extra":1}]}\n```'),
    ("ação inválida após ação válida",
     '```json\n{"response":"x","actions":[{"action":"delete","path":"a"},'
     '{"action":"chmod","path":"b"}]}\n```'),
    ("sem response", '```json\n{"actions":[]}\n```'),
    ("criar sem code", '```json\n{"response":"x","actions":[{"action":"create","path":"a"}]}\n```'),
    ("decision misturada com outra ação",
     '```json\n{"response":"x","actions":[{"action":"decision",'
     '"question":"Qual?","options":["A","B"]},{"action":"done"}]}\n```'),
]:
    invalid = parse(resposta, "json")
    checa(nome, not invalid.valida and not invalid.acoes, invalid.erro)

print("\n-- 3. XML fenced preserva CDATA e mapeia ações --")
xml_resposta = """```xml
<response>
<text>Arquivo preparado.</text>
<actions>
<action type="create" path="src/a.py"><code><![CDATA[def soma(a, b):
    return a + b
]]></code></action>
<action type="search" term="soma" path="src" extension="py" />
<action type="run"><command><![CDATA[pytest -q]]></command></action>
<action type="done" />
</actions>
</response>
```"""
r_xml = parse(xml_resposta, "xml")
checa("XML válido", r_xml.valida, r_xml.erro)
checa("texto de resposta XML separado",
      r_xml.resumo == "Arquivo preparado.", r_xml.resumo)
checa("quatro ações XML", len(r_xml.acoes) == 4, len(r_xml.acoes))
if len(r_xml.acoes) == 4:
    checa("CDATA e newlines preservados",
          r_xml.acoes[0].conteudo == "def soma(a, b):\n    return a + b\n",
          repr(r_xml.acoes[0].conteudo))
    checa("busca XML", r_xml.acoes[1].extras == {"termo": "soma", "ext": "py"},
          r_xml.acoes[1].extras)
    checa("comando XML", r_xml.acoes[2].conteudo == "pytest -q",
          r_xml.acoes[2].conteudo)
    checa("fim XML", r_xml.acoes[3].verbo == "fim", r_xml.acoes[3].verbo)
xml_decisao = parse(
    '```xml\n<response><text>Preciso da sua escolha.</text><actions>'
    '<action type="decision" question="Qual opção?"><options>'
    '<option>A</option><option>B</option></options></action>'
    '</actions></response>\n```',
    "xml")
checa("XML reconhece a ação decision",
      xml_decisao.valida and len(xml_decisao.acoes) == 1
      and xml_decisao.acoes[0].extras["opcoes"] == ["A", "B"],
      xml_decisao.erro)

for nome, resposta in [
    ("XML cru recusado", "<response><text>x</text><actions /></response>"),
    ("XML malformado", "```xml\n<response>\n```"),
    ("tipo desconhecido", '```xml\n<response><text>x</text><actions><action type="chmod" path="x"/></actions></response>\n```'),
    ("atributo extra", '```xml\n<response><text>x</text><actions><action type="delete" path="x" extra="1"/></actions></response>\n```'),
    ("ação XML inválida após válida",
     '```xml\n<response><text>x</text><actions>'
     '<action type="delete" path="a"/><action type="chmod" path="b"/>'
     '</actions></response>\n```'),
    ("DTD recusado", '```xml\n<!DOCTYPE response [<!ENTITY x "y">]><response><text>&x;</text><actions /></response>\n```'),
    ("campo XML legado não aceito",
     '```xml\n<response><message>x</message><actions /></response>\n```'),
    ("crases no CDATA", '````xml\n<response><text>teste</text><actions><action type="create" path="a.md"><code><![CDATA[texto ``` interno]]></code></action></actions></response>\n````'),
    ("decision XML misturada com outra ação",
     '```xml\n<response><text>x</text><actions>'
     '<action type="decision" question="Qual?"><options><option>A</option>'
     '<option>B</option></options></action><action type="done"/>'
     '</actions></response>\n```'),
]:
    invalid = parse(resposta, "xml")
    esperado = (invalid.valida and invalid.acoes
                and invalid.acoes[0].conteudo == "texto ``` interno"
                if nome == "crases no CDATA" else not invalid.valida and not invalid.acoes)
    checa(nome, bool(esperado), invalid.erro)

print("\n-- 4. montagem do protocolo e persistência por projeto --")
with tempfile.TemporaryDirectory(prefix="protocolos_") as temp:
    raiz = Path(temp) / "projeto"
    raiz.mkdir()
    session = ProjectSession(raiz)
    checa("markdown padrão", session.formato_resposta() == "markdown")
    checa("salva seleção JSON", session.salvar_formato_resposta("json"))
    checa("formato persiste", ProjectSession(raiz).formato_resposta() == "json")
    checa("formato inválido rejeitado",
          _formato_invalido_rejeitado(session))
    checa("monta instrução JSON", "PROTOCOLO JSON DE RESPOSTA" in
          montar("pedido", Project(raiz), formato="json"))
    checa("processo aparece na primeira mensagem Markdown",
          "PROCESSO DE DESENVOLVIMENTO" in
          montar("pedido", Project(raiz), primeira=True))
    checa("protocolo JSON orienta a pedir decisões",
          '"action":"decision"' in
          montar("pedido", Project(raiz), formato="json"))
    checa("monta leitura por rodada", "uma leitura de arquivo por resposta" in
          montar("pedido", Project(raiz), agente=True, formato="xml"))
    checa("realimentação mantém protocolo", "PROTOCOLO JSON DE RESPOSTA" in
          realimentar("resultado", formato="json", agente=True))
    checa("sonda pede ação inofensiva",
          SONDA_CAMINHO in prompt_sonda("json")
          and SONDA_CONTEUDO in prompt_sonda("json")
          and "sem aplicá-la" in prompt_sonda("json").lower())

    print("\n-- 5. agente repete resposta estruturada inválida --")

    class FakeController:
        is_connected = True

        def __init__(self):
            self.enviadas = []
            self.respostas_recapturadas = []
            self.respostas = [
                "isso não é JSON",
                '```json\n{"response":"Concluído.",'
                '"actions":[{"action":"done"}]}\n```',
            ]

        def send_message(self, texto, on_update=None, on_sent=None):
            _ = on_update
            self.enviadas.append(texto)
            if on_sent:
                on_sent()
            return self.respostas.pop(0)

        def extract_last_response(self):
            if self.respostas_recapturadas:
                return self.respostas_recapturadas.pop(0)
            return None

    class FakeCallbacks(Callbacks):
        def __init__(self):
            self.motivo = ""
            self.decisoes = []

        def fim(self, motivo):
            self.motivo = motivo

        def confirmar_decisao(self, acao):
            self.decisoes.append(acao)
            return "Opção B"

    controller = FakeController()
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("termine a tarefa")
    checa("duas rodadas após erro de formato", len(agente.passos) == 2,
          len(agente.passos))
    checa("segundo envio explica o erro e mantém protocolo",
          "O app não conseguiu interpretar" in controller.enviadas[1]
          and "PROTOCOLO JSON DE RESPOSTA" in controller.enviadas[1],
          controller.enviadas[1])
    checa("agente encerrou após resposta válida", "concluída" in callbacks.motivo,
          callbacks.motivo)

    controller = FakeController()
    decisao = (
        '```json\n{"response":"Qual opção?","actions":[{"action":"decision",'
        '"question":"Qual abordagem?","options":["A","B"]}]}\n```')
    concluido = (
        '```json\n{"response":"Concluído.",'
        '"actions":[{"action":"done"}]}\n```')
    controller.respostas = [decisao] * 13 + [concluido]
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("termine a tarefa")
    checa("agente continua além de 12 rodadas por padrão",
          len(agente.passos) == 14 and len(callbacks.decisoes) == 13,
          (len(agente.passos), len(callbacks.decisoes)))
    checa("agente encerra normalmente depois da 13a rodada",
          "concluída" in callbacks.motivo, callbacks.motivo)

    controller = FakeController()
    controller.respostas = ['```json\n{"response":"\n```']
    controller.respostas_recapturadas = [
        '```json\n{"response":"Concluído.",'
        '"actions":[{"action":"done"}]}\n```'
    ]
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("termine a tarefa")
    checa("recaptura JSON completo do DOM sem reenviar",
          len(controller.enviadas) == 1 and len(agente.passos) == 1
          and agente.passos[0].resposta.endswith("```"),
          (len(controller.enviadas), len(agente.passos)))
    checa("continua após recuperar a resposta completa",
          "concluída" in callbacks.motivo, callbacks.motivo)

    controller = FakeController()
    controller.respostas = [
        '```json\n{"response":"\n```',
        '```json\n{"response":"\n```',
    ]
    controller.respostas_recapturadas = [
        '```json\n{"response":"\n```',
        '```json\n{"response":"Concluído.",'
        '"actions":[{"action":"done"}]}\n```',
    ]
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("termine a tarefa")
    checa("repete recaptura antes de pedir nova resposta ao modelo",
          len(controller.enviadas) == 1 and len(agente.passos) == 1
          and "Concluído." in agente.passos[0].resposta,
          (len(controller.enviadas), len(agente.passos)))

    controller = FakeController()
    controller.respostas = [
        '```json\n{"response":"\n```',
        '```json\n{"response":"\n```',
        '```json\n{"response":"\n```',
        '```json\n{"response":"\n```',
        '```json\n{"response":"ok","actions":[]}\n```',
    ]
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("atualize o vault")
    checa("interrompe após quatro respostas JSON inválidas",
          len(controller.enviadas) == 4 and len(agente.passos) == 4,
          (len(controller.enviadas), len(agente.passos)))
    checa("não continua reenviando erro de formato",
          "interrompida após 4 respostas JSON inválidas" in callbacks.motivo,
          callbacks.motivo)

    controller = FakeController()
    controller.respostas = [
        '```json\n{"response":"Qual opção?","actions":[{"action":"decision",'
        '"question":"Qual abordagem?","options":["A","B"]}]}\n```',
        '```json\n{"response":"Concluído.",'
        '"actions":[{"action":"done"}]}\n```',
    ]
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("faça a tarefa")
    checa("agente aguarda e recebe decisão do usuário",
          len(callbacks.decisoes) == 1
          and "Decisão do usuário" in controller.enviadas[1]
          and "Opção B" in controller.enviadas[1],
          controller.enviadas[1] if len(controller.enviadas) > 1 else "")

    controller = FakeController()
    controller.respostas = [
        '```json\n{"response":"Vou ler.", "actions":['
        '{"action":"read","path":"a.txt"},'
        '{"action":"read","path":"b.txt"}]}\n```',
        '```json\n{"response":"Concluído.",'
        '"actions":[{"action":"done"}]}\n```',
    ]
    callbacks = FakeCallbacks()
    agente = Agente(controller, Project(raiz), callbacks, formato="json")
    agente.rodar("analise os arquivos")
    checa("agente rejeita dois pedidos de leitura",
          not agente.passos[0].leituras
          and "um pedido de leitura" in controller.enviadas[1],
          controller.enviadas[1])
    checa("segue após resposta com um pedido",
          "concluída" in callbacks.motivo, callbacks.motivo)

    print("\n-- 6. sonda UI valida e nunca aplica --")
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet())
    resposta_visual = parse("""```json
{"response":"Texto normal que vai aparecer.","actions":[
  {"action":"create","path":"eusouocodigo.py","code":"print('Eu sou o código')"}
]}
```""", "json")
    mensagem_visual = AgentMessage()
    mensagem_visual.set_structured_content(resposta_visual)
    codigo_visual = mensagem_visual.findChildren(CodeCard)
    textos_visuais = mensagem_visual.findChildren(QLabel)
    checa("JSON renderiza resposta e código separados",
          resposta_visual.valida and len(codigo_visual) == 1
          and codigo_visual[0].code == "print('Eu sou o código')"
          and codigo_visual[0].findChild(QLabel, "codeLang").text() == "PY"
          and any("Texto normal que vai aparecer." in widget.text()
                  for widget in textos_visuais))
    xml_visual = parse(
        '```xml\n<response><text>Texto XML normal.</text><actions>'
        '<action type="create" path="arquivo.py"><code><![CDATA[print(1)'
        ']]></code></action></actions></response>\n```',
        "xml")
    mensagem_xml_visual = AgentMessage()
    mensagem_xml_visual.set_structured_content(xml_visual)
    codigo_xml_visual = mensagem_xml_visual.findChildren(CodeCard)
    checa("XML renderiza resposta e código separados",
          xml_visual.valida and len(codigo_xml_visual) == 1
          and codigo_xml_visual[0].code == "print(1)",
          xml_visual.erro)
    escolhas_visuais = []
    for formato_decisao, resposta_decisao in [
        ("markdown", """Confirme uma escolha.

```text
# kitty: acao=decidir
{"question":"Qual opção?","options":["A","B"]}
```"""),
        ("json", '```json\n{"response":"Confirme.","actions":[{"action":'
         '"decision","question":"Qual opção?","options":["A","B"]}]}\n```'),
        ("xml", '```xml\n<response><text>Confirme.</text><actions>'
         '<action type="decision" question="Qual opção?"><options>'
         '<option>A</option><option>B</option></options></action>'
         '</actions></response>\n```'),
    ]:
        parsed_decisao = parse(resposta_decisao, formato=formato_decisao)
        painel_decisao = ChatPanel()
        painel_decisao.start_agent()
        painel_decisao.finish_agent(
            resposta_decisao, parsed_decisao, formato=formato_decisao,
            on_decision=lambda _acao, valor: escolhas_visuais.append(valor))
        cards_decisao = painel_decisao.findChildren(DecisionCard)
        botoes_decisao = (
            cards_decisao[0].findChildren(QToolButton, "decisionOption")
            if cards_decisao else [])
        if len(botoes_decisao) == 2:
            botoes_decisao[1].click()
        checa(f"card de decisão visualizado em {formato_decisao.upper()}",
              parsed_decisao.valida and len(cards_decisao) == 1
              and escolhas_visuais[-1:] == ["B"],
              parsed_decisao.erro)
        painel_decisao.deleteLater()
    historico_visual = ChatPanel()
    historico_visual.load_history(
        [{"role": "assistant", "content": """```json
{"response":"Histórico normal.","actions":[
  {"action":"create","path":"salvo.py","code":"print(2)"}
]}
```"""},
         {"role": "assistant", "content": """```xml
<response><text>Histórico XML.</text><actions>
<action type="create" path="salvo2.py"><code><![CDATA[print(3)]]></code></action>
</actions></response>
```"""}],
        formato="json")
    mensagens_historico = historico_visual.findChildren(AgentMessage)
    codigos_historico = historico_visual.findChildren(CodeCard)
    checa("histórico JSON também reidrata os cards",
          len(mensagens_historico) == 2 and len(codigos_historico) == 2
          and {card.code for card in codigos_historico}
          == {"print(2)", "print(3)"})
    mensagem_visual.deleteLater()
    mensagem_xml_visual.deleteLater()
    historico_visual.deleteLater()

    janela = MainWindow()
    janela._set_project(str(raiz), avisar=False)
    envio_decisao = []
    janela.input.setPlainText("rascunho preservado")
    janela._send = lambda: envio_decisao.append(janela.input.toPlainText())
    janela._enviar_decisao(json_decisao.acoes[0], "B")
    checa("escolha comum vira continuação sem apagar rascunho",
          len(envio_decisao) == 1
          and "Minha decisão para “Qual opção?”: B" in envio_decisao[0]
          and janela.input.toPlainText() == "rascunho preservado",
          envio_decisao)
    janela._formato_envio = "json"
    pendente = janela.chat.start_agent()
    bruto_parcial = '```json\n{"response":"texto secreto","actions":[]}'
    janela._atualizar_resposta_parcial(bruto_parcial)
    checa("JSON parcial só mostra indicador até validação",
          "response" not in pendente._raw
          and "Recebendo resposta JSON" in pendente._raw)
    resposta_invalida = parse('```json\n{"response":\n```', formato="json")
    janela.chat.finish_agent(bruto_parcial, resposta_invalida)
    invalida_visual = janela.chat._holder.findChildren(AgentMessage)[-1]
    checa("JSON inválido também nunca aparece cru",
          "response" not in invalida_visual._raw
          and "inválida" in invalida_visual._raw)
    checa("UI expõe a captura que causou a rejeição",
          any(isinstance(card, CodeCard) and '{"response":' in card.code
              for card in invalida_visual.findChildren(CodeCard)))
    checa("retorno habilitado mesmo desconectado",
          not janela.controller.is_connected and janela.cmb_formato.isEnabled())
    checa("lista de retorno usa tema escuro com contraste",
          janela.cmb_formato.objectName() == "responseFormat"
          and janela.cmb_formato.view().objectName() == "responseFormatOptions"
          and "QAbstractItemView#responseFormatOptions"
          in stylesheet()
          and janela.cmb_formato.view().palette().color(
              janela.cmb_formato.view().palette().ColorRole.Base).name()
          == Color.SURFACE_ALT.lower()
          and janela.cmb_formato.view().palette().color(
              janela.cmb_formato.view().palette().ColorRole.Text).name()
          == Color.TEXT.lower())
    janela.cmb_formato.setCurrentIndex(janela.cmb_formato.findData("json"))
    checa("seleção desconectada salva no projeto",
          ProjectSession(raiz).formato_resposta() == "json")
    janela._formato_em_uso = True
    janela._atualizar_estado_formato()
    checa("retorno bloqueado durante envio", not janela.cmb_formato.isEnabled())
    janela._formato_em_uso = False
    janela._atualizar_estado_formato()
    resposta_sonda = (
        '```json\n{"response":"Teste de formato recebido.", "actions":'
        f'[{{"action":"create","path":"{SONDA_CAMINHO}",'
        f'"code":"{SONDA_CONTEUDO}"}}]}}\n```')
    janela._registrar_resultado_sonda(resposta_sonda, "json")
    checa("ação da sonda não foi aplicada",
          not (raiz / SONDA_CAMINHO).exists())
    checa("resultado JSON salvo",
          ProjectSession(raiz).sondas_formato()["json"]
          == {"tests": 1, "valid": 1})
    janela._registrar_resultado_sonda(
        '```xml\n<response><text>Teste de formato recebido.</text><actions /></response>\n```',
        "xml")
    checa("sonda inválida contabilizada sem ação",
          ProjectSession(raiz).sondas_formato()["xml"]
          == {"tests": 1, "valid": 0})
    resposta_sonda_xml = (
        '```xml\n<response><text>Teste de formato recebido.</text><actions>'
        f'<action type="create" path="{SONDA_CAMINHO}"><code>'
        f'<![CDATA[{SONDA_CONTEUDO}]]></code></action>'
        '</actions></response>\n```')
    janela._registrar_resultado_sonda(resposta_sonda_xml, "xml")
    checa("sonda XML válida também não escreve",
          not (raiz / SONDA_CAMINHO).exists()
          and ProjectSession(raiz).sondas_formato()["xml"]
          == {"tests": 2, "valid": 1})
    checa("contador exibido na UI", "JSON: 1/1" in janela.lbl_sondas.text()
          and "XML: 1/2" in janela.lbl_sondas.text(), janela.lbl_sondas.text())
    outro_projeto = Path(temp) / "outro"
    outro_projeto.mkdir()
    ProjectSession(outro_projeto).salvar_formato_resposta("xml")
    janela._set_project(str(outro_projeto), avisar=False)
    checa("formato carregado do novo projeto",
          janela._formato_atual() == "xml")
    janela._set_project(str(raiz), avisar=False)
    checa("formato e estatísticas isolados por projeto",
          janela._formato_atual() == "json"
          and "JSON: 1/1" in janela.lbl_sondas.text()
          and "XML: 1/2" in janela.lbl_sondas.text(), janela.lbl_sondas.text())
    janela.close()

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
