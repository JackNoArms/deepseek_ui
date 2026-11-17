"""Testa configuração visual e integração das políticas com a UI/agente.

Rodar como script: `python testes/test_access_profiles.py`.
Quando importado pelo pytest, nada é executado — sem isso o `sys.exit` do
final derrubava o coletor.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DEEPSEEK_UI_CONFIG"] = str(
    Path(tempfile.gettempdir()) / "deepseek_ui_access_profiles_test.json")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel

from src.parser import Acao
from src.executor import Executor
from src.permission_view import PermissionDialog
from src.permissions import PermissionPolicy
from src.project import Project
from src.session import ProjectSession
from src.theme import stylesheet
from src.window import MainWindow

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


def main():
    with tempfile.TemporaryDirectory(prefix="access_profiles_") as temp:
        base = Path(temp)
        projeto = base / "projeto"
        externa = base / "externa"
        projeto.mkdir()
        externa.mkdir()
        app = QApplication.instance() or QApplication(sys.argv)
        app.setStyleSheet(stylesheet())

        print("-- 1. diálogo de permissões --")
        policy = PermissionPolicy(projeto)
        dialogo = PermissionDialog(Project(projeto, policy))
        checa("mostra os cinco perfis",
              {dialogo.mode.itemData(i) for i in range(dialogo.mode.count())}
              == {"project_confirm", "project_auto", "folders",
                  "computer_confirm", "computer_auto"})
        checa("projeto começa com leitura e sem grants de escrita",
              dialogo.settings()["grants"][0]["read"]
              and not dialogo.settings()["grants"][0]["create"])
        checa("consentimento de leitura começa ligado",
              dialogo.confirm_reads.isChecked()
              and dialogo.settings()["confirm_reads"])
        checa("caixas de pasta configuráveis mesmo fora do perfil Pastas",
              dialogo.tabela.isEnabled()
              and "só autorizam operações" in dialogo.grants_info.text())
        dialogo.show()
        app.processEvents()
        celula_criar = dialogo.tabela.cellWidget(0, 2)
        caixa_criar = celula_criar.findChild(QCheckBox)
        estado_anterior = caixa_criar.isChecked()
        QTest.mouseClick(
            caixa_criar, Qt.MouseButton.LeftButton, pos=caixa_criar.rect().center())
        checa("clique na caixa de operação altera o estado",
              caixa_criar.isChecked() != estado_anterior)
        dialogo.mode.setCurrentIndex(dialogo.mode.findData("project_auto"))
        checa("perfil projeto automático informa escopo e mantém comando protegido",
              "vault vinculado" in dialogo.aviso.text()
              and "comandos ainda exigem confirmação" in dialogo.aviso.text()
              and not dialogo.confirm_reads.isEnabled()
              and not dialogo.confirm_reads.isChecked())
        dialogo.mode.setCurrentIndex(dialogo.mode.findData("project_confirm"))
        checa("preferência de leitura sobrevive a troca de perfil",
              dialogo.confirm_reads.isEnabled()
              and dialogo.confirm_reads.isChecked())
        dialogo.confirm_reads.setChecked(False)
        checa("salva opção para não perguntar leituras",
              not dialogo.settings()["confirm_reads"])
        dialogo.mode.setCurrentIndex(dialogo.mode.findData("folders"))
        checa("perfil Pastas mostra instrução de permissão ativa",
              "sem confirmação adicional" in dialogo.grants_info.text()
              and "Para notas novas, marque Criar" in dialogo.grants_info.text()
              and "Qualquer comando" in dialogo.aviso.text()
              and "sem confirmação" in dialogo.aviso.text())
        caixa_criar.setChecked(True)
        dialogo._adicionar_regra({
            "path": str(externa.resolve()), "read": True, "create": False,
            "edit": True, "delete": False,
        })
        settings = dialogo.settings()
        checa("salva grants e modo por pasta",
              settings["mode"] == "folders" and settings["grants"][0]["create"]
              and settings["grants"][1]["edit"])
        dialogo.close()

        print("\n-- 2. carregar política salva no projeto --")
        sessao = ProjectSession(projeto)
        sessao.salvar_permissoes({
            "mode": "folders",
            "grants": [{
                "path": str(projeto.resolve()), "read": True, "create": False,
                "edit": False, "delete": False,
            }],
        })
        janela = MainWindow()
        janela._set_project(str(projeto), avisar=False)
        checa("janela restaura modo e grants",
              janela.project.permissions.mode == "folders"
              and not janela.project.permissions.grants[0]["create"])
        checa("resumo visível informa confirmação de leitura",
              "confirma leitura/envio" in janela.lbl_access_summary.text())

        print("\n-- 3. grant controla operações no executor --")
        (projeto / "app.py").write_text("antes", encoding="utf-8")
        resposta = ("```python\n# kitty: file=app.py acao=modificar\n"
                    "depois\n```")
        janela._processar_acoes(resposta)
        checa("modo por pasta nega escrita desmarcada",
              (projeto / "app.py").read_text(encoding="utf-8") == "antes")

        print("\n-- 3b. grants de vault aplicam sem confirmação extra --")
        pasta_notas = projeto / "vault" / "Notas"
        pasta_notas.mkdir(parents=True, exist_ok=True)
        janela.project = Project(projeto, PermissionPolicy(projeto, "folders", [
            {"path": str(pasta_notas.resolve()), "read": True, "create": True,
             "edit": True, "delete": False},
        ]))
        janela._processar_acoes(
            "```text\n# kitty: file=vault/Notas/decisao.md acao=criar\n# Decisão\n```")
        nota_grant = pasta_notas / "decisao.md"
        checa("cria nota no vault com grant de Criar sem revisão extra",
              nota_grant.is_file()
              and nota_grant.read_text(encoding="utf-8") == "# Decisão"
              and not janela.project.permissions.requires_file_confirmation)

        janela.project = Project(projeto, PermissionPolicy(projeto, "folders", [
            {"path": str(pasta_notas.resolve()), "read": True, "create": False,
             "edit": True, "delete": False},
        ]))
        janela._processar_acoes(
            "```text\n# kitty: file=vault/Notas/sem-grant.md acao=criar\n# Nota\n```")
        checa("grant de Editar sozinho não autoriza criar nota",
              not (pasta_notas / "sem-grant.md").exists())
        checa("negação de permissão aparece no chat",
              any("não permitido nesta pasta" in label.text()
                  for label in janela.chat._holder.findChildren(QLabel)))

        print("\n-- 4. modo automático aplica com backup --")
        janela.project = Project(
            projeto, PermissionPolicy(projeto, "computer_auto"))
        janela._processar_acoes(resposta)
        checa("auto aplicou alteração",
              (projeto / "app.py").read_text(encoding="utf-8") == "depois")
        checa("auto preservou backup",
              any((projeto / ".deepseek_ui" / "backups").rglob("app.py")))
        original_grande = "linha\n" * 80
        (projeto / "grande.py").write_text(original_grande, encoding="utf-8")
        janela._processar_acoes(
            "```python\n# kitty: file=grande.py acao=modificar\nx\n```")
        # Nova regra: em perfil automático a política já autorizou escrita.
        # O aviso de truncamento é informativo, não veto — o app aplica mesmo
        # assim, avisa no chat e o backup cobre a reversão. O parser do
        # protocolo remove trailing whitespace, então o arquivo fica "x".
        checa("modo automático aplica provável truncamento com backup e aviso",
              (projeto / "grande.py").read_text(encoding="utf-8") == "x"
              and any((projeto / ".deepseek_ui" / "backups").rglob("grande.py"))
              and any("truncamento" in label.text().lower()
                      for label in janela.chat._holder.findChildren(QLabel)))
        plano_externo = Executor(janela.project).preparar([
            Acao("criar", str(externa / "novo.txt"), "novo")])
        resultado_externo = Executor(janela.project).aplicar(plano_externo)
        checa("modo amplo automático escreve fora do projeto",
              resultado_externo[0].status == "aplicado"
              and (externa / "novo.txt").read_text(encoding="utf-8") == "novo")

        print("\n-- 4b. modo automático limitado ao projeto e vault --")
        (projeto / "criado.txt").write_text("criado", encoding="utf-8")
        nota_vault = projeto / "vault" / "Notas" / "automatico.md"
        nota_vault.parent.mkdir(parents=True, exist_ok=True)
        nota_vault.write_text("# antes\n", encoding="utf-8")
        janela.project = Project(projeto, PermissionPolicy(projeto, "project_auto"))
        checa("perfil do projeto automatiza leituras sem abrir escopo externo",
              not janela.project.permissions.requires_read_confirmation
              and janela.project.permissions.requires_command_confirmation)
        resposta_editar = (
            "```text\n# kitty: file=criado.txt acao=modificar\n"
            "editado\n```\n"
            "```text\n# kitty: file=vault/Notas/automatico.md acao=modificar\n"
            "# atualizado\n```")
        janela._processar_acoes(resposta_editar)
        checa("projeto e vault atualizados sem confirmação manual",
              (projeto / "criado.txt").read_text(encoding="utf-8") == "editado"
              and nota_vault.read_text(encoding="utf-8") == "# atualizado")
        checa("edições automáticas mantêm backups",
              any((projeto / ".deepseek_ui" / "backups").rglob("criado.txt"))
              and any((projeto / ".deepseek_ui" / "backups").rglob("automatico.md")))
        janela._processar_acoes(
            "```text\n# kitty: file=novo.txt acao=criar\nnovo\n```\n"
            "```text\n# kitty: file=vault/Notas/novo.md acao=criar\n# nota\n```")
        novo_vault = projeto / "vault" / "Notas" / "novo.md"
        checa("criação automática funciona no projeto e no vault",
              (projeto / "novo.txt").read_text(encoding="utf-8") == "novo"
              and novo_vault.read_text(encoding="utf-8") == "# nota")
        janela._processar_acoes(
            "```text\n# kitty: file=criado.txt acao=apagar\n```\n"
            "```text\n# kitty: file=vault/Notas/novo.md acao=apagar\n```")
        checa("exclusões automáticas também preservam backup",
              not (projeto / "criado.txt").exists()
              and not novo_vault.exists()
              and any((projeto / ".deepseek_ui" / "backups").rglob("criado.txt"))
              and any((projeto / ".deepseek_ui" / "backups").rglob("novo.md")))

        print("\n-- 5. modos automáticos rodam qualquer comando sem confirmar --")
        janela.project = Project(projeto, PermissionPolicy(projeto, "computer_auto"))

        class FakeAgent:
            def __init__(self):
                self.retorno = None

            def responder(self, valor):
                self.retorno = valor

        fake = FakeAgent()
        janela._agente = fake
        janela._agente_pedir_comando([
            Acao("rodar", conteudo="python -c \"print('comando-permitido')\""),
            Acao("rodar", conteudo="hostname"),
        ])
        checa("comando permitido executou", "comando-permitido" in fake.retorno)
        checa("comando fora da antiga allowlist também roda",
              "comando recusado" not in fake.retorno
              and "$ hostname\n(saiu com 0)" in fake.retorno, fake.retorno)

        janela.project = Project(projeto, PermissionPolicy(projeto, "folders", [
            {"path": str(projeto.resolve()), "read": True, "create": True,
             "edit": True, "delete": True},
        ]))
        fake = FakeAgent()
        janela._agente = fake
        with patch("src.window.confirmar_comandos",
                   side_effect=AssertionError("não deveria pedir confirmação")):
            janela._agente_pedir_comando([
                Acao("rodar", conteudo="python -c \"print('pastas-sem-prompt')\""),
            ])
        checa("Pastas escolhidas executa comando permitido sem confirmação",
              "pastas-sem-prompt" in fake.retorno, fake.retorno)
        janela._agente = None
        janela.close()

    print(f"\n==> {ok} corretos, {fail} falhas")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
