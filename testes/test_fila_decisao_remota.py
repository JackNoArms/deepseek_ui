"""Fila cancelável, decisão com anexo e importação de skills (contrato).

Cobre o lado sem janela real do plano
[[Planos/Remap visual, decisões, fila e importação de skills]]:

- rotas `/api/queue/cancel`, `/api/queue/clear` e `anexos_json` em
  `/api/decision/<id>` (servidor HTTP em porta efêmera, `execute` ligado a
  uma chamada direta, como em `test_remote_ponte.py`);
- handlers `_remote_cancel_queue`, `_remote_clear_queue`,
  `_remote_decision_attach` e `converter_anexos_json`;
- `SkillsRepo.importar` / `importar_texto` e a importação pela `SkillsView`.
"""

import base64
import http.client
import json
import zipfile
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt

from src.remote import RemoteServer
from src.remote_handlers import RemoteHandlersMixin, converter_anexos_json
from src.skills import SkillsRepo


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# ---------------- handlers ----------------


class _Janela(RemoteHandlersMixin):
    def __init__(self):
        self._anexos = []
        self._decisoes_remotas = {}
        self._anexos_decisao_remota = {}
        self.fila = ["q1", "q2"]

    def _cancelar_da_fila(self, id_pedido):
        if id_pedido in self.fila:
            self.fila.remove(id_pedido)
            return True
        return False

    def _editar_texto_fila(self, id_pedido, texto):
        if id_pedido in self.fila:
            self.textos = {id_pedido: texto}
            return True
        return False

    def _limpar_fila(self):
        total = len(self.fila)
        self.fila.clear()
        return total


def test_cancelar_item_da_fila():
    janela = _Janela()
    assert janela._remote_cancel_queue(id="q2") == {"ok": True}
    assert janela.fila == ["q1"]


def test_cancelar_item_que_ja_saiu_da_fila_avisa():
    janela = _Janela()
    assert "erro" in janela._remote_cancel_queue(id="q9")


def test_editar_item_da_fila():
    janela = _Janela()
    assert janela._remote_edit_queue(id="q1", texto="novo texto") == {"ok": True}
    assert janela.textos == {"q1": "novo texto"}


def test_editar_com_texto_vazio_e_recusado():
    janela = _Janela()
    assert "erro" in janela._remote_edit_queue(id="q1", texto="  ")


def test_editar_item_que_saiu_da_fila_avisa():
    janela = _Janela()
    assert "erro" in janela._remote_edit_queue(id="q9", texto="x")


def test_limpar_fila_devolve_quantos_cancelou():
    janela = _Janela()
    assert janela._remote_clear_queue() == {"ok": True, "cancelados": 2}
    assert janela.fila == []


def test_converter_anexos_json_imagem_vira_upload_temporario():
    convertidos, recusados = converter_anexos_json(
        [{"rotulo": "print.png", "tipo_mime": "image/png", "dados_b64": _b64(PNG)},
         {"rotulo": "nota.md", "tipo_mime": "text/markdown",
          "dados_b64": _b64("# oi".encode())},
         {"rotulo": "ruim", "dados_b64": "@@@"}])
    try:
        assert [a.modo for a in convertidos] == ["upload", "inline"]
        assert Path(convertidos[0].caminho).read_bytes() == PNG
        assert convertidos[0].temporario is True
        assert convertidos[1].conteudo == "# oi"
        assert len(recusados) == 1
    finally:
        for anexo in convertidos:
            anexo.descartar()


def test_anexo_de_decisao_fica_guardado_ate_a_resposta():
    janela = _Janela()
    janela._decisoes_remotas["abc"] = lambda *a, **k: None
    r = janela._remote_decision_attach(
        id_card="abc",
        anexos_json=[{"rotulo": "tela.png", "tipo_mime": "image/png",
                      "dados_b64": _b64(PNG)}])
    assert r["ok"] is True and r["adicionados"] == ["tela.png"]
    guardados = janela._anexos_decisao_remota["abc"]
    assert len(guardados) == 1 and Path(guardados[0].caminho).exists()
    guardados[0].descartar()
    # Não vai para os anexos do composer.
    assert janela._anexos == []


def test_anexo_de_decisao_desconhecida_e_recusado():
    janela = _Janela()
    r = janela._remote_decision_attach(
        id_card="nao-existe",
        anexos_json=[{"rotulo": "a.png", "dados_b64": _b64(PNG)}])
    assert "erro" in r
    assert janela._anexos_decisao_remota == {}


