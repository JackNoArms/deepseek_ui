"""Configuração do pytest para o projeto.

Existem dois tipos de teste convivendo em `testes/`:

1. **Scripts standalone** (`test_parser.py`, `test_runner.py`, ...) que montam
   o próprio `ok/fail`, imprimem no console e terminam com `sys.exit`. São
   executados por `python testes/rodar_tudo.py` ou diretamente. Como rodam o
   corpo inteiro no import, o pytest os derrubaria com `SystemExit` durante a
   coleta.

2. **Testes pytest de verdade** (`test_remote.py`, `test_multiplas_instancias.py`,
   `test_skills*.py`) com funções `test_*` e asserções, pensados para rodar via
   `pytest testes/`.

Para os dois conviverem, o pytest ignora a lista abaixo. Os scripts standalone
continuam rodando pelo `rodar_tudo.py` e por invocação direta — nada muda para
eles. Ao criar um novo script standalone, adicione o nome do arquivo aqui; ao
criar um teste no formato pytest, não o inclua.

**Qt em testes.** `QT_QPA_PLATFORM=offscreen` é definido aqui, antes de qualquer
módulo test_* importar PyQt6 — caso contrário, dependendo da ordem de import o
PyQt carrega a plataforma nativa e a segunda inicialização em ambiente headless
derruba o processo (`STATUS_STACK_BUFFER_OVERRUN` em Python 3.14 + PyQt6).

`pytest_sessionstart` cria uma **`QApplication`** antes de qualquer teste tocar
PyQt. `QApplication` é superset de `QCoreApplication` — uma vez criada, todo
`.instance()` posterior devolve ela. Sem isso, um teste que crie
`QCoreApplication` primeiro (era o caso do `test_remote.py` original) impede
que qualquer `QApplication` seja criada no mesmo processo, derrubando o pytest
com `STATUS_STACK_BUFFER_OVERRUN`. A fixture `qt_app` continua disponível para
os testes que precisam da referência explícita.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

collect_ignore = [
    "test_access_profiles.py",
    "test_agente_investiga.py",
    "test_agente_ui.py",
    "test_anexos.py",
    "test_captura_tamanho.py",
    "test_chat_decisao.py",
    "test_executor.py",
    "test_fila_decisao_ui.py",
    "test_parser.py",
    "test_permissions.py",
    "test_processos.py",
    "test_protocolos.py",
    "test_runner.py",
    "test_testes_tela.py",
    "test_sandbox.py",
    "test_sessao_terminal.py",
    "test_ui_fase2.py",
    "test_vault_management.py",
    "test_workspace_vault.py",
    "test_wrapper_envio.py",
]


def pytest_sessionstart(session):
    """Cria `QApplication` antes de qualquer teste tocar PyQt.

    Previne que algum teste crie `QCoreApplication` primeiro (o que impede
    `QApplication` de existir no mesmo processo — fatal no Windows/Python 3.14).
    `QApplication` herda de `QCoreApplication`, então todo `.instance()`
    posterior devolve esta.
    """
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication([])


@pytest.fixture(scope="session")
def qt_app():
    """Devolve a `QApplication` já criada por `pytest_sessionstart`.

    Mantida para testes que querem dependência explícita. `QApplication` é
    singleton — chamar `.instance()` aqui é só um acessor.
    """
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
