"""Chat: sem texto sobreposto, sem área vazia no fim, rolagem que respeita a
leitura e recomendação do DeepSeek nas decisões."""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton

from src.chat import ChatPanel, DecisionCard
from src.parser import parse
from src.prompts import REGRAS_DECISAO_MARKDOWN, REGRAS_JSON, REGRAS_XML
from src.theme import stylesheet

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


def bloco(acoes, texto="Resposta."):
    return ("```json\n" + json.dumps({"response": texto, "actions": acoes},
                                     ensure_ascii=False) + "\n```")


DECISAO = {"action": "decision", "question": "Como seguir?",
           "options": ["Escala CSS", "Presets com zoom", "Botões A-/A/A+"]}

print("-- 1. recomendação no protocolo --")
r = parse(bloco([{**DECISAO, "recommended": 2, "reason": "menos refactor"}]), "json")
checa("JSON aceita recommended e reason", r.valida, r.erro)
checa("guarda número e motivo",
      r.acoes and r.acoes[0].extras.get("recomendada") == 2
      and r.acoes[0].extras.get("motivo") == "menos refactor", r.acoes and r.acoes[0].extras)
r = parse(bloco([{**DECISAO, "recommended": "Botões A-/A/A+"}]), "json")
checa("recommended pelo texto da opção vira número",
      r.valida and r.acoes[0].extras.get("recomendada") == 3, (r.erro, r.acoes))
r = parse(bloco([DECISAO]), "json")
checa("sem recommended continua válido (não gera rodada de erro)",
      r.valida and "recomendada" not in r.acoes[0].extras, r.erro)
r = parse(bloco([{**DECISAO, "recommended": 7}]), "json")
checa("recommended fora das opções é recusado", not r.valida and "fora" in r.erro, r.erro)
r = parse(bloco([{**DECISAO, "recommended": True}]), "json")
checa("booleano não vale como número", not r.valida, r.erro)
r = parse(bloco([{"action": "done", "reason": "x"}]), "json")
checa("reason fora de decision continua proibido", not r.valida, r.erro)

xml = ('```xml\n<response><text>t</text><actions><action type="decision" '
       'question="Como seguir?" recommended="1" reason="mais limpo"><options>'
       '<option>A</option><option>B</option></options></action></actions></response>\n```')
r = parse(xml, "xml")
checa("XML aceita recommended e reason",
      r.valida and r.acoes[0].extras.get("recomendada") == 1
      and r.acoes[0].extras.get("motivo") == "mais limpo", r.erro)

md = ('Preciso decidir.\n\n```text\n# kitty: acao=decidir\n'
      '{"question":"Qual?","options":["A","B"],"recommended":2,"reason":"porque sim"}\n```')
r = parse(md, "markdown")
checa("Markdown aceita recommended e reason",
      r.valida and r.acoes[0].extras.get("recomendada") == 2, r.erro)

checa("regras JSON pedem a recomendação", '"recommended"' in REGRAS_JSON
      and '"reason"' in REGRAS_JSON)
checa("regras XML pedem a recomendação", "recommended" in REGRAS_XML)
checa("regras Markdown pedem a recomendação", '"recommended"' in REGRAS_DECISAO_MARKDOWN)

app = QApplication.instance() or QApplication(sys.argv)
app.setStyleSheet(stylesheet())


def esperar(ms=120):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


print("\n-- 2. card mostra a recomendação --")
acao = parse(bloco([{**DECISAO, "recommended": 2, "reason": "menos refactor"}]),
             "json").acoes[0]
escolhas = []
card = DecisionCard(acao, lambda _a, valor: escolhas.append(valor))
textos = [l.text() for l in card.findChildren(QLabel)]
checa("texto da recomendação com motivo",
      any("Recomendação do DeepSeek" in t and "opção 2" in t and "menos refactor" in t
          for t in textos), textos)
botoes = card.findChildren(QToolButton, "decisionOption")
checa("opção recomendada marcada", "★ recomendada" in botoes[1].text()
      and botoes[1].property("recomendada") is True, botoes[1].text())
checa("as outras não", all("★" not in b.text() for b in (botoes[0], botoes[2])))
botoes[1].click()
checa("escolha devolve o texto limpo da opção", escolhas == ["Presets com zoom"], escolhas)

print("\n-- 3. sem sobreposição durante a decisão --")
TEXTO = "Ainda não implementei: isso é escopo novo, fora da fila atual. " * 8
chat = ChatPanel()
chat.resize(1200, 700)
chat.show()
resultado = {}


