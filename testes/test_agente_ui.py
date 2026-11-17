"""Modo agente pela UI de verdade: QThread + confirmacao bloqueante + runner."""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# config descartavel: teste nao mexe na ultima pasta do usuario
os.environ["DEEPSEEK_UI_CONFIG"] = os.path.join(
    tempfile.gettempdir(), "deepseek_ui_teste_workspace.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QToolButton
from src.chat import DecisionCard
from src.theme import stylesheet
from src.window import MainWindow
from src.permissions import PermissionPolicy
from src.project import Project

# Os testes exercitam o loop sem interação humana e registram cada consentimento.
consentimentos = []
decisao_consentimento = QMessageBox.StandardButton.Yes
def autoriza_compartilhamento(*args, **kwargs):
    consentimentos.append(args[1])
    return decisao_consentimento
QMessageBox.question = autoriza_compartilhamento

ok = fail = 0
F = "```"

def checa(n, c, e=""):
    global ok, fail
    if c: print(f"  ok      {n}"); ok += 1
    else: print(f"  FALHOU  {n} -> {e}"); fail += 1


class FakeController:
    """`atraso` imita o tempo real de resposta do DeepSeek.

    Sem ele, o loop inteiro termina antes de qualquer QTimer disparar, e testar
    o botao Parar fica impossivel: o teto de iteracoes chega primeiro.
    """

    def __init__(self, respostas, atraso=0.0):
        self.respostas = list(respostas); self.enviadas = []
        self.is_connected = True; self.atraso = atraso
    def current_url(self): return None
    def send_message(self, texto, on_update=None, arquivos=None, on_sent=None):
        self.enviadas.append(texto)
        if self.atraso:
            time.sleep(self.atraso)
        if on_sent:
            on_sent()
        return self.respostas.pop(0) if self.respostas else f"{F}\n# kitty: acao=fim\n{F}"


def roda_ate_fim(w, app, timeout_ms=15000):
    """Espera o agente terminar sem travar a GUI."""
    loop = QEventLoop()
    original = w._agente_fim
    def envolvido(motivo):
        original(motivo)
        loop.quit()
    w._agente_fim = envolvido
    w._agente.fim_sig.disconnect()
    w._agente.fim_sig.connect(envolvido)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    w._agente_fim = original


base = Path(tempfile.mkdtemp(prefix="agui_"))
(base / "src").mkdir()
(base / "src" / "app.py").write_text("valor = 1\n", encoding="utf-8")

app = QApplication(sys.argv)
app.setStyleSheet(stylesheet())
w = MainWindow()
w.show()          # sem show(), todo widget filho reporta invisivel e o teste mente
w._set_project(str(base))
w.chk_agente.set_state(True)

print("-- 1. ciclo ler -> escrever -> fim, com aprovacao --")
w.controller = FakeController([
    f"Vou ver o arquivo.\n\n{F}\n# kitty: acao=ler file=src/app.py\n{F}",
    f"{F}python\n# kitty: file=src/app.py acao=modificar\nvalor = 99\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
# aprova tudo sem abrir dialogo
import src.window as W
W.revisar = lambda planos, parent=None: [p for p in planos if p.aplicavel]

w.input.setPlainText("troque para 99")
w._send()
checa("agente comecou", w._agente is not None)
checa("botao Parar visivel", w.btn_stop.isVisible())
checa("Enviar fica disponível para enfileirar",
      w.btn_send.isEnabled() and w.btn_send.text() == "Enfileirar",
      w.btn_send.text())
roda_ate_fim(w, app)

checa("agente terminou", w._agente is None)
checa("pediu consentimento para estrutura e leitura",
      "Autorizar compartilhamento da estrutura" in consentimentos
      and "Autorizar leitura e compartilhamento" in consentimentos,
      consentimentos)
decisao_consentimento = QMessageBox.StandardButton.No
checa("recusar estrutura omite o mapa",
      not w._autorizar_compartilhamento_estrutura())
decisao_consentimento = QMessageBox.StandardButton.Yes
checa("botao Parar escondido", not w.btn_stop.isVisible())
checa("Enviar reabilitado", w.btn_send.isEnabled())
checa("arquivo gravado",
      (base / "src" / "app.py").read_text(encoding="utf-8") == "valor = 99",
      repr((base / "src" / "app.py").read_text(encoding="utf-8")))
checa("3 mensagens enviadas", len(w.controller.enviadas) == 3, len(w.controller.enviadas))
checa("2a levou o arquivo lido", "valor = 1" in w.controller.enviadas[1])
checa("DeepSeek recebeu confirmação de aplicação, não uma falsa recusa",
      "aplicado" in w.controller.enviadas[2]
      and "recusou as alterações" not in w.controller.enviadas[2],
      w.controller.enviadas[2][:240])
checa("nao aplicou duas vezes",
      (base / "src" / "app.py").read_text(encoding="utf-8").count("valor") == 1)

print("\n-- 1b. criacao aprovada reportada como aplicada --")
W.revisar = lambda planos, parent=None: [p for p in planos if p.aplicavel]
w.controller = FakeController([
    f"{F}python\n# kitty: file=src/novo.py acao=criar\nprint('novo')\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
w.input.setPlainText("crie um arquivo novo")
w._send()
roda_ate_fim(w, app)
checa("arquivo novo criado apos aprovacao",
      (base / "src" / "novo.py").read_text(encoding="utf-8") == "print('novo')",
      repr((base / "src" / "novo.py").read_text(encoding="utf-8")
           if (base / "src" / "novo.py").exists() else "ausente"))
checa("DeepSeek recebeu confirmacao da criacao, nao uma falsa recusa",
      "src/novo.py" in w.controller.enviadas[1]
      and "aplicado" in w.controller.enviadas[1]
      and "recusou" not in w.controller.enviadas[1],
      w.controller.enviadas[1][:240])

print("\n-- 2. recusa do usuario volta ao modelo --")
(base / "src" / "app.py").write_text("valor = 99\n", encoding="utf-8")
W.revisar = lambda planos, parent=None: []
w.controller = FakeController([
    f"{F}python\n# kitty: file=src/app.py acao=modificar\nESTRAGADO\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
w.input.setPlainText("estrague")
w._send()
roda_ate_fim(w, app)
checa("arquivo intacto",
      (base / "src" / "app.py").read_text(encoding="utf-8") == "valor = 99\n",
      repr((base / "src" / "app.py").read_text(encoding="utf-8")))
checa("modelo soube que nada foi selecionado",
      "foi selecionada para aplicação" in w.controller.enviadas[1],
      w.controller.enviadas[1][:120])

print("\n-- 3. modo automático também reporta a aplicação real --")
w.project = Project(base, PermissionPolicy(base, "computer_auto"))
W.revisar = lambda planos, parent=None: []
w.controller = FakeController([
    f"{F}python\n# kitty: file=src/app.py acao=modificar\n"
    "valor = 123\n"
    f"{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
w.input.setPlainText("troque para 123")
w._send()
roda_ate_fim(w, app)
checa("modo automático aplicou o arquivo",
      (base / "src" / "app.py").read_text(encoding="utf-8") == "valor = 123",
      (base / "src" / "app.py").read_text(encoding="utf-8"))
checa("modo automático não reportou falsa recusa",
      "aplicado" in w.controller.enviadas[1]
      and "recusou as alterações" not in w.controller.enviadas[1],
      w.controller.enviadas[1][:240])

print("\n-- 3b. projeto automático aceita edição do vault com backup --")
w.project = Project(base, PermissionPolicy(base, "project_auto"))
nota_auto = base / "vault" / "auto-agent.md"
nota_auto.write_text("# antes\n", encoding="utf-8")
revisoes = []
W.revisar = lambda planos, parent=None: revisoes.append(planos) or []
w.controller = FakeController([
    f"{F}text\n# kitty: file=vault/auto-agent.md acao=modificar\n"
    "# atualizado automaticamente\n"
    f"{F}\n{F}\n# kitty: acao=fim\n{F}",
])
w.input.setPlainText("atualize a nota")
w._send()
roda_ate_fim(w, app)
checa("perfil projeto_auto aplica vault sem abrir revisão",
      nota_auto.read_text(encoding="utf-8") == "# atualizado automaticamente"
      and not revisoes,
      f"conteúdo={nota_auto.read_text(encoding='utf-8')!r}; "
      f"revisões={len(revisoes)}; agente={w._agente}")
checa("edição automática do vault mantém backup",
      any((base / ".deepseek_ui" / "backups").rglob("auto-agent.md")))
w.project = Project(base)

print("\n-- 4. comando recusado na confirmação não roda --")
W.confirmar_comandos = lambda cmds, cwd, parent=None: []
w.controller = FakeController([
    f"{F}bash\n# kitty: acao=rodar\nrmdir /s /q pasta_inexistente_do_teste\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
w.input.setPlainText("apague tudo")
w._send()
roda_ate_fim(w, app)
checa("projeto intacto", (base / "src" / "app.py").is_file())
checa("modelo soube que nao rodou", "não autorizou" in w.controller.enviadas[1],
      w.controller.enviadas[1][:120])

print("\n-- 5. comando autorizado roda e devolve saida --")
W.confirmar_comandos = lambda cmds, cwd, parent=None: list(cmds)
w.controller = FakeController([
    f"{F}bash\n# kitty: acao=rodar\npython --version\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
w.input.setPlainText("qual a versao")
w._send()
roda_ate_fim(w, app)
checa("saida voltou ao modelo", "Python" in w.controller.enviadas[1],
      w.controller.enviadas[1][:160])

print("\n-- 6. Parar interrompe --")
w.controller = FakeController([f"{F}\n# kitty: acao=ler file=src/app.py\n{F}"] * 30,
                              atraso=0.4)
W.revisar = lambda planos, parent=None: []
w.input.setPlainText("loop")
w._send()
QTimer.singleShot(1000, w._parar_agente)
roda_ate_fim(w, app)
checa("parou antes do teto", len(w.controller.enviadas) < 12, len(w.controller.enviadas))
checa("agente limpo", w._agente is None)

print("\n-- 7. fila FIFO envia mensagens enquanto ocupado --")
w.chk_agente.set_state(False)
w.controller = FakeController(["primeira resposta", "segunda resposta",
                               "terceira resposta"], atraso=0.15)
w.input.setPlainText("primeira")
w._send()
w.input.setPlainText("segunda")
w._send()
w.input.setPlainText("terceira")
w._send()
checa("duas mensagens aparecem na fila", len(w._fila_mensagens) == 2,
      len(w._fila_mensagens))
checa("indicador exibe quantidade pendente", w.lbl_queue.text() == "Fila: 2",
      w.lbl_queue.text())
loop = QEventLoop()
poll = QTimer()
def fila_concluida():
    if (len(w.controller.enviadas) == 3 and not w._envio_em_andamento
            and not w._fila_mensagens):
        loop.quit()
poll.timeout.connect(fila_concluida)
poll.start(20)
QTimer.singleShot(5000, loop.quit)
loop.exec()
poll.stop()
checa("fila foi processada por completo",
      len(w.controller.enviadas) == 3 and not w._fila_mensagens
      and not w._envio_em_andamento,
      (len(w.controller.enviadas), len(w._fila_mensagens), w._envio_em_andamento))
checa("ordem FIFO preservada",
      [next((palavra for palavra in ("primeira", "segunda", "terceira")
             if palavra in texto), "")
       for texto in w.controller.enviadas]
      == ["primeira", "segunda", "terceira"], w.controller.enviadas)
checa("indicador some quando fila esvazia", not w.lbl_queue.text(),
      w.lbl_queue.text())

print("\n-- 8. falha em um envio não trava os próximos --")
class FalhaUmaVez(FakeController):
    def send_message(self, texto, on_update=None, arquivos=None, on_sent=None):
        self.enviadas.append(texto)
        if len(self.enviadas) == 1:
            raise RuntimeError("falha simulada")
        if on_sent:
            on_sent()
        return self.respostas.pop(0)

w.controller = FalhaUmaVez(["resposta após falha"])
w.input.setPlainText("falhar")
w._send()
w.input.setPlainText("continuar")
w._send()
loop = QEventLoop()
poll = QTimer()
def falha_concluida():
    if (len(w.controller.enviadas) == 2 and not w._envio_em_andamento
            and not w._fila_mensagens):
        loop.quit()
poll.timeout.connect(falha_concluida)
poll.start(20)
QTimer.singleShot(5000, loop.quit)
loop.exec()
poll.stop()
checa("fila continua após erro explícito",
      len(w.controller.enviadas) == 2 and not w._fila_mensagens
      and not w._envio_em_andamento,
      (len(w.controller.enviadas), len(w._fila_mensagens), w._envio_em_andamento))
checa("erro visível no chat",
      any("Falha na troca com o DeepSeek" in label.text()
          for label in w.chat._holder.findChildren(QLabel)),
      "aviso de envio ausente")

print("\n-- 9. modo agente sem pasta avisa --")
w2 = MainWindow(); w2.project = None; w2.chk_agente.set_state(True)
w2.controller = FakeController([])
w2.input.setPlainText("faca algo"); w2._send()
checa("nao iniciou agente", w2._agente is None)
w2.close()

print("\n-- 10. agente pausa ate o usuario escolher --")
w4 = MainWindow(); w4.show(); w4._set_project(str(base)); w4.chk_agente.set_state(True)
w4.cmb_formato.setCurrentIndex(w4.cmb_formato.findData("json"))
w4.controller = FakeController([
    '```json\n{"response":"Qual opção?","actions":[{"action":"decision",'
    '"question":"Qual abordagem?","options":["A","B"]}]}\n```',
    '```json\n{"response":"Concluído.",'
    '"actions":[{"action":"done"}]}\n```',
])

def escolher_decisao():
    cards = w4.chat.findChildren(DecisionCard)
    if not cards:
        QTimer.singleShot(20, escolher_decisao)
        return
    botoes = cards[-1].findChildren(QToolButton, "decisionOption")
    if len(botoes) == 2:
        botoes[1].click()

QTimer.singleShot(0, escolher_decisao)
w4.input.setPlainText("faça uma alteração")
w4._send()
roda_ate_fim(w4, app)
checa("escolha liberou a próxima rodada do agente",
      len(w4.controller.enviadas) == 2
      and "Decisão do usuário" in w4.controller.enviadas[1]
      and ": B." in w4.controller.enviadas[1],
      len(w4.controller.enviadas))
checa("card registra a decisão escolhida",
      any("DECISÃO REGISTRADA: B" in label.text()
          for label in w4.chat.findChildren(QLabel)))
w4.close()

print("\n-- 10b. comando longo nao trava a janela e Parar encerra --")
W.confirmar_comandos = lambda cmds, cwd, parent=None: list(cmds)
w.chk_agente.set_state(True)
w.controller = FakeController([
    f'{F}bash\n# kitty: acao=rodar\n"{sys.executable}" -c "import time; time.sleep(60)"\n{F}',
    f"{F}\n# kitty: acao=fim\n{F}",
])
batidas = []
status_visto = []
relogio = QTimer()
relogio.timeout.connect(lambda: batidas.append(1))
relogio.start(100)
inicio = time.monotonic()
w.input.setPlainText("rode o comando longo")
w._send()
QTimer.singleShot(2200, lambda: status_visto.append(w.lbl_status.text()))
QTimer.singleShot(2500, w._parar_agente)
roda_ate_fim(w, app, timeout_ms=40000)
relogio.stop()
duracao = time.monotonic() - inicio
checa("janela segue viva durante o comando", len(batidas) >= 15, len(batidas))
checa("Parar encerra o comando de 60 s", duracao < 20, round(duracao, 1))
checa("chat avisa que o comando foi interrompido",
      any("interrompido por você" in label.text()
          for label in w.chat._holder.findChildren(QLabel)))
checa("status mostra há quanto tempo o comando roda",
      status_visto and "Rodando há" in status_visto[0]
      and "Parar encerra" in status_visto[0], status_visto)

print("\n-- 10c. processo em segundo plano (servidor do adb) nao trava o agente --")
w.controller = FakeController([
    f'{F}bash\n# kitty: acao=rodar\nstart "" /b "{sys.executable}" -c "import time; time.sleep(60)" & echo servidor-no-fundo\n{F}',
    f"{F}\n# kitty: acao=fim\n{F}",
])
inicio = time.monotonic()
w.input.setPlainText("suba o servidor")
w._send()
roda_ate_fim(w, app, timeout_ms=40000)
duracao = time.monotonic() - inicio
checa("agente segue sem esperar o processo de fundo", duracao < 15, round(duracao, 1))
checa("saída do comando voltou ao modelo",
      len(w.controller.enviadas) == 2 and "servidor-no-fundo" in w.controller.enviadas[1],
      w.controller.enviadas[-1][-200:] if w.controller.enviadas else None)

print("\n-- 11. fechar com agente rodando nao trava --")
w3 = MainWindow(); w3._set_project(str(base)); w3.chk_agente.set_state(True)
w3.controller = FakeController([f"{F}\n# kitty: acao=ler file=src/app.py\n{F}"] * 30)
w3.input.setPlainText("loop"); w3._send()
checa("rodando", w3._agente is not None)
w3.close()
app.processEvents()
checa("fechou sem travar", w3._agente is None)

w.close()
shutil.rmtree(base, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
