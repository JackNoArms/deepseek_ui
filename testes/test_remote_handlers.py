"""Testes dos handlers remotos (`RemoteHandlersMixin`).

Os handlers rodam na thread da GUI quando chamados pelo servidor HTTP, mas
são testáveis diretamente: só tocam em `Project`, `WorkspaceStore`,
`ProjectSession` e em atributos simples da janela. Crio um `FakeWindow`
que herda do mixin e monta o mínimo que cada handler precisa — sem QApplication.

O que fica de fora: nada. Os handlers são o contrato que o painel remoto
usa; deixar sem teste é o mesmo que deixar a rota sem teste.
"""

import base64
from pathlib import Path

import pytest

from src import anexos
from src.permissions import PermissionPolicy
from src.project import Project
from src.remote_handlers import RemoteHandlersMixin
from src.session import ProjectSession


@pytest.fixture
def fake_window(tmp_path, monkeypatch):
    """Janela de mentira: só o que os handlers usam de verdade.

    `_atualizar_arvore`, `_atualizar_arvore_vault`, `_carregar_instrucoes_vault`
    e `_atualizar_feedback_acesso` são chamados pelos handlers para sincronizar
    a UI local. No FakeWindow viram no-op — a UI em si é outra camada.
    """
    config = tmp_path / "config.json"
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(config))
    raiz = tmp_path / "proj"
    raiz.mkdir()

    class FakeWindow(RemoteHandlersMixin):
        def __init__(self, project):
            self.project = project
            self.atualizacoes = {"arvore": 0, "vault": 0, "instrucoes": 0,
                                 "acesso": 0}
            self._anexos = []

        def _atualizar_arvore(self):
            self.atualizacoes["arvore"] += 1

        def _atualizar_arvore_vault(self):
            self.atualizacoes["vault"] += 1

        def _carregar_instrucoes_vault(self):
            self.atualizacoes["instrucoes"] += 1
            return True

        def _atualizar_feedback_acesso(self):
            self.atualizacoes["acesso"] += 1

        def _set_project(self, caminho, avisar=True):
            self.project = Project(caminho, PermissionPolicy(caminho))

        def _remover_anexo(self, chip):
            pass

        def _previsualizar_anexo(self, anexo):
            pass

    projeto = Project(str(raiz), PermissionPolicy(str(raiz)))
    return FakeWindow(projeto), raiz


# ---------------- projeto ----------------


def test_list_projects_inclui_atual(fake_window):
    janela, raiz = fake_window
    dados = janela._remote_list_projects()
    assert dados["atual"] == str(raiz.resolve())
    assert dados["nome_atual"] == raiz.name
    assert str(raiz.resolve()) in dados["recentes"]


def test_open_project_troca_raiz(fake_window, tmp_path):
    janela, _ = fake_window
    outra = tmp_path / "outra"
    outra.mkdir()
    dados = janela._remote_open_project(str(outra))
    assert dados.get("ok") is True
    assert janela.project.root == outra.resolve()


def test_open_project_caminho_invalido(fake_window, tmp_path):
    janela, _ = fake_window
    dados = janela._remote_open_project(str(tmp_path / "nao-existe"))
    assert "erro" in dados


def test_open_project_vazio(fake_window):
    janela, _ = fake_window
    assert "erro" in janela._remote_open_project("")


# ---------------- vault ----------------


def test_list_vaults(fake_window):
    janela, raiz = fake_window
    dados = janela._remote_list_vaults()
    assert "vinculado" in dados
    assert dados["padrao"] == str(raiz / "vault")


def test_open_vault_cria_e_vincula(fake_window, tmp_path):
    janela, _ = fake_window
    pasta = tmp_path / "meu_vault"
    pasta.mkdir()
    dados = janela._remote_open_vault(str(pasta))
    assert dados.get("ok") is True
    salvo = ProjectSession(janela.project.root).vault_path()
    assert salvo and Path(salvo).resolve() == pasta.resolve()


def test_open_vault_recusa_raiz_do_projeto(fake_window):
    janela, raiz = fake_window
    dados = janela._remote_open_vault(str(raiz))
    assert "erro" in dados


def test_open_vault_sem_projeto(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(config))

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

        def _atualizar_arvore(self):
            pass

        def _atualizar_arvore_vault(self):
            pass

        def _carregar_instrucoes_vault(self):
            return True

    f = Fake()
    assert "erro" in f._remote_list_vaults()
    assert "erro" in f._remote_open_vault(str(tmp_path))


# ---------------- árvore ----------------


