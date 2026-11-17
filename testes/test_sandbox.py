"""Testa o Sandbox contra caminhos maliciosos de verdade, no disco."""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.sandbox import Sandbox, SandboxError

base = Path(tempfile.mkdtemp(prefix="sbx_"))
root = base / "projeto"
fora = base / "fora"
(root / "src").mkdir(parents=True)
fora.mkdir()
(root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
(fora / "segredo.txt").write_text("SENHA", encoding="utf-8")

sb = Sandbox(root)
print("raiz:", sb.root)

ok = fail = 0

def deve_passar(rel):
    global ok, fail
    try:
        p = sb.resolve(rel)
        print(f"  PASSOU  {rel!r:45} -> {sb.relative(p)}")
        ok += 1
    except SandboxError as e:
        print(f"  ERRO!   {rel!r:45} recusou indevidamente: {e}")
        fail += 1

def deve_recusar(rel, motivo):
    global ok, fail
    try:
        p = sb.resolve(rel)
        print(f"  FUROU!  {rel!r:45} ({motivo}) -> {p}")
        fail += 1
    except SandboxError as e:
        print(f"  barrou  {rel!r:45} ({motivo}): {str(e)[:60]}")
        ok += 1

print("\n-- caminhos legitimos (devem passar) --")
for r in ["src/app.py", "novo.txt", "a/b/c/d.py", "src\\win.py", "./src/app.py",
          ".gitignore", "pasta/.env", "arquivo.tar.gz"]:
    deve_passar(r)

print("\n-- travessia (devem ser recusados) --")
for r, m in [("../fora/segredo.txt", "..'"), ("../../etc/passwd", "..x2"),
             ("src/../../fora/x.txt", ".. no meio"), ("..", "so .."),
             ("src/../..", "termina fora")]:
    deve_recusar(r, m)

print("\n-- absoluto / unidade / rede --")
for r, m in [("C:/Windows/System32/x.dll", "unidade"), ("C:x.txt", "drive-relativo"),
             ("/etc/passwd", "raiz unix"), ("//servidor/share/x", "UNC"),
             ("\\\\servidor\\share\\x", "UNC barra invertida"),
             (str(fora / "segredo.txt"), "absoluto real")]:
    deve_recusar(r, m)

print("\n-- truques do Windows --")
for r, m in [("CON", "reservado"), ("nul.txt", "reservado com extensao"),
             ("COM1.log", "reservado"), ("src/PRN.py", "reservado em subpasta"),
             ("nota.txt:oculto", "ADS"), ("arq ", "espaco no fim"),
             ("arq.", "ponto no fim"), ("", "vazio"), ("   ", "so espaco")]:
    deve_recusar(r, m)

print("\n-- byte nulo --")
deve_recusar("a\x00b.txt", "NUL")

print("\n-- symlink apontando para fora --")
try:
    os.symlink(fora, root / "atalho", target_is_directory=True)
    criou = True
except OSError as e:
    criou = False
    print(f"  (sem permissao para criar symlink neste Windows: {e.__class__.__name__}) - pulando")
if criou:
    deve_recusar("atalho/segredo.txt", "symlink de pasta para fora")
    deve_recusar("atalho", "o proprio symlink")

print("\n-- junction (mklink /J, nao precisa de admin) --")
import subprocess
jdir = root / "junc"
r = subprocess.run(f'mklink /J "{jdir}" "{fora}"', shell=True, capture_output=True, text=True)
if r.returncode == 0:
    deve_recusar("junc/segredo.txt", "junction para fora")
else:
    print("  (mklink falhou:", r.stderr.strip()[:60], ") - pulando")

print("\n-- teto de tamanho --")
try:
    sb.check_size("a" * 3_000_000, "grande.txt")
    print("  FUROU! aceitou arquivo de 3MB"); fail += 1
except SandboxError as e:
    print(f"  barrou  arquivo de 3MB: {str(e)[:60]}"); ok += 1

print("\n-- raiz inexistente --")
try:
    Sandbox(base / "nao_existe")
    print("  FUROU! aceitou raiz inexistente"); fail += 1
except SandboxError as e:
    print(f"  barrou  raiz inexistente: {str(e)[:50]}"); ok += 1

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
