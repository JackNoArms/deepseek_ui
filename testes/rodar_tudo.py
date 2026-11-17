"""Roda toda a bateria de testes no formato script standalone e resume.

Existem dois estilos de teste em `testes/`:

- **Scripts standalone** (`test_parser.py`, `test_runner.py`, ...): montam o
  próprio `ok/fail`, imprimem e terminam com `sys.exit`. Rodam por este
  orquestrador ou direto.
- **Testes pytest de verdade** (`test_remote.py`, `test_push.py`,
  `test_multiplas_instancias.py`, `test_remote_ui.py`, `test_remote_handlers.py`,
  `test_remote_ponte.py`, `test_skills*.py`): usam `test_*` e asserções. Devem
  rodar por `pytest testes/`, não por aqui.

A lista `PULAR` mantém os dois mundos separados, em espelho ao
`collect_ignore` do `conftest.py`. Ao criar um teste novo, escolha um estilo e
atualize o arquivo do outro lado se necessário.
"""
import pathlib
import subprocess
import sys

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent

# Arquivos que NÃO são scripts standalone; o pytest é quem os roda.
PULAR = {
    "test_wrapper_chrome_real.py",
    "test_primeira_execucao.py",
    "test_caminhos.py",
    "test_fila_decisao_remota.py",
    "test_multiplas_instancias.py",
    "test_push.py",
    "test_remote.py",
    "test_remote_handlers.py",
    "test_remote_ponte.py",
    "test_remote_ui.py",
    "test_skills.py",
    "test_skills_agent.py",
    "test_skills_bootstrap.py",
    "test_skills_migration.py",
    "test_skills_prompt.py",
    "test_skills_view.py",
}

testes = sorted(
    p for p in AQUI.glob("test_*.py") if p.name not in PULAR)
total_ok = total_falhas = 0
quebrados = []

for teste in testes:
    proc = subprocess.run([sys.executable, str(teste)], cwd=str(RAIZ),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env={**__import__("os").environ,
                                                 "PYTHONIOENCODING": "utf-8"})
    ultima = [l for l in (proc.stdout or "").strip().split("\n") if l.startswith("==>")]
    resumo = ultima[-1] if ultima else "(sem resumo)"
    print(f"{teste.name:24} {resumo}")
    if ultima:
        partes = resumo.replace("==>", "").split(",")
        total_ok += int(partes[0].split()[0])
        total_falhas += int(partes[1].split()[0])
    if proc.returncode != 0:
        quebrados.append(teste.name)
        if not ultima:
            print((proc.stdout or "")[-1500:], (proc.stderr or "")[-1500:])

print(f"\n{'=' * 50}\nTOTAL: {total_ok} corretos, {total_falhas} falhas")
if PULAR:
    print("fora daqui (pytest cuida):", ", ".join(sorted(PULAR)))
if quebrados:
    print("com falha:", ", ".join(quebrados))
sys.exit(1 if quebrados else 0)
