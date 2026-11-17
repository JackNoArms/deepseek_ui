"""Comandos do agente rodam no shell, sem travas (ADR-022)."""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src import runner
from src.runner import ComandoRecusado, destrutivo, encerrar, rodar

ok = fail = 0
PY = f'"{sys.executable}"'


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


with tempfile.TemporaryDirectory(prefix="runner_") as temporario:
    raiz = Path(temporario) / "projeto"
    raiz.mkdir()
    fora = Path(temporario)

    print("-- 1. shell completo --")
    s = rodar("echo abc | findstr abc", raiz)
    checa("pipe funciona", s.ok and s.texto == "abc", s.resumo())
    s = rodar("echo gravado > saida.txt && type saida.txt", raiz)
    checa("redirecionamento e && funcionam",
          s.ok and "gravado" in s.texto and (raiz / "saida.txt").exists(), s.resumo())
    s = rodar("cmd /c exit 3 || echo recuperou", raiz)
    checa("|| roda o alternativo", s.ok and "recuperou" in s.texto, s.resumo())
    s = rodar("echo um & echo dois", raiz)
    checa("& encadeia", [l.strip() for l in s.texto.splitlines()] == ["um", "dois"], s.texto)
    s = rodar("cd .. && cd", raiz)
    checa("cd sai da pasta do projeto", s.ok and Path(s.texto) == fora.resolve(), s.texto)
    s = rodar("git --version", raiz)
    checa("programa fora da antiga allowlist roda",
          s.ok and "git version" in s.texto, s.resumo())
    s = rodar(f"{PY} -c \"print('olá')\"", raiz)
    checa("saída UTF-8 de programa preservada", "olá" in s.texto, repr(s.texto))
    s = rodar("echo olá", raiz)
    checa("saída do cmd (página de código do console) decodificada",
          "olá" in s.texto, repr(s.texto))

    print("\n-- 2. várias linhas --")
    s = rodar("echo primeira\ncd ..\ncd", raiz)
    checa("várias linhas rodam como script, cd vale entre linhas",
          s.ok and s.texto.splitlines() == ["primeira", str(fora.resolve())], s.texto)
    restos = list(Path(tempfile.gettempdir()).glob("deepseek_ui_*.cmd"))
    checa("script temporário apagado", not restos, restos)

    print("\n-- 3. timeout padrão e encerrabilidade --")
    checa("timeout padrão de 5 min", runner.TIMEOUT_PADRAO == 300.0)
    checa("limite de silêncio padrão de 2 min",
          runner.LIMITE_SEM_SAIDA_PADRAO == 120.0)
    inicio = time.monotonic()
    s = rodar(f"{PY} -c \"input()\"", raiz)
    checa("stdin fechado: comando interativo não trava",
          not s.ok and time.monotonic() - inicio < 15, (s.codigo, s.texto[-80:]))
    caixa = {}
    inicio = time.monotonic()
    t = threading.Thread(target=lambda: caixa.update(s=rodar(
        f"{PY} -c \"import time; time.sleep(60)\"", raiz,
        ao_iniciar=lambda p: caixa.update(p=p))))
    t.start()
    while "p" not in caixa and time.monotonic() - inicio < 10:
        time.sleep(0.05)
    time.sleep(0.5)
    encerrar(caixa.get("p"))
    t.join(20)
    s = caixa.get("s")
    checa("encerrar derruba o comando na hora",
          s is not None and s.interrompido and time.monotonic() - inicio < 15,
          (s and s.resumo(), time.monotonic() - inicio))
    checa("resumo avisa que foi interrompido",
          s is not None and "interrompido por você" in s.resumo())
    checa("motivo=interrompido",
          s is not None and s.motivo == "interrompido",
          (s and s.motivo))
    s = rodar(f"{PY} -c \"import time; time.sleep(30)\"", raiz, timeout=1)
    checa("timeout explícito ainda funciona", s.estourou_tempo and not s.ok, s.resumo())
    checa("motivo=timeout", s.motivo == "timeout", s.motivo)
    checa("segundos é preenchido", s.segundos >= 1, s.segundos)

    print("\n-- 3b. streaming com ao_progredir --")
    progressos = []
    tempos = []
    def progresso(texto, seg):
        progressos.append(texto)
        tempos.append(seg)
    s = rodar(
        f'{PY} -c "import sys,time;print(\'a\',flush=True);time.sleep(0.5);print(\'b\',flush=True)"',
        raiz, ao_progredir=progresso)
    checa("ao_progredir entrega saída ao vivo (a e b)",
          "a" in "".join(progressos) and "b" in "".join(progressos),
          progressos)
    checa("ao_progredir e Saida.texto batem",
          s.ok and "a" in s.texto and "b" in s.texto, s.resumo())
    checa("ao_progredir recebe pelo menos 2 chamadas (não só no fim)",
          len(progressos) >= 2, len(progressos))

    progressos.clear()
    tempos.clear()
    inicio = time.monotonic()
    s = rodar(f"{PY} -c \"import time; time.sleep(2)\"", raiz,
              limite_sem_saida=0.5, ao_progredir=progresso)
    checa("aviso de silêncio dispara sem matar",
          any(seg >= 0.5 for seg in tempos) and s.ok,
          (tempos, s.resumo()))
    checa("aviso de silêncio só uma vez por período",
          sum(1 for t in tempos if t >= 0.5) == 1, tempos)

    # Caso real de 2026-10-20: `adb devices` sobe o servidor do adb em segundo
    # plano; ele herdava a saída do comando e o app esperou 40 min o cano
    # fechar. `start /b` reproduz: o filho fica vivo com os mesmos handles.
    # Pasta do sistema: o processo de fundo segura a pasta em que roda.
    fundo = Path(tempfile.gettempdir())
    inicio = time.monotonic()
    s = rodar(f'start "" /b {PY} -c "import time; time.sleep(25)" & echo pronto', fundo)
    duracao = time.monotonic() - inicio
    checa("processo em segundo plano não segura o comando (servidor do adb)",
          duracao < 8 and s.ok and "pronto" in s.texto, (round(duracao, 1), s.resumo()))
    inicio = time.monotonic()
    s = rodar(f'start "" /b {PY} -c "import time; time.sleep(25)"\necho linha2', fundo)
    checa("idem em várias linhas (script .cmd)",
          time.monotonic() - inicio < 8 and "linha2" in s.texto,
          (round(time.monotonic() - inicio, 1), s.resumo()))

    print("\n-- 4. execução sem janela e erros --")
    capturado = {}
    original = runner.subprocess.Popen

    def espia(*args, **kwargs):
        capturado.update(kwargs)
        return original(*args, **kwargs)

    with patch("src.runner.subprocess.Popen", side_effect=espia):
        rodar("echo x", raiz)
    checa("sem janela de console",
          capturado.get("creationflags") == getattr(runner.subprocess, "CREATE_NO_WINDOW", 0))
    checa("começa na raiz do projeto", Path(capturado.get("cwd")) == raiz)
    s = rodar("comando_que_nao_existe_123", raiz)
    checa("programa inexistente vira saída com erro, não exceção",
          not s.ok and "comando_que_nao_existe_123" in s.texto, s.resumo())
    for vazio in ("", "   "):
        try:
            rodar(vazio, raiz)
            checa(f"comando vazio {vazio!r} recusado", False)
        except ComandoRecusado:
            checa(f"comando vazio {vazio!r} recusado", True)
    try:
        rodar("echo x", raiz / "nao-existe")
        checa("pasta inexistente recusada", False)
    except ComandoRecusado:
        checa("pasta inexistente recusada", True)

    print("\n-- 5. aviso de destrutivo (só informativo) --")
    for comando in ("rm -rf /", "del /s /q build", "git push --force",
                    "npm publish", "Remove-Item x -Recurse", "pip uninstall x"):
        checa(f"⚠ {comando}", destrutivo(comando))
    for comando in ("python --version", "pytest -q", "git status"):
        checa(f"sem ⚠ {comando}", not destrutivo(comando))

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
