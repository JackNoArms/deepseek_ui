"""Testes da ponte requisição/resposta (`RemoteServer.executar_na_gui`).

O `RemoteServer` em produção emite `execute` para a thread da GUI e espera
num `threading.Event`. Aqui não há GUI nem event loop: para os casos de sucesso
conecto `execute` a um slot que chama a tarefa direto (equivale ao Qt entregar
numa `DirectConnection`); para o caso de "GUI ocupada" conecto a um no-op
(equivale ao sinal ficar enfileirado esperando o modal fechar).

O que se prova:

- Sucesso: devolve o valor do handler e emite `remote_action` para o PC ver.
- Erro do handler: devolve o erro, **não** emite `remote_action`.
- Comando silencioso (`_COMANDOS_SILENCIOSOS`): não emite `remote_action`.
- GUI travada além do timeout: devolve `{erro:'app_ocupado', dica:...}` sem
  esperar o handler terminar.
"""

import pytest
from PyQt6.QtCore import QCoreApplication

from src.remote import RemoteServer

_APP = None


@pytest.fixture(scope="module", autouse=True)
def qcore():
    global _APP
    _APP = QCoreApplication.instance() or QCoreApplication([])
    yield


class _HandlerFalso:
    """Só os métodos que o teste chama; o nome `_remote_*` importa."""

    def __init__(self, retorno=None):
        self.retorno = retorno
        self.chamadas = []

    def _remote_write_file(self, **kwargs):
        self.chamadas.append(("write_file", kwargs))
        return self.retorno if self.retorno is not None else {"ok": True}

    def _remote_list_tree(self, **kwargs):
        self.chamadas.append(("list_tree", kwargs))
        return {"ok": True, "entries": []}


@pytest.fixture
def servidor_rodando(tmp_path):
    """Servidor com `execute` conectado a um slot que roda a tarefa direto."""
    s = RemoteServer(porta=0, token_path=str(tmp_path / "token"))
    s.bridge.execute.connect(lambda tarefa: tarefa())
    return s


def test_sucesso_emite_remote_action(servidor_rodando):
    servidor_rodando.set_handlers(_HandlerFalso(retorno={"ok": True}))
    emitidos = []
    servidor_rodando.bridge.remote_action.connect(
        lambda metodo, resumo: emitidos.append((metodo, resumo)))

    resultado = servidor_rodando.executar_na_gui(
        "_remote_write_file", tipo="projeto", caminho="a.txt", conteudo="x")

    assert resultado == {"ok": True}
    assert len(emitidos) == 1
    metodo, resumo = emitidos[0]
    assert metodo == "_remote_write_file"
    assert "a.txt" in resumo


def test_erro_nao_emite_remote_action(servidor_rodando):
    servidor_rodando.set_handlers(_HandlerFalso(retorno={"erro": "falhou"}))
    emitidos = []
    servidor_rodando.bridge.remote_action.connect(
        lambda metodo, resumo: emitidos.append((metodo, resumo)))

    resultado = servidor_rodando.executar_na_gui(
        "_remote_write_file", tipo="projeto", caminho="a.txt", conteudo="x")

    assert resultado == {"erro": "falhou"}
    assert emitidos == []


def test_comando_silencioso_nao_emite(servidor_rodando):
    servidor_rodando.set_handlers(_HandlerFalso(retorno={"ok": True}))
    emitidos = []
    servidor_rodando.bridge.remote_action.connect(
        lambda metodo, resumo: emitidos.append((metodo, resumo)))

    servidor_rodando.executar_na_gui("_remote_list_tree", tipo="projeto")

    assert emitidos == []


def test_timeout_devolve_app_ocupado(tmp_path):
    """GUI travada além do timeout → `app_ocupado` sem esperar o handler.

    Simulo "GUI ocupada" conectando `execute` a um no-op: o sinal não chega
    ao handler, o evento interno nunca é setado, o `wait(timeout)` estoura.
    É exatamente o que acontece quando um modal está aberto no PC — o slot da
    GUI não roda até o modal fechar, e a requisição HTTP precisa falhar rápido.
    """
    s = RemoteServer(porta=0, token_path=str(tmp_path / "token"))
    s.bridge.execute.connect(lambda _tarefa: None)  # GUI nunca roda a tarefa
    s.set_handlers(_HandlerFalso())
    emitidos = []
    s.bridge.remote_action.connect(
        lambda metodo, resumo: emitidos.append((metodo, resumo)))

    resultado = s.executar_na_gui(
        "_remote_write_file", timeout=0.2,
        tipo="projeto", caminho="travado.txt", conteudo="x")

    assert resultado.get("erro") == "app_ocupado"
    assert "dica" in resultado
    assert emitidos == []


def test_sem_handlers_devolve_erro(tmp_path):
    """Sem `set_handlers` (servidor subiu fora da janela): erro claro."""
    s = RemoteServer(porta=0, token_path=str(tmp_path / "token"))
    s.bridge.execute.connect(lambda tarefa: tarefa())
    resultado = s.executar_na_gui("_remote_write_file", caminho="x")
    assert resultado.get("erro") == "servidor sem janela registrada"


def test_metodo_desconhecido(servidor_rodando):
    servidor_rodando.set_handlers(_HandlerFalso())
    resultado = servidor_rodando.executar_na_gui("_remote_nao_existe")
    assert "erro" in resultado
    assert "desconhecido" in resultado["erro"]
