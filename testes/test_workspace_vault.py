"""Testa a associação de vault, suas instruções e a árvore do projeto."""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DEEPSEEK_UI_CONFIG"] = str(
    Path(tempfile.gettempdir()) / "deepseek_ui_workspace_vault_test.json")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from PyQt6.QtWidgets import QApplication

from src.prompts import REGRAS_VAULT, montar
from src.project import Project
from src.session import ProjectSession
from src.theme import Color, stylesheet
from src.window import MainWindow
from src.vault import WorkspaceStore, conteudo_nota
from src.vault_view import TextFileDialog
import src.window as window_module

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


def aguarda(app, condicao, timeout=5):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        app.processEvents()
        if condicao():
            return True
        time.sleep(0.01)
    app.processEvents()
    return condicao()


with tempfile.TemporaryDirectory(prefix="workspace_vault_") as temp:
    base = Path(temp)
    projeto = base / "projeto"
    vault = projeto / "vault"
    (projeto / "src").mkdir(parents=True)
    vault.mkdir()
    (projeto / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (vault / "AGENTS.md").write_text("Use testes focados.", encoding="utf-8")

    print("-- 1. vínculo de vault por projeto --")
    sessao = ProjectSession(projeto)
    checa("sem vault inicialmente", sessao.vault_path() is None)
    checa("salva vault", sessao.salvar_vault(str(vault)))
    checa("normaliza para caminho absoluto",
          sessao.vault_path() == str(vault.resolve()), sessao.vault_path())
    checa("vínculo persiste em nova sessão",
          ProjectSession(projeto).vault_path() == str(vault.resolve()))

    print("\n-- 2. instruções entram no prompt --")
    prompt = montar(
        "Corrija o projeto", Project(projeto), primeira=True,
        instrucoes="Use testes focados.")
    checa("prompt contém instruções", "Use testes focados." in prompt)
    checa("prompt identifica AGENTS.md", "AGENTS.md no vault" in prompt)
    checa("primeira mensagem orienta o uso do vault",
          REGRAS_VAULT in prompt and "vault/00 - Índice.md" in prompt)
    sem_mapa = montar("Corrija o projeto", Project(projeto), incluir_mapa=False)
    checa("recusar o mapa omite arquivos e grants do prompt",
          "main.py" not in sem_mapa and str(projeto.resolve()) not in sem_mapa
          and "não foram compartilhados" in sem_mapa,
          sem_mapa)

    print("\n-- 3. árvore e edição pela UI --")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(stylesheet())
    janela = MainWindow()
    janela._set_project(str(projeto), avisar=False)
    checa("carrega árvores sem bloquear a janela",
          aguarda(app, lambda: janela.project_tree.topLevelItemCount() > 0
                  and janela.vault_tree.topLevelItemCount() > 0))
    estilos = stylesheet()
    checa("abas do projeto identificadas para o tema",
          janela.workspace_tabs.objectName() == "workspaceTabs"
          and "QTabWidget#workspaceTabs::pane" in estilos)
    checa("árvore usa superfície e texto do tema",
          janela.project_tree.objectName() == "projectTree"
          and "QTreeWidget#projectTree" in estilos)
    checa("árvore do vault usa o tema",
          janela.vault_tree.objectName() == "vaultTree"
          and "QTreeWidget#vaultTree" in estilos)
    editor_arquivo = TextFileDialog(
        "Editar arquivo", "vault/Notas/Exemplo.md", "# Título\n", janela)
    checa("editor de arquivo usa superfície escura e texto legível",
          editor_arquivo.editor.objectName() == "workspaceEditor"
          and "QPlainTextEdit#workspaceEditor" in estilos
          and f"color: {Color.CODE_TEXT}" in estilos)
    editor_arquivo.deleteLater()
    checa("árvore tem src", janela.project_tree.topLevelItemCount() >= 1)
    src_item = next(
        (janela.project_tree.topLevelItem(i)
         for i in range(janela.project_tree.topLevelItemCount())
         if janela.project_tree.topLevelItem(i).text(0) == "src"),
        None)
    checa("árvore mostra arquivo aninhado",
          src_item is not None and src_item.childCount() == 1
          and src_item.child(0).text(0) == "main.py")
    checa("vault encontrado ao abrir o projeto",
          janela._vault_instructions == "Use testes focados.",
          janela._vault_instructions)
    checa("árvore do vault mostra notas e instruções",
          janela.vault_tree.topLevelItemCount() > 0
          and (vault / "00 - Índice.md").is_file()
          and (vault / "Padrão de notas.md").is_file())

    print("\n-- 3b. varredura lenta do vault roda fora da UI --")
    sentinela = vault / "varredura-em-background.md"
    sentinela.write_text("# teste\n", encoding="utf-8")
    thread_ids = []
    listar_original = WorkspaceStore.entries

    def listar_lento(store):
        thread_ids.append(threading.get_ident())
        time.sleep(0.2)
        return listar_original(store)

    thread_ui = threading.get_ident()
    with patch.object(WorkspaceStore, "entries", listar_lento):
        inicio = time.monotonic()
        janela._atualizar_arvore_vault()
        duracao = time.monotonic() - inicio
        checa("pedido de atualização retorna sem esperar varredura",
              duracao < 0.1, duracao)
        checa("resultado assíncrono aparece na árvore",
              aguarda(app, lambda: any(
                  janela.vault_tree.topLevelItem(i).text(0)
                  == "varredura-em-background.md"
                  for i in range(janela.vault_tree.topLevelItemCount()))))
        checa("listagem ocorreu em thread de fundo",
              thread_ids and all(tid != thread_ui for tid in thread_ids),
              thread_ids)
    janela._gravar_arquivo_workspace(
        "vault", "AGENTS.md", "Revise o diff antes de aplicar.")
    checa("salva AGENTS.md",
          (vault / "AGENTS.md").read_text(encoding="utf-8")
          == "Revise o diff antes de aplicar.")
    checa("nota criada no formulário recebe padrão e datas",
          "tipo: decisao" in conteudo_nota(
              "Registro de decisão", "decisao", "arquitetura",
              "Contexto do pedido", "Decisão", hoje="2026-10-15")
          and "atualizado: 2026-10-15" in conteudo_nota(
              "Registro de decisão", "decisao", hoje="2026-10-15"))

    pasta_nova = vault / "Notas" / "CRUD"
    store_vault = WorkspaceStore(vault, projeto, backup_prefix="_vault")
    store_vault.create_folder("Notas/CRUD")
    janela._gravar_arquivo_workspace("vault", "Notas/CRUD/Teste.md", "# nota\n",
                                     criar=True)
    janela._gravar_arquivo_workspace("vault", "Notas/CRUD/Teste.md", "# editada\n")
    checa("vault permite criar pasta e nota pela árvore",
          (pasta_nova / "Teste.md").read_text(encoding="utf-8") == "# editada\n")
    store_vault.delete("Notas/CRUD")
    checa("exclusão de pasta mantém cópia no backup",
          not pasta_nova.exists()
          and any((projeto / ".deepseek_ui" / "backups").rglob("CRUD")))

    outro = base / "outro"
    outro.mkdir()
    outro_vault = base / "outro-vault"
    outro_vault.mkdir()
    ProjectSession(outro).salvar_vault(str(outro_vault))
    janela._set_project(str(outro), avisar=False)
    checa("trocar projeto carrega vault correspondente",
          ProjectSession(outro).vault_path() == str(outro_vault.resolve()))
    checa("trocar projeto não altera vínculo anterior",
          ProjectSession(projeto).vault_path() == str(vault.resolve()))
    janela.close()

    print("\n-- 3c. selecionar/preparar um vault não bloqueia a UI --")
    projeto_escolha = base / "projeto-escolha"
    projeto_escolha.mkdir()
    vault_escolhido = base / "vault-escolhido"
    vault_escolhido.mkdir()
    janela_escolha = MainWindow()
    janela_escolha._set_project(str(projeto_escolha), avisar=False)
    preparar_original = window_module.garantir_vault
    threads_preparo = []

    def preparar_lento(caminho, nome):
        threads_preparo.append(threading.get_ident())
        time.sleep(0.2)
        return preparar_original(caminho, nome)

    thread_ui = threading.get_ident()
    with patch.object(
            window_module.QFileDialog, "getExistingDirectory",
            return_value=str(vault_escolhido)), \
            patch.object(window_module, "garantir_vault", preparar_lento):
        inicio = time.monotonic()
        janela_escolha._open_vault()
        duracao = time.monotonic() - inicio
        checa("seleção retorna sem esperar a preparação",
              duracao < 0.1, duracao)
        checa("prepara e vincula vault em segundo plano",
              aguarda(app, lambda: ProjectSession(projeto_escolha).vault_path()
                      == str(vault_escolhido.resolve()))
              and threads_preparo and all(
                  tid != thread_ui for tid in threads_preparo),
              threads_preparo)
    janela_escolha.close()

    print("\n-- 4. vault padrão criado automaticamente --")
    sem_vault = base / "sem-vault"
    sem_vault.mkdir()
    janela2 = MainWindow()
    janela2._set_project(str(sem_vault), avisar=False)
    caminho_padrao = sem_vault / "vault"
    checa("cria e vincula vault padrão",
          ProjectSession(sem_vault).vault_path() == str(caminho_padrao.resolve()))
    checa("cria índice central com esqueleto",
          (caminho_padrao / "00 - Índice.md").is_file()
          and "Visão geral" in (caminho_padrao / "00 - Índice.md").read_text(
              encoding="utf-8"))
    checa("primeira mensagem inclui o índice do projeto",
          "Visão geral" in montar(
              "Comece", janela2.project, primeira=True))
    janela2.close()

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
