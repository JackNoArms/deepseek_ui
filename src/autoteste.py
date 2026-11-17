"""Autoteste do app empacotado (`DeepSeekUI.exe --verificar`).

Prova, de dentro do pacote, o que o PyInstaller pode ter deixado para trás:
recursos só-leitura, plugin de janela do Qt, shell do agente, painel do celular
servindo os arquivos e o Chrome subindo pelo Selenium (chromedriver baixado
pelo `selenium-manager.exe`). Cada item vira uma linha no log; o processo sai
com o número de falhas — 0 é tudo certo.
"""

from __future__ import annotations

import http.client
import shutil
import subprocess
import tempfile
from pathlib import Path

from src import caminhos

RECURSOS = (
    ("config.json",),
    ("configurar_tailscale.bat",),
    ("assets", "favicon.png"),
    ("assets", "skills_default"),
    ("src", "remote_panel.html"),
    ("src", "remote_panel.css"),
    ("src", "remote_panel.js"),
)


def _recursos() -> tuple[bool, str]:
    faltando = ["/".join(p) for p in RECURSOS if not caminhos.recurso(*p).exists()]
    return not faltando, ("todos presentes" if not faltando
                          else "faltando: " + ", ".join(faltando))


def _janela(app) -> tuple[bool, str]:
    plataforma = app.platformName()
    return plataforma in ("windows", "offscreen", "xcb", "cocoa", "wayland"), plataforma


def _shell() -> tuple[bool, str]:
    import time

    from src.runner import rodar
    saida = rodar("echo shell-livre | findstr livre", caminhos.pasta_dados())
    pipe_ok = saida.ok and saida.texto.strip() == "shell-livre"
    # Processo deixado em segundo plano (como o servidor do adb) não pode
    # segurar o comando — o app ficou 40 min parado assim em 2026-10-20.
    inicio = time.monotonic()
    fundo = rodar('start "" /b ping -n 20 127.0.0.1 >nul & echo fundo-ok',
                  tempfile.gettempdir())
    segundos = time.monotonic() - inicio
    fundo_ok = fundo.ok and "fundo-ok" in fundo.texto and segundos < 8
    return (pipe_ok and fundo_ok,
            f"pipe {'ok' if pipe_ok else 'FALHOU'}; processo em segundo plano "
            f"liberou o comando em {segundos:.1f} s")


def _painel() -> tuple[bool, str]:
    from src.remote import RemoteServer
    pasta = Path(tempfile.mkdtemp(prefix="dsui_autoteste_"))
    servidor = RemoteServer(porta=0, token_path=str(pasta / "token"))
    try:
        servidor.start()
        estados = []
        for rota in ("/remote_panel.css", "/remote_panel.js", "/remote_theme.css"):
            con = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=5)
            con.request("GET", rota)
            resposta = con.getresponse()
            corpo = resposta.read()
            con.close()
            estados.append((rota, resposta.status, len(corpo)))
        ok = all(status == 200 and tamanho > 100 for _, status, tamanho in estados)
        return ok, ", ".join(f"{r} {s} ({t} B)" for r, s, t in estados)
    finally:
        servidor.stop()
        shutil.rmtree(pasta, ignore_errors=True)


def _chrome() -> tuple[bool, str]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    perfil = Path(tempfile.mkdtemp(prefix="dsui_autoteste_chrome_"))
    opcoes = Options()
    opcoes.add_argument("--headless=new")
    opcoes.add_argument(f"--user-data-dir={perfil}")
    opcoes.add_argument("--no-first-run")
    opcoes.add_argument("--no-default-browser-check")
    servico = Service(popen_kw={
        "creation_flags": getattr(subprocess, "CREATE_NO_WINDOW", 0)})
    driver = None
    try:
        driver = webdriver.Chrome(options=opcoes, service=servico)
        driver.get("data:text/html,<title>deepseek-ui-ok</title>")
        titulo = driver.title
        versao = driver.capabilities.get("browserVersion", "?")
        enviado_ok, detalhe_envio = _envio_com_crlf(driver)
        return (titulo == "deepseek-ui-ok" and enviado_ok,
                f"Chrome {versao}, título {titulo!r}; {detalhe_envio}")
    finally:
        if driver is not None:
            driver.quit()
        shutil.rmtree(perfil, ignore_errors=True)


_PAGINA_ENVIO = (
    "<!doctype html><meta charset='utf-8'><textarea id='e'></textarea>"
    "<button class='send'>enviar</button><script>window.enviadas=[];"
    "const t=document.getElementById('e');t.addEventListener('keydown',ev=>{"
    "if(ev.key==='Enter'&&!ev.shiftKey){ev.preventDefault();"
    "window.enviadas.push(t.value);t.value='';}});</script>")


def _envio_com_crlf(driver) -> tuple[bool, str]:
    """Envio pelo `_submit_message` com quebras do Windows (bug de 2026-10-20)."""
    import threading
    from urllib.parse import quote

    from src.wrapper import DeepSeekWrapper

    wrapper = DeepSeekWrapper.__new__(DeepSeekWrapper)
    wrapper.driver = driver
    wrapper._lock = threading.RLock()
    wrapper.config = {"selectors": {"css": {"send_button": "button.send"}},
                      "timeouts": {"element_wait": 2}}
    wrapper._visible_user_messages = lambda: None
    texto = "$ dir\r\n" + "linha de saída de comando\r\n" * 200 + "fim"
    driver.get("data:text/html;charset=utf-8," + quote(_PAGINA_ENVIO))
    wrapper._submit_message(driver.find_element("id", "e"), texto)
    enviadas = driver.execute_script("return window.enviadas") or []
    ok = enviadas == [texto.replace("\r\n", "\n")]
    return ok, f"envio com CRLF de {len(texto)} caracteres {'ok' if ok else 'FALHOU'}"


def rodar_autoteste(app, com_chrome: bool = True) -> int:
    """Roda os itens, escreve no log e devolve o número de falhas."""
    itens = [
        ("recursos do pacote", _recursos),
        ("plataforma da janela", lambda: _janela(app)),
        ("shell do agente", _shell),
        ("painel do celular", _painel),
    ]
    if com_chrome:
        itens.append(("Chrome pelo Selenium", _chrome))
    falhas = 0
    for nome, teste in itens:
        try:
            ok, detalhe = teste()
        except Exception as e:  # o autoteste nunca derruba o app
            ok, detalhe = False, f"{type(e).__name__}: {e}"
        falhas += not ok
        print(f"verificar: {'ok    ' if ok else 'FALHOU'} {nome} — {detalhe}")
    print(f"verificar: {'TUDO CERTO' if not falhas else f'{falhas} FALHA(S)'}")
    return falhas