def test_list_tree_projeto(fake_window):
    janela, raiz = fake_window
    (raiz / "a.py").write_text("x", encoding="utf-8")
    (raiz / "sub").mkdir()
    (raiz / "sub" / "b.md").write_text("y", encoding="utf-8")
    dados = janela._remote_list_tree("projeto")
    caminhos = {e["path"] for e in dados["entries"]}
    assert "a.py" in caminhos
    assert "sub/b.md" in caminhos


def test_list_tree_tipo_invalido(fake_window):
    janela, _ = fake_window
    assert "erro" in janela._remote_list_tree("qualquer")


def test_list_tree_vault_sem_vinculo_e_vazio(fake_window):
    janela, _ = fake_window
    dados = janela._remote_list_tree("vault")
    assert dados["entries"] == []


# ---------------- arquivo ----------------


def test_read_file(fake_window):
    janela, raiz = fake_window
    (raiz / "ola.txt").write_text("bom dia", encoding="utf-8")
    dados = janela._remote_read_file("projeto", "ola.txt")
    assert dados["conteudo"] == "bom dia"


def test_read_file_inexistente(fake_window):
    janela, _ = fake_window
    dados = janela._remote_read_file("projeto", "nao-existe.txt")
    assert "erro" in dados


def test_read_file_sandbox_recusa(fake_window):
    janela, _ = fake_window
    dados = janela._remote_read_file("projeto", "../fora.txt")
    assert "erro" in dados


def test_write_file_novo(fake_window):
    janela, raiz = fake_window
    dados = janela._remote_write_file("projeto", "novo.md", "# Título", criar=True)
    assert dados.get("ok") is True
    assert (raiz / "novo.md").read_text(encoding="utf-8") == "# Título"
    assert janela.atualizacoes["arvore"] >= 1


def test_write_file_edita_com_backup(fake_window):
    janela, raiz = fake_window
    alvo = raiz / "alvo.txt"
    alvo.write_text("antes", encoding="utf-8")
    dados = janela._remote_write_file("projeto", "alvo.txt", "depois")
    assert dados.get("ok") is True
    assert alvo.read_text(encoding="utf-8") == "depois"
    backups = list((raiz / ".deepseek_ui" / "backups").rglob("alvo.txt"))
    assert any(b.read_text(encoding="utf-8") == "antes" for b in backups)


def test_write_file_tipo_invalido(fake_window):
    janela, _ = fake_window
    assert "erro" in janela._remote_write_file("qualquer", "x", "y")


def test_delete_file_move_pra_backup(fake_window):
    janela, raiz = fake_window
    alvo = raiz / "apagar.txt"
    alvo.write_text("conteudo", encoding="utf-8")
    dados = janela._remote_delete_file("projeto", "apagar.txt")
    assert dados.get("ok") is True
    assert not alvo.exists()
    assert any(
        p.read_text(encoding="utf-8") == "conteudo"
        for p in (raiz / ".deepseek_ui" / "backups").rglob("apagar.txt"))


def test_delete_file_inexistente(fake_window):
    janela, _ = fake_window
    assert "erro" in janela._remote_delete_file("projeto", "nao-existe")


def test_new_folder(fake_window):
    janela, raiz = fake_window
    dados = janela._remote_new_folder("projeto", "nova")
    assert dados.get("ok") is True
    assert (raiz / "nova").is_dir()


def test_new_folder_dentro_de_subpasta_existente(fake_window):
    janela, raiz = fake_window
    (raiz / "sub").mkdir()
    dados = janela._remote_new_folder("projeto", "sub/nova")
    assert dados.get("ok") is True
    assert (raiz / "sub" / "nova").is_dir()


def test_new_folder_pai_inexistente_falha(fake_window):
    janela, _ = fake_window
    dados = janela._remote_new_folder("projeto", "nao-existe/nova")
    assert "erro" in dados


def test_new_folder_tipo_invalido(fake_window):
    janela, _ = fake_window
    assert "erro" in janela._remote_new_folder("qualquer", "x")


# ---------------- browse ----------------


def test_browse_lista_pastas(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))
    pai = tmp_path / "pai"
    pai.mkdir()
    (pai / "um").mkdir()
    (pai / "dois").mkdir()
    (pai / "arquivo.txt").write_text("ignorar", encoding="utf-8")
    (pai / ".oculto").mkdir()

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

    f = Fake()
    dados = f._remote_browse(str(pai))
    nomes = {c["nome"] for c in dados["filhos"]}
    assert nomes == {"um", "dois"}
    assert dados["pai"] == str(pai.parent)


