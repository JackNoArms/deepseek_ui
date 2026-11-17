"""Fase 2 pela UI: resposta chega -> card aparece -> aplicar grava no disco."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# config descartavel: teste nao mexe na ultima pasta do usuario
os.environ["DEEPSEEK_UI_CONFIG"] = os.path.join(
    tempfile.gettempdir(), "deepseek_ui_teste_workspace.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtWidgets import QApplication
from src.chat import ActionCard
from src.diff_view import DiffDialog, diff_html
from src.executor import Executor
from src.parser import parse
from src.theme import stylesheet
from src.window import MainWindow

ok = fail = 0
F = "```"

def checa(nome, cond, extra=""):
    global ok, fail
    if cond:
        print(f"  ok      {nome}"); ok += 1
    else:
        print(f"  FALHOU  {nome} -> {extra}"); fail += 1

base = Path(tempfile.mkdtemp(prefix="ui2_"))
(base / "src").mkdir()
(base / "src" / "app.py").write_text("valor = 1\n", encoding="utf-8")

app = QApplication(sys.argv)
app.setStyleSheet(stylesheet())
w = MainWindow()
w.show()
w._set_project(str(base))
checa("projeto aberto", w.project is not None and w.project.root == base.resolve(),
      w.project.root if w.project else None)

RESPOSTA = f"""Fiz as duas coisas que voce pediu.

{F}python
# kitty: file=src/app.py acao=modificar
valor = 42
{F}

{F}python
# kitty: file=src/extra.py acao=criar
def novo():
    return "oi"
{F}
"""

print("-- 1. resposta vira card, sem gravar nada --")
antes_app = (base / "src" / "app.py").read_text(encoding="utf-8")
w.chat.start_agent()
w._on_response(RESPOSTA)
app.processEvents()

cards = w.chat._holder.findChildren(ActionCard)
checa("1 ActionCard no chat", len(cards) == 1, len(cards))
card = cards[0] if cards else None
checa("2 planos", card and len(card.planos) == 2, len(card.planos) if card else None)
checa("NADA gravado antes de aplicar",
      (base / "src" / "app.py").read_text(encoding="utf-8") == antes_app
      and not (base / "src" / "extra.py").exists())
checa("botao habilitado", card and card.btn.isEnabled())

print("\n-- 2. diff montado certo --")
p_mod = [p for p in card.planos if p.rel == "src/app.py"][0]
checa("diff -valor = 1", "-valor = 1" in p_mod.diff, repr(p_mod.diff))
checa("diff +valor = 42", "+valor = 42" in p_mod.diff, repr(p_mod.diff))
checa("html do diff colore adicao", "#6FE0A8" in diff_html(p_mod.diff))

print("\n-- 3. dialogo de revisao --")
dlg = DiffDialog(card.planos)
checa("2 itens na lista", dlg.lista.count() == 2, dlg.lista.count())
checa("todos marcados por padrao", len(dlg.marcados()) == 2, len(dlg.marcados()))
from PyQt6.QtCore import Qt
dlg.lista.item(0).setCheckState(Qt.CheckState.Unchecked)
checa("desmarcar reduz a selecao", len(dlg.marcados()) == 1, len(dlg.marcados()))
dlg.lista.setCurrentRow(1); app.processEvents()
checa("troca de item nao quebra", True)
dlg.close()

print("\n-- 3b. risco de truncamento continua sob decisão do usuário --")
(base / "grande.py").write_text("linha original\n" * 80, encoding="utf-8")
resposta_curta = (
    f"{F}text\n# kitty: file=grande.py acao=modificar\n{F}")
plano_risco = Executor(w.project).preparar(parse(resposta_curta).acoes)[0]
dlg_risco = DiffDialog([plano_risco])
item_risco = dlg_risco.lista.item(0)
checa("risco começa desmarcado", item_risco.checkState() == Qt.CheckState.Unchecked)
checa("risco ainda pode ser marcado",
      bool(item_risco.flags() & Qt.ItemFlag.ItemIsUserCheckable))
checa("aplicar habilita depois da escolha explícita",
      not dlg_risco.btn_aplicar.isEnabled())
item_risco.setCheckState(Qt.CheckState.Checked)
app.processEvents()
checa("botão habilita após marcar o risco",
      dlg_risco.btn_aplicar.isEnabled()
      and dlg_risco.marcados() == [plano_risco])
resultado_risco = Executor(w.project).aplicar(dlg_risco.marcados())
checa("arquivo zerado marcado foi aplicado",
      resultado_risco[0].status == "aplicado"
      and (base / "grande.py").read_text(encoding="utf-8") == "")
backup_risco = list((base / ".deepseek_ui" / "backups").rglob("grande.py"))
checa("backup preservou arquivo longo original",
      backup_risco
      and backup_risco[0].read_text(encoding="utf-8")
      == "linha original\n" * 80)
dlg_risco.close()

print("\n-- 4. aplicar de verdade --")
resultados = Executor(w.project).aplicar(card.planos)
checa("2 aplicados", all(r.status == "aplicado" for r in resultados),
      [r.status for r in resultados])
checa("app.py atualizado",
      (base / "src" / "app.py").read_text(encoding="utf-8") == "valor = 42",
      repr((base / "src" / "app.py").read_text(encoding="utf-8")))
checa("extra.py criado",
      (base / "src" / "extra.py").read_text(encoding="utf-8") == 'def novo():\n    return "oi"',
      repr((base / "src" / "extra.py").read_text(encoding="utf-8")))
bkp = list((base / ".deepseek_ui" / "backups").rglob("app.py"))
checa("backup guardou o original", bkp and bkp[0].read_text(encoding="utf-8") == "valor = 1\n",
      [str(b) for b in bkp])
card.selar("✓ 2 aplicada(s)")
checa("card selado", not card.btn.isEnabled() and "2" in card.btn.text(), card.btn.text())

print("\n-- 5. resposta sem pasta aberta avisa --")
w2 = MainWindow(); w2.project = None
w2.chat.start_agent(); w2._on_response(RESPOSTA)
app.processEvents()
notas = [c for c in w2.chat._holder.findChildren(type(w2.chat.add_system("x")))]
checa("nenhum card sem projeto", not w2.chat._holder.findChildren(ActionCard))
w2.close()

print("\n-- 6. codigo sem alvo cai no modo degradado --")
w._on_response(f"Exemplo:\n\n{F}python\nprint(1)\n{F}")
app.processEvents()
checa("nenhum card novo", len(w.chat._holder.findChildren(ActionCard)) == 1,
      len(w.chat._holder.findChildren(ActionCard)))

print("\n-- 7. caminho fora da raiz nao vira botao ativo --")
w._on_response(f"{F}python\n# kitty: file=../invasor.py acao=criar\nx\n{F}")
app.processEvents()
cards = w.chat._holder.findChildren(ActionCard)
ultimo = cards[-1]
checa("card mostra recusa", all(p.erro for p in ultimo.planos), [p.erro for p in ultimo.planos])
checa("botao desabilitado", not ultimo.btn.isEnabled())
checa("nada criado fora", not (base.parent / "invasor.py").exists())

w.close()
shutil.rmtree(base, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