def rodada_com_decisao():
    chat.start_agent()
    chat.update_agent("Recebendo resposta JSON; será exibida após validação…")
    texto = bloco([DECISAO], TEXTO)
    lido = parse(texto, "json")
    # Igual ao app: resposta e decisão processadas na mesma passada, com a
    # decisão abrindo um loop aninhado — a exclusão adiada não roda ali dentro.
    chat.finish_agent(texto, lido, formato="json", show_decisions=False)
    chat.add_decision(lido.acoes[0], lambda *_: None)
    aninhado = QEventLoop()

    def medir():
        resultado["placeholder_visivel"] = any(
            "Recebendo resposta" in l.text() and l.isVisible()
            for l in chat.widget().findChildren(QLabel))
        aninhado.quit()
    QTimer.singleShot(300, medir)
    aninhado.exec()
    principal.quit()


principal = QEventLoop()
QTimer.singleShot(50, rodada_com_decisao)
principal.exec()
checa("placeholder some antes da decisão", resultado.get("placeholder_visivel") is False,
      resultado)

print("\n-- 4. sem área vazia no fim --")
chat = ChatPanel()
chat.resize(1200, 600)
chat.show()
for i in range(6):
    chat.add_system(f"— rodada {i} —")
    chat.start_agent()
    chat.finish_agent(f"[{i}] " + TEXTO)
esperar(200)
holder = chat.widget()
ultimo = [chat._lay.itemAt(i).widget() for i in range(chat._lay.count())
          if chat._lay.itemAt(i).widget() is not None][-1]
fim = ultimo.mapTo(holder, ultimo.rect().bottomLeft()).y()
vazio = holder.height() - fim
checa("conteúdo termina no fim da área rolável", vazio <= 20, f"{vazio}px vazios")

print("\n-- 5. rolagem respeita a leitura --")
bar = chat.verticalScrollBar()
bar.setValue(bar.maximum())
esperar()
chat.add_system("nota nova")
esperar()
checa("no fim, acompanha o que chega", bar.value() == bar.maximum(),
      (bar.value(), bar.maximum()))
bar.setValue(0)
esperar()
chat.add_system("outra nota")
chat.start_agent()
chat.finish_agent("curta")
esperar()
checa("lendo lá em cima, nada puxa para baixo", bar.value() == 0, bar.value())

checa("lendo lá em cima, botão Ir para o fim aparece",
      chat.btn_fim.isVisible(), chat.btn_fim.text())

bar.setValue(bar.maximum())
esperar()
checa("de volta ao fim, botão some", not chat.btn_fim.isVisible())
pendente = chat.start_agent()
parcial = "INICIO DA LONGA "
for _ in range(10):
    parcial += TEXTO
    chat.update_agent(parcial)
    esperar(40)
checa("barra acompanha a resposta enquanto chega",
      bar.value() == bar.maximum(), (bar.value(), bar.maximum()))

bar.setValue(max(0, bar.maximum() - 900))
esperar()
posicao = bar.value()
for _ in range(4):
    parcial += TEXTO
    chat.update_agent(parcial)
    esperar(40)
checa("subir durante a resposta solta: nada puxa de volta",
      bar.value() == posicao, (bar.value(), posicao, bar.maximum()))
checa("botão avisa que chegou resposta nova",
      chat.btn_fim.isVisible() and "Nova resposta" in chat.btn_fim.text(),
      chat.btn_fim.text())
chat.finish_agent(parcial)
esperar(200)
checa("fim da resposta também não puxa quem está lendo",
      bar.value() == posicao, (bar.value(), posicao))
chat.btn_fim.click()
esperar()
checa("botão leva ao fim", bar.value() == bar.maximum())
chat.add_decision(acao, lambda *_: None)
esperar(200)
checa("depois do botão volta a acompanhar",
      bar.value() == bar.maximum() and not chat.btn_fim.isVisible(),
      (bar.value(), bar.maximum()))
roda = QWheelEvent(QPointF(50, 50), QPointF(chat.mapToGlobal(QPoint(50, 50))),
                   QPoint(0, 0), QPoint(0, 360), Qt.MouseButton.NoButton,
                   Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
QApplication.sendEvent(chat.viewport(), roda)
esperar()
antes = bar.value()
chat.start_agent()
chat.finish_agent("chegou depois da roda " + TEXTO * 3)
esperar(200)
checa("roda do mouse para cima solta o acompanhamento",
      antes < bar.maximum() and bar.value() == antes, (antes, bar.value(), bar.maximum()))
bar.setValue(0)
esperar()
bar.setValue(bar.maximum())
esperar()
chat.add_system("depois de rolar até o fim")
esperar()
checa("rolar até o fim com a barra volta a acompanhar",
      bar.value() == bar.maximum(), (bar.value(), bar.maximum()))

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
