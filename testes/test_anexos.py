"""Colar com Ctrl+V: imagem vira upload, texto vira inline, chip aparece e sai."""
import os
import shutil
import sys
import threading
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# config descartavel: teste nao mexe na ultima pasta do usuario
os.environ["DEEPSEEK_UI_CONFIG"] = os.path.join(
    tempfile.gettempdir(), "deepseek_ui_teste_workspace.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtCore import QEventLoop, QMimeData, QTimer, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QToolButton,
)

from src import anexos
from src.attachment_view import AttachmentPreviewDialog
from src.controller import Controller
from src.theme import stylesheet
from src.window import ChipAnexo, MainWindow

# Teste não interativo: autoriza explicitamente o mapa que acompanha o pedido.
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

ok = fail = 0
def checa(n, c, e=""):
    global ok, fail
    if c: print(f"  ok      {n}"); ok += 1
    else: print(f"  FALHOU  {n} -> {e}"); fail += 1

base = Path(tempfile.mkdtemp(prefix="anx_"))
(base / "src").mkdir()
(base / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
(base / "foto.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
(base / "grande.py").write_text("y = 2\n" * 40000, encoding="utf-8")  # > 100 KB

app = QApplication(sys.argv)
app.setStyleSheet(stylesheet())
w = MainWindow()
w.show()
w._set_project(str(base))

print("-- 1. classificacao: texto inline, binario upload --")
a = anexos.de_arquivo(base / "src" / "app.py", base)
checa("py vira inline", a and a.modo == "inline", a.modo if a else None)
checa("rotulo relativo a raiz", a and a.rotulo == "src/app.py", a.rotulo if a else None)
checa("conteudo lido", a and a.conteudo == "x = 1\n", repr(a.conteudo) if a else None)

a = anexos.de_arquivo(base / "foto.png", base)
checa("png vira upload", a and a.modo == "upload", a.modo if a else None)
checa("upload guarda caminho", a and a.caminho and Path(a.caminho).is_file())

a = anexos.de_arquivo(base / "grande.py", base)
checa("texto grande vira upload", a and a.modo == "upload", a.modo if a else None)

checa("pasta nao vira anexo", anexos.de_arquivo(base / "src", base) is None)
checa("inexistente nao vira anexo", anexos.de_arquivo(base / "nada.txt", base) is None)

print("\n-- 2. imagem da area de transferencia --")
img = QImage(120, 80, QImage.Format.Format_RGB32)
img.fill(0x884422)
a = anexos.de_imagem(img)
checa("imagem vira upload", a and a.modo == "upload", a.modo if a else None)
checa("PNG gravado", a and Path(a.caminho).is_file())
checa("rotulo com as medidas", a and "120×80" in a.rotulo, a.rotulo if a else None)
checa("marcado como temporario", a and a.temporario)
temp = a.caminho
a.descartar()
checa("descartar apaga o temporario", not Path(temp).exists())
checa("imagem nula e ignorada", anexos.de_imagem(QImage()) is None)

print("\n-- 3. colar imagem no campo cria chip --")
mime = QMimeData(); mime.setImageData(img)
checa("Qt aceita colar imagem", w.input.canInsertFromMimeData(mime))
w.input.insertFromMimeData(mime)
app.processEvents()
chips = w.barra_anexos.findChildren(ChipAnexo)
checa("1 chip", len(chips) == 1, len(chips))
checa("barra visivel", w.barra_anexos.isVisible())
checa("campo de texto continua vazio", w.input.toPlainText() == "", repr(w.input.toPlainText()))
checa("chip marcado como upload", w._anexos[0].modo == "upload", w._anexos[0].modo)
preview_dialog = AttachmentPreviewDialog(w._anexos[0], w)
checa("prévia da imagem mostra conteúdo visual",
      any(label.pixmap() is not None
          for label in preview_dialog.findChildren(QLabel)))
preview_dialog.close()
abertos = []
chip_preview = ChipAnexo(w._anexos[0], lambda _: None, abertos.append)
chip_preview.findChildren(QToolButton)[0].click()
checa("clique no rótulo do chip abre prévia", abertos == [w._anexos[0]])
chip_preview.close()
anexo_texto_grande = anexos.de_arquivo(base / "grande.py", base)
dialogo_texto = AttachmentPreviewDialog(anexo_texto_grande, w)
editores = dialogo_texto.findChildren(QPlainTextEdit)
checa("prévia de arquivo de texto grande mostra conteúdo",
      bool(editores) and "y = 2" in editores[0].toPlainText())
checa("prévia de texto é somente leitura e permite fechar",
      editores and editores[0].isReadOnly()
      and bool(dialogo_texto.findChildren(QDialogButtonBox)))
dialogo_texto.close()

print("\n-- 4. colar arquivo do Explorer --")
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(str(base / "src" / "app.py"))])
checa("Qt aceita colar arquivo", w.input.canInsertFromMimeData(mime))
w.input.insertFromMimeData(mime)
app.processEvents()
checa("2 chips", len(w.barra_anexos.findChildren(ChipAnexo)) == 2,
      len(w.barra_anexos.findChildren(ChipAnexo)))
