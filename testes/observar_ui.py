"""Watchdog visual da UI durante testes manuais ou automatizados.

Uso:
    python testes/observar_ui.py --segundos 180 --intervalo 5

As capturas ficam em diagnosticos_ui/ e o estado das janelas/processos em
watchdog.jsonl. O watchdog nao envia mensagens nem clica na aplicacao.
"""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pyautogui

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "diagnosticos_ui"


def processos_controlados():
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | "
         "Where-Object { $_.CommandLine -match 'deepseek_ui\\\\chrome_profile|main.py' } | "
         "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    texto = resultado.stdout.strip()
    if not texto:
        return []
    dados = json.loads(texto)
    return dados if isinstance(dados, list) else [dados]


def janela_ui():
    janelas = [janela for janela in pyautogui.getAllWindows()
               if janela.title == "DeepSeek UI"]
    if not janelas:
        return None
    return janelas[0]


def estado(janela):
    if janela is None:
        return {"janela": False}
    return {
        "janela": True,
        "left": janela.left,
        "top": janela.top,
        "width": janela.width,
        "height": janela.height,
        "minimizada": janela.isMinimized,
        "maximizada": janela.isMaximized,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--segundos", type=float, default=180)
    parser.add_argument("--intervalo", type=float, default=5)
    args = parser.parse_args()

    SAIDA.mkdir(exist_ok=True)
    log = SAIDA / "watchdog.jsonl"
    fim = time.monotonic() + args.segundos
    rodada = 0

    while time.monotonic() < fim:
        janela = janela_ui()
        if janela is not None and (janela.isMinimized or janela.left < -1000):
            janela.restore()
            janela.activate()
        registro = {
            "hora": datetime.now().isoformat(timespec="seconds"),
            "rodada": rodada,
            "estado": estado(janela_ui()),
            "processos": processos_controlados(),
        }
        pyautogui.screenshot(str(SAIDA / f"tela_{rodada:04d}.png"))
        with log.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
        print(json.dumps(registro, ensure_ascii=False), flush=True)
        rodada += 1
        time.sleep(max(0.5, args.intervalo))


if __name__ == "__main__":
    main()
