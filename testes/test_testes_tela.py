"""Testes de tela pelo runtime Playwright do computador (ADR-026)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src import testes_tela
from src.prompts import montar

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


print("-- 1. pasta Documentos do usuário atual --")
docs = testes_tela.pasta_documentos()
checa("Documentos existe", docs.is_dir(), docs)
checa("não é a raiz do disco", len(docs.parts) > 1, docs)

with tempfile.TemporaryDirectory(prefix="tela_") as tmp:
    rt = Path(tmp) / "Playwright-Lab"
    rt.mkdir()
    instalar = Path(tmp) / "instalar.ps1"
    instalar.write_text("# modelo", encoding="utf-8")

    print("-- 2. regras conforme o que existe no computador --")
    regras = testes_tela.regras(runtime=rt, instalador=None)
    checa("cita o runtime pelo caminho real", rt.as_posix() in regras, regras[:200])
    for termo in ("Headless sempre", "mapear.cjs", "runtime.cjs", "passoAPasso",
                  "pp.concluir", "headed: true", "Só dados fictícios"):
        checa(f"regra tem: {termo}", termo in regras)
    checa("chaves do JS não ficaram duplicadas", "{{" not in regras and "{ abrir, passoAPasso }" in regras)
    so_instalador = testes_tela.regras(runtime=None, instalador=instalar)
    checa("sem runtime, ensina a criar", "instalar.ps1" in so_instalador
          and "ainda não tem" in so_instalador, so_instalador)
    checa("sem runtime nem instalador, nada", testes_tela.regras(runtime=None, instalador=None) == "")

    print("-- 3. detecção pela variável e pelo arquivo runtime.cjs --")
    antes = os.environ.get("DEEPSEEK_UI_PLAYWRIGHT")
    os.environ["DEEPSEEK_UI_PLAYWRIGHT"] = str(rt)
    try:
        checa("pasta sem runtime.cjs não conta", testes_tela.runtime_playwright() is None)
        (rt / "runtime.cjs").write_text("module.exports = {};", encoding="utf-8")
        checa("pasta com runtime.cjs é achada", testes_tela.runtime_playwright() == rt,
              testes_tela.runtime_playwright())

        print("-- 4. entra no prompt só no modo Agente, na primeira mensagem --")
        com = montar("testar o cadastro", primeira=True, agente=True)
        checa("agente + primeira: bloco presente", "TESTES DE TELA" in com and rt.as_posix() in com)
        sem_agente = montar("testar o cadastro", primeira=True, agente=False)
        checa("sem agente: bloco ausente", "TESTES DE TELA" not in sem_agente)
        seguinte = montar("continua", primeira=False, agente=True)
        checa("mensagens seguintes: bloco ausente", "TESTES DE TELA" not in seguinte)
        json_agente = montar("testar", primeira=True, agente=True, formato="json")
        checa("protocolo JSON também recebe", "TESTES DE TELA" in json_agente)
    finally:
        if antes is None:
            os.environ.pop("DEEPSEEK_UI_PLAYWRIGHT", None)
        else:
            os.environ["DEEPSEEK_UI_PLAYWRIGHT"] = antes

print("-- 5. runtime real deste computador, se existir --")
real = testes_tela.runtime_playwright()
if real is None:
    print("  (sem runtime real neste computador; pulado)")
else:
    checa("runtime real tem mapear.cjs", (real / "mapear.cjs").is_file(), real)

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
