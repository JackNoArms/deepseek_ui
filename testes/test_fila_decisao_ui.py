"""Fila visível/editável/cancelável, card de decisão e temas, pela janela real.

Plano: [[Planos/Remap visual, decisões, fila e importação de skills]].
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DEEPSEEK_UI_CONFIG"] = os.path.join(
    tempfile.gettempdir(), "deepseek_ui_teste_fila_decisao.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QMessageBox, QToolButton

from src import anexos
from src.anexos import Anexo
from src.chat import DecisionCard, UserMessage
from src.parser import parse
from src.project import carregar_tema
from src.theme import Color, aplicar_tema, stylesheet
from src.window import MainWindow

QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes

ok = fail = 0


def checa(n, c, e=""):
    global ok, fail
    if c:
        print(f"  ok      {n}")
        ok += 1
    else:
        print(f"  FALHOU  {n} -> {e}")
        fail += 1


class FakeController:
    def __init__(self, respostas, atraso=0.0):
        self.respostas = list(respostas)
        self.enviadas = []
        self.arquivos = []
        self.is_connected = True
        self.atraso = atraso

    def current_url(self):
        return None

    def send_message(self, texto, on_update=None, arquivos=None, on_sent=None):
        self.enviadas.append(texto)
        self.arquivos.append(list(arquivos or []))
        if self.atraso:
            time.sleep(self.atraso)
        if on_sent:
            on_sent()
        return self.respostas.pop(0) if self.respostas else "ok"


def espera(cond, ms=6000):
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: cond() and loop.quit())
    poll.start(20)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    poll.stop()
    return cond()


def png(pasta: Path, nome="tela.png") -> str:
    img = QImage(8, 8, QImage.Format.Format_RGB32)
    img.fill(0x3366FF)
    caminho = pasta / nome
    img.save(str(caminho), "PNG")
    return str(caminho)


def bolhas(w):
    return len(w.chat.findChildren(UserMessage))


base = Path(tempfile.mkdtemp(prefix="filadec_"))
(base / "src").mkdir()
(base / "src" / "app.py").write_text("valor = 1\n", encoding="utf-8")

app = QApplication(sys.argv)
app.setStyleSheet(stylesheet())
w = MainWindow()
w.show()
w._set_project(str(base))

print("-- 1. fila aparece, edita e cancela --")
w.chk_agente.set_state(False)
w.controller = FakeController(["r1", "r2", "r3"], atraso=0.3)
for texto in ("primeira", "segunda", "terceira"):
    w.input.setPlainText(texto)
    w._send()
checa("duas na fila", len(w._fila_mensagens) == 2, len(w._fila_mensagens))
checa("painel da fila visível", w.painel_fila.isVisible())
checa("painel lista os dois itens", len(w.painel_fila._itens) == 2,
      len(w.painel_fila._itens))
checa("só a mensagem enviada virou bolha", bolhas(w) == 1, bolhas(w))
ids = [p[4] for p in w._fila_mensagens]
checa("contador continua", w.lbl_queue.text() == "Fila: 2", w.lbl_queue.text())
checa("edita item na fila", w._editar_texto_fila(ids[1], "terceira EDITADA"))
checa("texto editado guardado", w._fila_mensagens[1][0] == "terceira EDITADA")
checa("texto vazio não edita", not w._editar_texto_fila(ids[1], "   "))
checa("cancela item da fila", w._cancelar_da_fila(ids[0]))
checa("cancelar de novo não acha", not w._cancelar_da_fila(ids[0]))
checa("painel com um item", len(w.painel_fila._itens) == 1)
if w.remote:
    itens = w.remote.snapshot().get("queue_items")
    checa("estado remoto traz itens da fila",
          [i["texto"] for i in itens] == ["terceira EDITADA"], itens)
espera(lambda: not w._envio_em_andamento and not w._fila_mensagens
       and len(w.controller.enviadas) == 2)
checa("cancelada não foi enviada",
      not any("segunda" in t for t in w.controller.enviadas), w.controller.enviadas)
checa("editada foi enviada",
      any("terceira EDITADA" in t for t in w.controller.enviadas), w.controller.enviadas)
checa("bolha entra quando sai da fila", bolhas(w) == 2, bolhas(w))
checa("painel some com fila vazia", not w.painel_fila.isVisible())

print("\n-- 2. cancelar/limpar descarta anexo temporário --")
tmp = base / "temp.png"
tmp.write_bytes(b"x")
w.controller = FakeController(["a", "b"], atraso=0.3)
w.input.setPlainText("ocupa")
w._send()
w._enfileirar_ou_iniciar("com anexo", False,
                         [Anexo("temp.png", "upload", caminho=str(tmp), temporario=True)])
checa("item com anexo enfileirado",
      w._itens_fila()[0]["anexos"] == ["temp.png"], w._itens_fila())
checa("limpar fila devolve total", w._limpar_fila() == 1)
checa("temporário apagado", not tmp.exists())
espera(lambda: not w._envio_em_andamento)

print("\n-- 3. card de decisão: recomendada, escolha e veredito --")
DECISAO = ('```json\n{"response":"Escolha.","actions":[{"action":"decision",'
           '"question":"Qual abordagem?","options":["A","B","C"],'
           '"recommended":2,"reason":"mais simples"}]}\n```')
acao = parse(DECISAO, "json").acoes[0]
escolhas = []
card = DecisionCard(acao, lambda *args: escolhas.append(args))
botoes = card.findChildren(QToolButton, "decisionOption")
checa("recomendada marcada", botoes[1].property("recomendada") is True)
botoes[1].click()
checa("escolhida marcada", botoes[1].property("escolhida") is True)
checa("card resolvido", card.property("estado") == "resolvida")
checa("veredito: seguiu", card.lbl_veredito.property("tom") == "segue"
      and "Seguiu" in card.lbl_veredito.text(), card.lbl_veredito.text())
checa("mostra sua escolha", "B" in card.lbl_escolha.text())
checa("callback com 2 argumentos sem anexo", len(escolhas[0]) == 2)

card2 = DecisionCard(acao, lambda *a: None)
card2.findChildren(QToolButton, "decisionOption")[0].click()
checa("veredito: divergiu", card2.lbl_veredito.property("tom") == "diverge")

print("\n-- 4. outra resposta: cancelar e anexar imagem --")
recebidos = []
card3 = DecisionCard(acao, lambda *args: recebidos.append(args))
card3.show()
card3._other()
checa("área livre aberta", card3.other_area.isVisible())
card3.other_input.setPlainText("rascunho")
card3._anexar_arquivos([png(base, "rasc.png")])
card3._cancel_other()
checa("cancelar fecha sem decidir",
      not card3.other_area.isVisible() and not card3.settled and not recebidos)
checa("cancelar limpa texto e anexos",
      not card3.other_input.toPlainText() and not card3.anexos)
card3._other()
card3.other_input.setPlainText("Nenhuma, olha o print")
card3._anexar_arquivos([png(base)])
checa("chip do anexo visível", card3.barra_anexos.isVisible())
card3._submit_other()
checa("callback recebe anexos",
      recebidos and len(recebidos[0]) == 3 and len(recebidos[0][2]) == 1, recebidos)
checa("título de resposta livre", "resposta livre" in card3.findChild(
    type(card3.lbl_escolha), "decisionTitle").text())

print("\n-- 5. decisão vai para o histórico --")
w.chat.registrar_decisao(acao, "B", "pc")
w.chat.registrar_decisao(acao, None, "pc")
regs = [m for m in w.chat.historico if m["role"] == "decision"]
checa("decisão registrada com recomendada e escolha",
      regs[-2]["decision"]["escolha"] == "B"
      and regs[-2]["decision"]["recomendada"] == 2, regs[-2])
checa("cancelamento registrado", regs[-1]["decision"]["escolha"] is None)

print("\n-- 6. agente: imagem da resposta livre sobe na rodada seguinte --")
w4 = MainWindow()
w4.show()
w4._set_project(str(base))
w4.chk_agente.set_state(True)
w4.cmb_formato.setCurrentIndex(w4.cmb_formato.findData("json"))
w4.controller = FakeController([
    DECISAO,
    '```json\n{"response":"Feito.","actions":[{"action":"done"}]}\n```',
])
imagem = png(base, "resposta.png")


def responder_com_imagem():
    cards = [c for c in w4.chat.findChildren(DecisionCard) if not c.settled]
    if not cards:
        QTimer.singleShot(20, responder_com_imagem)
        return
    c = cards[-1]
    c._other()
    c.other_input.setPlainText("Faz do meu jeito")
    c._anexar_arquivos([imagem])
    c._submit_other()


QTimer.singleShot(0, responder_com_imagem)
w4.input.setPlainText("decide aí")
w4._send()
espera(lambda: w4._agente is None, 15000)
checa("duas rodadas", len(w4.controller.enviadas) == 2, len(w4.controller.enviadas))
checa("resposta livre chegou ao modelo",
      len(w4.controller.enviadas) == 2
      and "Faz do meu jeito" in w4.controller.enviadas[1])
checa("imagem subiu na rodada 2",
      len(w4.controller.arquivos) == 2
      and w4.controller.arquivos[1] == [str(Path(imagem).resolve())],
      w4.controller.arquivos)
regs = [m for m in w4.chat.historico if m["role"] == "decision"]
checa("histórico guarda anexo da decisão",
      regs and regs[-1]["decision"]["anexos"] == ["resposta.png"], regs)
w4.close()

print("\n-- 7. temas --")
w._trocar_tema("alto_contraste_claro")
checa("tema ativo trocado", Color.NOME == "alto_contraste_claro" and Color.BG == "#FFFFFF")
checa("QSS do app regerado", "background: #FFFFFF" in app.styleSheet())
checa("tema salvo no config", carregar_tema() == "alto_contraste_claro")
w.chk_agente.set_state(True)
checa("pílula ligada usa o acento do tema novo",
      Color.ACCENT.lower() in w.chk_agente.styleSheet().lower(),
      w.chk_agente.styleSheet()[:120])
if w.remote:
    checa("celular recebe o tema", w.remote.snapshot().get("theme") == "alto_contraste_claro")
marcados = [a.data() for a in w._grupo_tema.actions() if a.isChecked()]
checa("menu marca só o tema ativo", marcados == ["alto_contraste_claro"], marcados)
w.chk_agente.set_state(False)
w._trocar_tema("papel")
checa("pílula desligada repinta na troca",
      Color.TEXT_DIM.lower() in w.chk_agente.styleSheet().lower(),
      w.chk_agente.styleSheet()[:120])
w._trocar_tema("nao-existe")
checa("tema inválido cai no padrão", Color.NOME == "grafite")
aplicar_tema("grafite")

w.close()
shutil.rmtree(base, ignore_errors=True)
try:
    os.unlink(os.environ["DEEPSEEK_UI_CONFIG"])
except OSError:
    pass
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
