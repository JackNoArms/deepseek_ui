"""Onde o app lê recursos e grava dados (`src/caminhos.py`).

Plano: [[Planos/Instalador Windows]].
"""

import sys
from pathlib import Path

from src import caminhos


def test_codigo_fonte_mantem_tudo_na_pasta_do_projeto(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_UI_DADOS", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    raiz = caminhos.RAIZ_CODIGO
    assert caminhos.arquivo_config() == raiz / ".workspace.json"
    assert caminhos.arquivo_token() == raiz / ".deepseek_ui" / "remote_token"
    assert caminhos.pasta_perfil_chrome() == raiz / "chrome_profile"
    assert caminhos.recurso("config.json") == raiz / "config.json"


def test_instalado_grava_em_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_UI_DADOS", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "pacote"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    base = tmp_path / "local" / "DeepSeek UI"
    assert caminhos.arquivo_config() == base / "workspace.json"
    assert caminhos.arquivo_token() == base / "remote_token"
    assert caminhos.pasta_perfil_chrome() == base / "chrome_profile"
    assert caminhos.recurso("assets", "favicon.png") == tmp_path / "pacote" / "assets" / "favicon.png"
    assert base.is_dir()


def test_override_usa_layout_de_instalado(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_UI_DADOS", str(tmp_path / "d"))
    assert caminhos.arquivo_token() == tmp_path / "d" / "remote_token"
    assert caminhos.pasta_logs() == tmp_path / "d" / "logs"


def _copia_antiga(raiz: Path) -> Path:
    (raiz / ".deepseek_ui").mkdir(parents=True)
    (raiz / "main.py").write_text("")
    (raiz / ".workspace.json").write_text('{"tema": "papel"}')
    (raiz / ".deepseek_ui" / "remote_token").write_text("tok-antigo")
    (raiz / ".deepseek_ui" / "vapid_private.pem").write_text("pem")
    perfil = raiz / "chrome_profile" / "Default"
    perfil.mkdir(parents=True)
    (perfil / "Cookies").write_text("login")
    (raiz / "chrome_profile" / "SingletonLock").write_text("trava")
    return raiz


def test_importar_de_copia_antiga(tmp_path):
    origem = _copia_antiga(tmp_path / "antiga")
    destino = tmp_path / "novo"
    assert caminhos.parece_copia_do_app(origem)
    trazidos = caminhos.importar_de(origem, destino)
    assert set(trazidos) == {"workspace.json", "remote_token",
                             "vapid_private.pem", "chrome_profile"}
    assert (destino / "remote_token").read_text() == "tok-antigo"
    assert (destino / "chrome_profile" / "Default" / "Cookies").read_text() == "login"
    assert not (destino / "chrome_profile" / "SingletonLock").exists()
    assert (origem / ".workspace.json").exists(), "origem não é apagada"


def test_importar_nao_sobrescreve(tmp_path):
    origem = _copia_antiga(tmp_path / "antiga")
    destino = tmp_path / "novo"
    destino.mkdir()
    (destino / "remote_token").write_text("tok-novo")
    trazidos = caminhos.importar_de(origem, destino)
    assert "remote_token" not in trazidos
    assert (destino / "remote_token").read_text() == "tok-novo"


def test_pasta_qualquer_nao_parece_copia(tmp_path):
    assert not caminhos.parece_copia_do_app(tmp_path)
    (tmp_path / "main.py").write_text("")
    assert not caminhos.parece_copia_do_app(tmp_path)