def test_browse_pasta_inexistente(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

    f = Fake()
    dados = f._remote_browse(str(tmp_path / "nao-existe"))
    assert "erro" in dados


def test_browse_sem_caminho_usa_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

    f = Fake()
    dados = f._remote_browse("")
    assert "filhos" in dados
    assert dados["atual"] == str(Path.home())


# ---------------- busca ----------------


def test_buscar_acha_em_arquivo(fake_window):
    janela, raiz = fake_window
    (raiz / "a.py").write_text("def calcular():\n    return 1\n", encoding="utf-8")
    dados = janela._remote_buscar("calcular")
    assert dados.get("ok") is True
    assert "calcular" in dados["resultado"]


def test_buscar_sem_projeto(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

    f = Fake()
    assert "erro" in f._remote_buscar("x")


# ---------------- chat ----------------


def test_get_chat_devolve_historico(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Chat:
        def historico_json(self):
            return {"messages": [{"role": "user", "content": "oi", "ts": "12:00"}],
                    "streaming": None}

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []
        chat = Chat()

    f = Fake()
    dados = f._remote_get_chat()
    assert dados["messages"][0]["content"] == "oi"
    assert dados["streaming"] is None


# ---------------- send ----------------


def test_send_sem_conexao(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Ctrl:
        is_connected = False

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []
        controller = Ctrl()

        def __init__(self):
            self._enviado = None

        def _send(self):
            self._enviado = True

    f = Fake()
    dados = f._remote_send_message("oi")
    assert "erro" in dados


def test_send_com_projeto_sem_agente_e_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Ctrl:
        is_connected = True

    class Input:
        def __init__(self):
            self.texto = ""

        def setPlainText(self, t):
            self.texto = t

    class Pill:
        def set_state(self, on):
            self.on = on

    class Fake(RemoteHandlersMixin):
        def __init__(self):
            self.project = None
            self._anexos = []
            self.controller = Ctrl()
            self.input = Input()
            self.chk_agente = Pill()
            self.enviado = 0

        def _send(self):
            self.enviado += 1

    f = Fake()
    dados = f._remote_send_message("pergunta", agente=False)
    assert dados.get("ok") is True
    assert f.input.texto == "pergunta"
    assert f.enviado == 1


# ---------------- new chat ----------------


def test_new_chat_delega(fake_window):
    janela, _ = fake_window
    chamadas = {"n": 0}

    def _new_chat():
        chamadas["n"] += 1

    janela._new_chat = _new_chat
    class Ctrl:
        is_connected = True
    janela.controller = Ctrl()

    dados = janela._remote_new_chat()
    assert dados.get("ok") is True
    assert chamadas["n"] == 1


def test_new_chat_sem_metodo(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

    f = Fake()
    assert "erro" in f._remote_new_chat()


def test_new_chat_recusa_ocupado(fake_window):
    janela, _ = fake_window
    janela._new_chat = lambda: None
    class Ctrl:
        is_connected = True
    janela.controller = Ctrl()
    janela._envio_em_andamento = True
    assert "erro" in janela._remote_new_chat()


def test_new_chat_recusa_desconectado(fake_window):
    janela, _ = fake_window
    janela._new_chat = lambda: None
    class Ctrl:
        is_connected = False
    janela.controller = Ctrl()
    assert "erro" in janela._remote_new_chat()


# ---------------- permissions ----------------


def test_get_permissions(fake_window):
    janela, _ = fake_window
    dados = janela._remote_get_permissions()
    assert dados["ok"] is True
    assert dados["mode"] == "project_confirm"
    assert dados["confirm_reads"] is True
    assert dados["grants"] == []
    assert isinstance(dados["modos"], list)
    assert "project_confirm" in dados["modos"]
    assert "folders" in dados["modos"]


def test_set_permissions_troca_modo(fake_window):
    janela, _ = fake_window
    dados = janela._remote_set_permissions(
        "project_auto", [], False)
    assert dados.get("ok") is True
    assert janela.project.permissions.mode == "project_auto"
    assert janela.project.permissions.confirm_reads is False
    salvo = ProjectSession(janela.project.root).permissoes()
    assert salvo and salvo.get("mode") == "project_auto"
    assert janela.atualizacoes["acesso"] >= 1


def test_set_permissions_modo_invalido(fake_window):
    janela, _ = fake_window
    dados = janela._remote_set_permissions("qualquer", [], True)
    assert "erro" in dados


def test_set_permissions_grant_inexistente_recusa(fake_window):
    janela, _ = fake_window
    dados = janela._remote_set_permissions(
        "folders", [{"path": "Z:/nao/existe/mesmo"}], True)
    assert "erro" in dados


def test_set_permissions_sem_projeto(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Fake(RemoteHandlersMixin):
        project = None
        _anexos = []

    f = Fake()
    assert "erro" in f._remote_set_permissions("project_confirm", [], True)


# ---------------- anexos ----------------


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def test_attach_texto_pequeno_vira_inline(fake_window):
    janela, _ = fake_window
    conteudo = "print('oi')\n"
    dados = janela._remote_attach([
        {"rotulo": "exemplo.py", "tipo_mime": "text/x-python",
         "dados_b64": _b64(conteudo.encode("utf-8"))},
    ])
    assert dados.get("ok") is True
    assert len(janela._anexos) == 1
    anexo = janela._anexos[0]
    assert anexo.rotulo == "exemplo.py"
    assert anexo.modo == "inline"
    assert anexo.conteudo == conteudo
    assert anexo.caminho is None
    assert anexo.temporario is False


def test_attach_imagem_vira_upload(fake_window):
    janela, _ = fake_window
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    dados = janela._remote_attach([
        {"rotulo": "print.png", "tipo_mime": "image/png",
         "dados_b64": _b64(png)},
    ])
    assert dados.get("ok") is True
    assert len(janela._anexos) == 1
    anexo = janela._anexos[0]
    assert anexo.modo == "upload"
    assert anexo.temporario is True
    assert anexo.caminho and Path(anexo.caminho).is_file()
    assert Path(anexo.caminho).read_bytes() == png
    anexo.descartar()
    assert not Path(anexo.caminho).exists()


def test_attach_texto_grande_vira_upload(fake_window):
    janela, _ = fake_window
    grande = ("linha\n" * (anexos.MAX_INLINE_BYTES // 6 + 100)).encode("utf-8")
    dados = janela._remote_attach([
        {"rotulo": "grande.txt", "tipo_mime": "text/plain",
         "dados_b64": _b64(grande)},
    ])
    assert dados.get("ok") is True
    assert janela._anexos[0].modo == "upload"


def test_attach_base64_invalido_e_recusado(fake_window):
    janela, _ = fake_window
    dados = janela._remote_attach([
        {"rotulo": "x.py", "tipo_mime": "text/x-python",
         "dados_b64": "@@@ não é base64 @@"},
    ])
    assert "erro" in dados
    assert janela._anexos == []


def test_attach_lista_vazia_e_recusada(fake_window):
    janela, _ = fake_window
    assert "erro" in janela._remote_attach([])
    assert "erro" in janela._remote_attach(None)


def test_attach_sem_lista_de_anexos(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_UI_CONFIG", str(tmp_path / "c.json"))

    class Fake(RemoteHandlersMixin):
        project = None

    f = Fake()
    dados = f._remote_attach([
        {"rotulo": "x.txt", "tipo_mime": "text/plain", "dados_b64": _b64(b"oi")},
    ])
    assert "erro" in dados


def test_attach_sanitiza_nome(fake_window):
    janela, _ = fake_window
    dados = janela._remote_attach([
        {"rotulo": "../etc/passwd!.txt", "tipo_mime": "text/plain",
         "dados_b64": _b64(b"oi")},
    ])
    assert dados.get("ok") is True
    assert janela._anexos[0].rotulo == "passwd.txt"


def test_attach_aceita_multiplos_itens(fake_window):
    janela, _ = fake_window
    itens = [
        {"rotulo": f"a{i}.py", "tipo_mime": "text/x-python",
         "dados_b64": _b64(f"print({i})\n".encode("utf-8"))}
        for i in range(3)
    ]
    dados = janela._remote_attach(itens)
    assert dados.get("ok") is True
    assert len(janela._anexos) == 3
    assert dados["adicionados"][0]["rotulo"] == "a0.py"


def test_attach_ignora_itens_malformados(fake_window):
    janela, _ = fake_window
    dados = janela._remote_attach([
        {"rotulo": "sem_dados.py", "tipo_mime": "text/x-python"},
        {"rotulo": "vazio.py", "tipo_mime": "text/x-python", "dados_b64": ""},
        {"rotulo": "ok.py", "tipo_mime": "text/x-python",
         "dados_b64": _b64(b"print('ok')\n")},
    ])
    assert dados.get("ok") is True
    assert len(janela._anexos) == 1
    assert janela._anexos[0].rotulo == "ok.py"
    assert len(dados["recusados"]) == 2


def test_attach_limita_a_oito(fake_window):
    janela, _ = fake_window
    itens = [
        {"rotulo": f"a{i}.py", "tipo_mime": "text/x-python",
         "dados_b64": _b64(b"x\n")}
        for i in range(12)
    ]
    dados = janela._remote_attach(itens)
    assert dados.get("ok") is True
    assert len(janela._anexos) == 8


def test_attach_texto_sem_extensao_conhecida_vira_upload(fake_window):
    janela, _ = fake_window
    dados = janela._remote_attach([
        {"rotulo": "arquivo.bin", "tipo_mime": "application/octet-stream",
         "dados_b64": _b64(b"\x00\x01\x02")},
    ])
    assert dados.get("ok") is True
    assert janela._anexos[0].modo == "upload"
