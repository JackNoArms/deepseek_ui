"""Controle remoto do Tailscale Serve: achar o binário, ler status, elevar.

Este módulo não importa Qt — os helpers dão para testar sem QApplication. O
diálogo que consome isso vive em `src/remote_view.py`.

Sobre elevação: `tailscale serve` no Windows exige Administrador. Como o app
roda como usuário comum, configurar o serve significa abrir o `.bat` (ou o
próprio `tailscale.exe`) com o verbo `runas` do ShellExecuteW, o que dispara o
UAC. Isso é irreversível de dentro do app — só o usuário aceita. Por isso
`habilitar_serve` devolve só "lançou ou não"; o estado real é lido depois por
`ler_serve_status`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

# Locais onde o instalador do Tailscale no Windows põe o executável. O `which`
# cobre o caso de PATH configurado; o caminho absoluto cobre o caso em que o
# app foi aberto antes do PATH atualizar (aconteceu no primeiro uso).
CAMINHOS_COMUNS = (
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
)

_URL_SERVE = re.compile(r"^(https://\S+)", re.MULTILINE)


def encontrar_tailscale() -> str | None:
    """Caminho do executável do Tailscale, ou None se não estiver instalado."""
    for caminho in CAMINHOS_COMUNS:
        if os.path.isfile(caminho):
            return caminho
    return shutil.which("tailscale")


def _rodar(ts: str, *args: str, timeout: int = 15):
    try:
        return subprocess.run(
            [ts, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None


def ler_serve_status(ts: str) -> tuple[bool, str]:
    """(ativo, url_sem_barra_final). URL é vazia quando não configurado.

    Reconhece as duas mensagens que o `tailscale serve status` devolve quando
    não há configuração: `No serve config` (feature habilitada, nada apontado)
    e `Serve is not enabled on your tailnet` (feature ainda não liberada no
    painel do Tailscale). Ambas viram `(False, "")`.
    """
    proc = _rodar(ts, "serve", "status")
    if proc is None or proc.returncode != 0:
        return False, ""
    texto = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if "not enabled" in texto.lower() or "No serve config" in texto:
        return False, ""
    m = _URL_SERVE.search(texto)
    if not m:
        return False, ""
    return True, m.group(1).rstrip("/")


def url_com_token(url: str, token: str) -> str:
    """Junta URL do serve com o token do painel. Vazio se faltar peça."""
    if not url or not token:
        return ""
    return f"{url.rstrip('/')}/?token={token}"


def ler_token(caminho: str | Path) -> str:
    """Lê o token gravado pelo `RemoteServer`. Vazio se o arquivo não existe."""
    try:
        return Path(caminho).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def habilitar_serve(ts: str, porta: int, bat: str | Path | None = None) -> bool:
    """Lança a configuração do serve com UAC elevado.

    Se `bat` for passado e existir, executa o `.bat` (que já imprime a URL e o
    token prontos, e mostra tudo na tela). Senão, roda o `tailscale.exe serve
    --bg` direto. Em ambos os casos, o verbo `runas` abre o UAC. Devolve True
    se o ShellExecuteW foi aceito (>32); a confirmação real vem de
    `ler_serve_status` no próximo poll.
    """
    import ctypes
    if bat is not None and Path(bat).is_file():
        arquivo, params = "cmd.exe", f'/c "{bat}"'
    else:
        arquivo, params = ts, f"serve --bg http://127.0.0.1:{porta}"
    resultado = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", arquivo, params, None, 1)
    return resultado > 32