# ---------------- rotas HTTP ----------------


class _Acao:
    def __init__(self):
        self.extras = {"pergunta": "A ou B?", "opcoes": ["A", "B"],
                       "recomendada": 1, "motivo": None}


class _HandlersRota:
    def __init__(self):
        self.chamadas = []

    def _remote_cancel_queue(self, id=""):
        self.chamadas.append(("cancel", id))
        return {"ok": True}

    def _remote_edit_queue(self, id="", texto=""):
        self.chamadas.append(("edit", id, texto))
        return {"ok": True}

    def _remote_clear_queue(self):
        self.chamadas.append(("clear",))
        return {"ok": True, "cancelados": 3}

    def _remote_decision_attach(self, id_card="", anexos_json=None):
        self.chamadas.append(("attach", id_card, len(anexos_json or [])))
        return {"ok": True, "adicionados": ["a.png"], "recusados": []}


@pytest.fixture
def servidor(tmp_path, qt_app):
    s = RemoteServer(porta=0, token_path=str(tmp_path / "token"))
    # Thread HTTP sem event loop na principal: a tarefa roda direto nela.
    s.bridge.execute.connect(lambda tarefa: tarefa(),
                             Qt.ConnectionType.DirectConnection)
    s.handlers_falsos = _HandlersRota()
    s.set_handlers(s.handlers_falsos)
    s.start()
    yield s
    s.stop()


def _post(servidor, caminho, payload):
    con = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=5)
    con.request("POST", caminho, body=json.dumps(payload), headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {servidor.token}"})
    r = con.getresponse()
    corpo = json.loads(r.read() or b"{}")
    con.close()
    return r.status, corpo


def test_rota_cancelar_fila(servidor):
    status, corpo = _post(servidor, "/api/queue/cancel", {"id": "q7"})
    assert status == 200 and corpo == {"ok": True}
    assert servidor.handlers_falsos.chamadas == [("cancel", "q7")]


def test_rota_editar_fila(servidor):
    status, corpo = _post(servidor, "/api/queue/edit", {"id": "q2", "texto": "outro"})
    assert status == 200 and corpo == {"ok": True}
    assert servidor.handlers_falsos.chamadas == [("edit", "q2", "outro")]


def test_css_dos_temas_tem_os_seis(servidor):
    con = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=5)
    con.request("GET", "/remote_theme.css")
    r = con.getresponse()
    css = r.read().decode("utf-8")
    con.close()
    assert r.status == 200
    from src.theme import TEMAS
    for nome in TEMAS:
        assert f':root[data-tema="{nome}"]' in css
    assert "--bw: 2px" in css and "color-scheme: light" in css


def test_rota_limpar_fila(servidor):
    status, corpo = _post(servidor, "/api/queue/clear", {})
    assert status == 200 and corpo["cancelados"] == 3


def test_estado_publica_itens_da_fila(servidor):
    itens = [{"id": "q1", "texto": "roda os testes", "anexos": [], "agente": True}]
    servidor.update(queue=1, queue_items=itens)
    assert servidor.snapshot()["queue_items"] == itens


def test_decisao_com_anexo_passa_pelo_handler_antes_de_responder(servidor):
    respostas = []
    servidor.bridge.decision_answered.connect(
        lambda id_card, escolha: respostas.append((id_card, escolha)),
        Qt.ConnectionType.DirectConnection)
    id_card = servidor.publish_decision(_Acao())
    status, corpo = _post(servidor, f"/api/decision/{id_card}", {
        "escolha": "Nenhuma, veja o print",
        "anexos_json": [{"rotulo": "a.png", "dados_b64": _b64(PNG)}]})
    assert status == 200, corpo
    assert servidor.handlers_falsos.chamadas == [("attach", id_card, 1)]
    assert respostas == [(id_card, "Nenhuma, veja o print")]


def test_decisao_resolvida_nao_aceita_anexo_atrasado(servidor):
    id_card = servidor.publish_decision(_Acao())
    servidor.mark_resolved(id_card, "A")
    status, _ = _post(servidor, f"/api/decision/{id_card}", {
        "escolha": "B", "anexos_json": [{"rotulo": "a.png", "dados_b64": _b64(PNG)}]})
    assert status == 409
    assert servidor.handlers_falsos.chamadas == []


# ---------------- importação de skills ----------------


