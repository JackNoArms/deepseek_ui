"""Testes dos helpers de controle remoto (sem Qt).

`subprocess.run` e `ctypes` são mockados: o que está sob teste é a nossa
lógica de decisão (quando o serve está ativo, como montar a URL, como o
comando de elevação é chamado), não o comportamento do Tailscale real.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src import remote_ui


def _run_falso(stdout="", stderr="", returncode=0):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------- encontrar_tailscale ----------------


def test_encontra_no_caminho_absoluto(tmp_path, monkeypatch):
    exe = tmp_path / "tailscale.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(remote_ui, "CAMINHOS_COMUNS", (str(exe),))
    monkeypatch.setattr(remote_ui.shutil, "which", lambda _: None)
    assert remote_ui.encontrar_tailscale() == str(exe)


def test_recorre_ao_which_quando_nao_esta_nos_caminhos(monkeypatch):
    monkeypatch.setattr(remote_ui, "CAMINHOS_COMUNS", ())
    monkeypatch.setattr(remote_ui.shutil, "which", lambda _: r"C:\x\tailscale.exe")
    assert remote_ui.encontrar_tailscale() == r"C:\x\tailscale.exe"


def test_devolve_none_quando_nao_instalado(monkeypatch):
    monkeypatch.setattr(remote_ui, "CAMINHOS_COMUNS", ())
    monkeypatch.setattr(remote_ui.shutil, "which", lambda _: None)
    assert remote_ui.encontrar_tailscale() is None


# ---------------- ler_serve_status ----------------


def test_serve_sem_configuracao(monkeypatch):
    monkeypatch.setattr(remote_ui, "_rodar", lambda *a, **k: _run_falso(
        stdout="No serve config\n"))
    ativo, url = remote_ui.ler_serve_status("ts")
    assert ativo is False and url == ""


def test_serve_nao_habilitado_na_tailnet(monkeypatch):
    monkeypatch.setattr(remote_ui, "_rodar", lambda *a, **k: _run_falso(
        stderr="Serve is not enabled on your tailnet.\n"))
    ativo, url = remote_ui.ler_serve_status("ts")
    assert ativo is False and url == ""


def test_serve_ativo_com_url(monkeypatch):
    texto = (
        "https://desktop-1qp4t30.taildc4d5d.ts.net (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8765\n")
    monkeypatch.setattr(remote_ui, "_rodar", lambda *a, **k: _run_falso(
        stdout=texto))
    ativo, url = remote_ui.ler_serve_status("ts")
    assert ativo is True
    assert url == "https://desktop-1qp4t30.taildc4d5d.ts.net"


def test_serve_com_falha_de_subprocess(monkeypatch):
    def _bum(*a, **k):
        raise OSError("sem tailscale")
    monkeypatch.setattr(remote_ui.subprocess, "run", _bum)
    ativo, url = remote_ui.ler_serve_status("ts")
    assert ativo is False and url == ""


# ---------------- url_com_token ----------------


def test_url_com_token_normal():
    assert remote_ui.url_com_token(
        "https://x.ts.net", "abc") == "https://x.ts.net/?token=abc"


def test_url_com_token_aceita_barra_final():
    assert remote_ui.url_com_token(
        "https://x.ts.net/", "abc") == "https://x.ts.net/?token=abc"


def test_url_com_token_vazia_sem_peca():
    assert remote_ui.url_com_token("", "abc") == ""
    assert remote_ui.url_com_token("https://x", "") == ""


# ---------------- ler_token ----------------


def test_ler_token(tmp_path):
    p = tmp_path / "remote_token"
    p.write_text("  JfbevgG2A8MI  \n", encoding="utf-8")
    assert remote_ui.ler_token(p) == "JfbevgG2A8MI"


def test_ler_token_arquivo_ausente(tmp_path):
    assert remote_ui.ler_token(tmp_path / "nao-existe") == ""


# ---------------- habilitar_serve ----------------


def test_habilitar_usa_bat_quando_existe(tmp_path):
    bat = tmp_path / "configurar_tailscale.bat"
    bat.write_text("rem vazio", encoding="utf-8")
    chamadas = []

    def fake_shell_execute(hwnd, op, arquivo, params, cwd, show):
        chamadas.append((op, arquivo, params))
        return 42  # >32 = sucesso

    with patch("ctypes.windll.shell32.ShellExecuteW", side_effect=fake_shell_execute):
        ok = remote_ui.habilitar_serve("ts.exe", 8765, bat)
    assert ok is True
    assert len(chamadas) == 1
    op, arquivo, params = chamadas[0]
    assert op == "runas"
    assert arquivo == "cmd.exe"
    assert str(bat) in params


def test_habilitar_sem_bat_chama_tailscale_direto(tmp_path):
    chamadas = []

    def fake_shell_execute(hwnd, op, arquivo, params, cwd, show):
        chamadas.append((op, arquivo, params))
        return 42

    with patch("ctypes.windll.shell32.ShellExecuteW", side_effect=fake_shell_execute):
        ok = remote_ui.habilitar_serve("C:/x/tailscale.exe", 8765, None)
    assert ok is True
    op, arquivo, params = chamadas[0]
    assert op == "runas"
    assert arquivo == "C:/x/tailscale.exe"
    assert "serve --bg http://127.0.0.1:8765" in params


def test_habilitar_devolve_false_quando_uac_recusado(tmp_path):
    with patch("ctypes.windll.shell32.ShellExecuteW", return_value=5):
        ok = remote_ui.habilitar_serve("ts.exe", 8765, None)
    assert ok is False