checa("2o e inline", w._anexos[1].modo == "inline", w._anexos[1].modo)

print("\n-- 5. colar texto normal ainda escreve no campo --")
mime = QMimeData(); mime.setText("ola mundo")
w.input.insertFromMimeData(mime)
checa("texto foi para o campo", w.input.toPlainText() == "ola mundo",
      repr(w.input.toPlainText()))
checa("nenhum chip novo", len(w._anexos) == 2, len(w._anexos))

print("\n-- 6. remover chip pelo X --")
chips = w.barra_anexos.findChildren(ChipAnexo)
w._remover_anexo(chips[0])
app.processEvents()
checa("sobrou 1 anexo", len(w._anexos) == 1, len(w._anexos))
checa("sobrou 1 chip", len(w.barra_anexos.findChildren(ChipAnexo)) == 1,
      len(w.barra_anexos.findChildren(ChipAnexo)))
w._remover_anexo(w.barra_anexos.findChildren(ChipAnexo)[0])
app.processEvents()
checa("barra some quando esvazia", not w.barra_anexos.isVisible())

print("\n-- 7. separar manda cada um pelo caminho certo --")
img2 = QImage(10, 10, QImage.Format.Format_RGB32); img2.fill(0)
w._colar_imagem(img2)
w._colar_arquivos([str(base / "src" / "app.py")])
inline, upload = anexos.separar(w._anexos)
checa("1 inline", len(inline) == 1, inline)
checa("1 upload", len(upload) == 1, upload)
checa("inline leva caminho e conteudo", inline[0][0] == "src/app.py" and "x = 1" in inline[0][1],
      inline)

print("\n-- 8. envio: upload vai para o controller, temporario sobrevive ate o fim --")
enviados = []
class FakeCtrl:
    is_connected = True
    def current_url(self): return None
    def send_message(self, texto, on_update=None, arquivos=None, on_sent=None):
        enviados.append((texto, list(arquivos or [])))
        checa("temporario ainda existe na hora do upload",
              all(Path(a).is_file() for a in (arquivos or [])), arquivos)
        if on_sent:
            on_sent()
        return "ok"
w.controller = FakeCtrl()
w.chk_agente.set_state(False)
temporario = [a.caminho for a in w._anexos if a.temporario][0]
w.input.setPlainText("olha essa imagem")
w._send()
app.processEvents()
w._agente = None
checa("mandou 1 vez", len(enviados) == 1, len(enviados))
if enviados:
    texto, arqs = enviados[0]
    checa("upload repassado", len(arqs) == 1, arqs)
    checa("inline entrou no texto", "Arquivo `src/app.py`" in texto, texto[:200])
    checa("pedido em primeiro", texto.startswith("olha essa imagem"), texto[:40])
checa("chips limpos apos enviar", w._anexos == [] and not w.barra_anexos.isVisible())

w._on_response("resposta qualquer")
app.processEvents()
checa("temporario apagado depois da resposta", not Path(temporario).exists(), temporario)

print("\n-- 9. modo Agente encaminha upload na primeira rodada --")
enviados_agente = []
evento_upload = threading.Event()
liberar_resposta = threading.Event()
class FakeCtrlAgente:
    is_connected = True
    def current_url(self): return None
    def send_message(self, texto, on_update=None, arquivos=None, on_sent=None):
        evento_upload.set()
        liberar_resposta.wait(2)
        enviados_agente.append((texto, list(arquivos or [])))
        checa("imagem existe durante upload do Agente",
              all(Path(a).is_file() for a in (arquivos or [])), arquivos)
        if on_sent:
            on_sent()
        return "Terminei.\n\n# kitty: acao=fim"

w.controller = FakeCtrlAgente()
w.chk_agente.set_state(True)
w._colar_imagem(img)
temporario_agente = w._anexos[0].caminho
w.input.setPlainText("Analise esta imagem")
w._send()
checa("Agente iniciou o envio", evento_upload.wait(2))
loop = QEventLoop()
w._agente.fim_sig.connect(loop.quit)
liberar_resposta.set()
QTimer.singleShot(5000, loop.quit)
loop.exec()
app.processEvents()
checa("Agente enviou a imagem uma vez",
      len(enviados_agente) == 1 and len(enviados_agente[0][1]) == 1,
      enviados_agente)
checa("imagem temporária removida após o Agente",
      not Path(temporario_agente).exists(), temporario_agente)
checa("Agente terminou", w._agente is None, w._agente)

print("\n-- 10. falha de upload cancela envio da mensagem --")
class FakeWrapper:
    enviada = False
    def anexar(self, caminho): return False
    def send_message(self, *args, **kwargs):
        self.enviada = True

controller = Controller.__new__(Controller)
controller.is_connected = True
controller.wrapper = FakeWrapper()
controller.gui = None
try:
    controller.send_message("pedido", arquivos=[temporario_agente])
    falha_upload = False
except RuntimeError as error:
    falha_upload = "não foi enviada" in str(error)
checa("erro de upload explícito", falha_upload)
checa("mensagem não enviada sem o anexo", not controller.wrapper.enviada)

w.close()
shutil.rmtree(base, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