def _skill(pasta: Path, nome: str, extra: dict | None = None):
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "SKILL.md").write_text(
        f"---\nname: {nome}\ndescription: Faz {nome}\n---\n\n# {nome}\n",
        encoding="utf-8")
    for rel, conteudo in (extra or {}).items():
        alvo = pasta / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    projeto = tmp_path / "proj"
    projeto.mkdir()
    r = SkillsRepo(projeto, bootstrap=False)
    r.load()
    return r


def test_importa_pasta_de_skill_com_arquivos_de_apoio(repo, tmp_path):
    _skill(tmp_path / "pdf", "pdf", {"scripts/extrai.py": "print(1)",
                                    ".git/HEAD": "ref", "__pycache__/x.pyc": ""})
    res = repo.importar(tmp_path / "pdf")
    assert [s.slug for s in res.importadas] == ["pdf"]
    destino = repo.skills_dir / "pdf"
    assert (destino / "scripts" / "extrai.py").read_text() == "print(1)"
    assert not (destino / ".git").exists()
    assert not (destino / "__pycache__").exists()
    assert repo.by_slug("pdf").habilitada is False


def test_importa_varias_skills_de_uma_pasta(repo, tmp_path):
    _skill(tmp_path / "pack" / "a", "a")
    _skill(tmp_path / "pack" / "grupo" / "b", "b")
    res = repo.importar(tmp_path / "pack")
    assert sorted(s.slug for s in res.importadas) == ["a", "b"]


def test_importar_de_novo_nao_sobrescreve(repo, tmp_path):
    _skill(tmp_path / "x", "x")
    repo.importar(tmp_path / "x")
    (repo.skills_dir / "x" / "SKILL.md").write_text(
        "---\nname: x\ndescription: editada\n---\n", encoding="utf-8")
    res = repo.importar(tmp_path / "x")
    assert [s.slug for s in res.importadas] == ["x-2"]
    assert "editada" in (repo.skills_dir / "x" / "SKILL.md").read_text("utf-8")


def test_importa_skill_md_solto_traz_a_pasta(repo, tmp_path):
    _skill(tmp_path / "rev", "rev", {"ref.md": "apoio"})
    res = repo.importar(tmp_path / "rev" / "SKILL.md")
    assert [s.slug for s in res.importadas] == ["rev"]
    assert (repo.skills_dir / "rev" / "ref.md").exists()


def test_importa_markdown_qualquer_como_skill(repo, tmp_path):
    arquivo = tmp_path / "Checklist de PR.md"
    arquivo.write_text("# Checklist de PR\n\n- testes\n", encoding="utf-8")
    res = repo.importar(arquivo)
    assert res.importadas[0].name == "Checklist de PR"
    assert res.importadas[0].slug == "checklist-de-pr"


def test_importar_texto_usa_frontmatter(repo):
    skill = repo.importar_texto(
        "---\nname: deploy\ndescription: Sobe para produção\n---\n\nPassos")
    assert (skill.slug, skill.name, skill.description) == (
        "deploy", "deploy", "Sobe para produção")
    assert skill.conteudo.strip() == "Passos"


def test_importa_zip(repo, tmp_path):
    z = tmp_path / "skills.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("pacote/web/SKILL.md", "---\nname: web\ndescription: w\n---\nok")
        zf.writestr("pacote/web/assets/a.css", "body{}")
    res = repo.importar(z)
    assert [s.slug for s in res.importadas] == ["web"]
    assert (repo.skills_dir / "web" / "assets" / "a.css").exists()


def test_zip_com_caminho_para_fora_e_recusado(repo, tmp_path):
    z = tmp_path / "mal.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../fora/SKILL.md", "---\nname: x\n---")
    res = repo.importar(z)
    assert res.importadas == []
    assert "inseguro" in res.ignorados[0]
    assert not (tmp_path.parent / "fora").exists()


def test_pasta_sem_skill_md_e_informada(repo, tmp_path):
    (tmp_path / "vazia").mkdir()
    res = repo.importar(tmp_path / "vazia")
    assert res.importadas == [] and "nenhum SKILL.md" in res.ignorados[0]


def test_view_importa_e_seleciona_e_habilita(qt_app, repo, tmp_path):
    from src.skills_view import SkillsView

    _skill(tmp_path / "nova", "nova")
    view = SkillsView(repo)
    view.importar_caminhos([str(tmp_path / "nova")])
    assert view._skill_atual is not None and view._skill_atual.slug == "nova"
    assert "1 importada" in view.lbl_status.text()
    view.chk_habilitada.setChecked(True)
    assert repo.by_slug("nova").habilitada is True
    assert SkillsRepo(repo.base_dir, bootstrap=False).load()[0].habilitada is True
