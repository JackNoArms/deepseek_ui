"""Primeira execução da versão instalada: diálogo de importação (`main.py`).

Só roda empacotado, então nenhum teste passava por ele — e ele quebrava com
`QMessageBox.StandardIcon` (não existe no PyQt6). Aqui o diálogo abre de
verdade e os botões são clicados.
"""

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

import main
from src import caminhos


def _copia_antiga(raiz: Path) -> Path:
    (raiz / ".deepseek_ui").mkdir(parents=True)
    (raiz / "main.py").write_text("")
    (raiz / ".workspace.json").write_text('{"tema": "papel"}')
    (raiz / ".deepseek_ui" / "remote_token").write_text("tok-antigo")
    (raiz / "chrome_profile" / "Default").mkdir(parents=True)
    (raiz / "chrome_profile" / "Default" / "Cookies").write_text("login")
    return raiz


@pytest.fixture
def instalado(qt_app, tmp_path, monkeypatch):
    dados = tmp_path / "dados"
    casa = tmp_path / "casa"
    (casa / "Documents").mkdir(parents=True)
    monkeypatch.setenv("DEEPSEEK_UI_DADOS", str(dados))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", ["DeepSeekUI.exe"])
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: casa))
    return dados, casa


def _clicar(texto_botao: str):
    """Clica no botão do diálogo modal assim que ele abrir."""
    def tentar():
        caixa = QApplication.activeModalWidget()
        if not isinstance(caixa, QMessageBox):
            QTimer.singleShot(50, tentar)
            return
        for botao in caixa.buttons():
            if botao.text().startswith(texto_botao):
                botao.click()
                return
        raise AssertionError([b.text() for b in caixa.buttons()])
    QTimer.singleShot(50, tentar)


def test_traz_login_da_copia_sugerida(instalado):
    dados, casa = instalado
    copia = _copia_antiga(casa / "Documents" / "deepseek_ui")
    _clicar("Trazer desta pasta")
    main._oferecer_importacao()
    assert (dados / "chrome_profile" / "Default" / "Cookies").read_text() == "login"
    assert (dados / "remote_token").read_text() == "tok-antigo"
    assert (dados / "workspace.json").exists()
    assert (dados / "primeira_execucao.ok").exists()
    assert (copia / ".workspace.json").exists(), "a cópia antiga não é tocada"


def test_comecar_do_zero_nao_importa(instalado):
    dados, casa = instalado
    _copia_antiga(casa / "Documents" / "deepseek_ui")
    _clicar("Começar do zero")
    main._oferecer_importacao()
    assert not (dados / "chrome_profile").exists()
    assert (dados / "primeira_execucao.ok").exists()


def test_sem_copia_oferece_so_escolher_ou_zero(instalado):
    dados, _ = instalado
    vistos = {}

    def olhar():
        caixa = QApplication.activeModalWidget()
        if not isinstance(caixa, QMessageBox):
            QTimer.singleShot(50, olhar)
            return
        vistos["botoes"] = [b.text() for b in caixa.buttons()]
        vistos["icone"] = caixa.icon()
        for botao in caixa.buttons():
            if botao.text().startswith("Começar do zero"):
                botao.click()

    QTimer.singleShot(50, olhar)
    main._oferecer_importacao()
    assert not any(t.startswith("Trazer") for t in vistos["botoes"]), vistos
    assert vistos["icone"] == QMessageBox.Icon.Question


def test_segunda_execucao_nao_pergunta(instalado):
    dados, _ = instalado
    dados.mkdir(parents=True, exist_ok=True)
    (dados / "primeira_execucao.ok").write_text("1.0")
    QTimer.singleShot(1000, lambda: (_ for _ in ()).throw(
        AssertionError("não deveria abrir diálogo"))
        if QApplication.activeModalWidget() else None)
    main._oferecer_importacao()  # volta na hora, sem diálogo
    assert QApplication.activeModalWidget() is None


def test_codigo_fonte_nunca_pergunta(qt_app, monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("DEEPSEEK_UI_DADOS", str(tmp_path))
    main._oferecer_importacao()
    assert not (tmp_path / "primeira_execucao.ok").exists()
    assert not caminhos.empacotado()
