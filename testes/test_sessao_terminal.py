"""Sessão por projeto (retomar a conversa) e terminal embutido de verdade."""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# config descartavel: teste nao mexe na ultima pasta do usuario
os.environ["DEEPSEEK_UI_CONFIG"] = os.path.join(
    tempfile.gettempdir(), "deepseek_ui_teste_workspace.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtWidgets import QApplication

from src.project import Project, _ler_config, auto_conectar, salvar_raiz
from src.session import ProjectSession, e_conversa
from src.theme import stylesheet
from src.window import MainWindow
from src.wrapper import DeepSeekWrapper
from selenium.webdriver.common.keys import Keys

ok = fail = 0
def checa(n, c, e=""):
    global ok, fail
    if c: print(f"  ok      {n}"); ok += 1
    else: print(f"  FALHOU  {n} -> {e}"); fail += 1

URL = "https://chat.deepseek.com/a/chat/s/3f2a9c10-1b4d-4e77-9c3a-5d6e7f801122"
URL2 = "https://chat.deepseek.com/a/chat/s/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

base = Path(tempfile.mkdtemp(prefix="ses_"))
(base / "src").mkdir()
(base / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
outro = Path(tempfile.mkdtemp(prefix="ses2_"))

print("-- 1. so URL de conversa e aceita --")
checa("conversa vale", e_conversa(URL))
checa("home nao vale", not e_conversa("https://chat.deepseek.com/"))
checa("outro site nao vale", not e_conversa("https://chatgpt.com/a/chat/s/123"))
checa("vazio nao vale", not e_conversa(""))

print("\n-- 1b. nova conversa envia Ctrl+J para a pagina --")
class FakeBrowser:
    current_url = URL

class FakeActions:
    chamadas = []
    def __init__(self, driver): self.driver = driver
    def key_down(self, tecla):
        self.chamadas.append(("down", tecla))
        return self
    def send_keys(self, tecla):
        self.chamadas.append(("key", tecla))
        return self
    def key_up(self, tecla):
        self.chamadas.append(("up", tecla))
        return self
    def perform(self):
        self.driver.current_url = URL2

wrapper = DeepSeekWrapper()
wrapper.driver = FakeBrowser()
wrapper.is_connected = True
FakeActions.chamadas = []
with patch("src.wrapper.ActionChains", FakeActions):
    nova_conversa = wrapper.new_chat()
checa("atalho pressionado na ordem correta",
      FakeActions.chamadas == [
          ("down", Keys.CONTROL), ("key", "j"), ("up", Keys.CONTROL)],
      FakeActions.chamadas)
checa("confirma nova URL após Ctrl+J", nova_conversa
      and wrapper.driver.current_url == URL2, wrapper.driver.current_url)

print("\n-- 2. grava e le --")
ses = ProjectSession(base)
checa("comeca vazio", ses.url() is None, ses.url())
ses.salvar_url(URL)
checa("guardou", ses.url() == URL, ses.url())
checa("arquivo no lugar certo", (base / ".deepseek_ui" / "session.json").is_file())
ses.salvar_url("https://chat.deepseek.com/")
checa("home nao sobrescreve", ses.url() == URL, ses.url())

print("\n-- 3. marca se as regras ja foram --")
checa("regras marcadas no save", ses.regras_enviadas())
ses2 = ProjectSession(base)
checa("persiste entre instancias", ses2.url() == URL and ses2.regras_enviadas())
ses.salvar_url(URL2, regras_enviadas=False)
checa("troca de conversa reseta as regras", not ProjectSession(base).regras_enviadas())

print("\n-- 4. esquecer desgruda --")
ses.esquecer()
checa("sem url", ProjectSession(base).url() is None)
checa("sem regras", not ProjectSession(base).regras_enviadas())

print("\n-- 5. cada projeto tem a sua --")
ProjectSession(base).salvar_url(URL)
ProjectSession(outro).salvar_url(URL2)
checa("projeto A", ProjectSession(base).url() == URL)
checa("projeto B", ProjectSession(outro).url() == URL2)

print("\n-- 6. config mescla em vez de sobrescrever --")
salvar_raiz(str(base))
antes = dict(_ler_config())
checa("raiz gravada", antes.get("root") == str(base))
checa("auto_conectar liga por padrao", auto_conectar())

print("\n-- 7. a janela grava a URL depois de responder --")
app = QApplication(sys.argv)
app.setStyleSheet(stylesheet())
ProjectSession(base).esquecer()

class FakeCtrl:
    is_connected = True
    def __init__(self, url): self._url = url
    def current_url(self): return self._url
    def send_message(self, *a, **k): return "ok"
    def new_chat(self): return False

w = MainWindow()
w.show()
w._set_project(str(base))
w.controller = FakeCtrl(URL)
w._on_response("resposta qualquer")
app.processEvents()
checa("URL gravada apos a resposta", ProjectSession(base).url() == URL,
      ProjectSession(base).url())

w.controller = FakeCtrl("https://chat.deepseek.com/")
ProjectSession(base).esquecer()
w._on_response("outra")
checa("home nao e gravada", ProjectSession(base).url() is None)

print("\n-- 8. retomar carrega o historico e poupa as regras --")
ProjectSession(base).salvar_url(URL, regras_enviadas=True)
abertas = []
class CtrlRetoma(FakeCtrl):
    def open_conversation(self, url): abertas.append(url); return True
    def extract_history(self): return [{"role": "user", "content": "oi"},
                                       {"role": "assistant", "content": "ola"}]
w.controller = CtrlRetoma(URL)
w._precisa_regras = True
w._retomar_conversa()
for _ in range(40):
    app.processEvents(); time.sleep(0.02)
checa("abriu a conversa salva", abertas == [URL], abertas)
checa("nao reenvia as regras", w._precisa_regras is False, w._precisa_regras)

ProjectSession(base).salvar_url(URL2, regras_enviadas=False)
w.controller = CtrlRetoma(URL2)
w._retomar_conversa()
for _ in range(40):
    app.processEvents(); time.sleep(0.02)
checa("conversa sem regras pede as regras", w._precisa_regras is True, w._precisa_regras)

print("\n-- 8b. nova conversa só limpa histórico após sucesso --")
ProjectSession(base).salvar_url(URL)
w.controller = FakeCtrl(URL)
w.chat.add_user("histórico preservado se falhar")
w._new_chat()
for _ in range(80):
    app.processEvents()
    if not w._workers:
        break
    time.sleep(0.02)
checa("falha preserva conversa vinculada",
      ProjectSession(base).url() == URL and w.chat._lay.count() > 1)

class CtrlNova(FakeCtrl):
    def new_chat(self): return True
w.controller = CtrlNova(URL)
w._new_chat()
for _ in range(80):
    app.processEvents()
    if not w._workers:
        break
    time.sleep(0.02)
checa("sucesso limpa conversa vinculada",
      ProjectSession(base).url() is None and w.chat._lay.count() == 1)

print("\n-- 9. terminal roda comando de verdade --")
w._mostrar_terminal(True)
checa("terminal visivel", w.terminal.isVisible())
checa("cwd = projeto", w.terminal.cwd == str(base.resolve()), w.terminal.cwd)
for _ in range(60):
    app.processEvents(); time.sleep(0.02)
checa("shell subiu", w.terminal._vivo())

w.terminal.entrada.setText("echo ping-do-teste")
w.terminal._enviar()
saida = ""
for _ in range(150):
    app.processEvents(); time.sleep(0.02)
    saida = w.terminal.saida.toPlainText()
    if "ping-do-teste" in saida:
        break
checa("saida do comando apareceu", "ping-do-teste" in saida, repr(saida[-200:]))
checa("comando entrou no historico", "echo ping-do-teste" in w.terminal._historico,
      w.terminal._historico)
checa("campo limpo apos enviar", w.terminal.entrada.text() == "")

print("\n-- 10. cd persiste (shell e o mesmo) --")
w.terminal.entrada.setText("cd src")
w.terminal._enviar()
for _ in range(50):
    app.processEvents(); time.sleep(0.02)
w.terminal.entrada.setText("echo marcador-apos-cd")
w.terminal._enviar()
saida = ""
for _ in range(150):
    app.processEvents(); time.sleep(0.02)
    saida = w.terminal.saida.toPlainText()
    if "marcador-apos-cd" in saida:
        break
checa("shell e persistente", "marcador-apos-cd" in saida, repr(saida[-200:]))

print("\n-- 11. historico com as setas --")
w.terminal._andar_hist(-1)
checa("seta para cima traz o ultimo", w.terminal.entrada.text() == "echo marcador-apos-cd",
      w.terminal.entrada.text())

print("\n-- 12. esconder e fechar --")
w._mostrar_terminal(False)
checa("escondeu", not w.terminal.isVisible())
checa("botao desmarcado", not w.btn_terminal.isChecked())
w.terminal.parar()
checa("shell parado", not w.terminal._vivo())

w.close()
shutil.rmtree(base, ignore_errors=True)
shutil.rmtree(outro, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
