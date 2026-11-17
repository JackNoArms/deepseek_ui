"""Testa o executor contra disco real: valida, diff, aplica, backup."""
import shutil
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.executor import Executor, relatorio
from src.parser import parse
from src.project import Project

ok = fail = 0
F = "```"

def checa(nome, cond, extra=""):
    global ok, fail
    if cond:
        print(f"  ok      {nome}"); ok += 1
    else:
        print(f"  FALHOU  {nome} -> {extra}"); fail += 1

base = Path(tempfile.mkdtemp(prefix="exec_"))
(base / "src").mkdir()
(base / "src" / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8")
(base / "velho.txt").write_text("apagar isso", encoding="utf-8")
proj = Project(base)
ex = Executor(proj)

print("-- 1. criar arquivo novo --")
r = parse(f"{F}python\n# kitty: file=src/novo.py acao=criar\nprint(1)\n{F}")
planos = ex.preparar(r.acoes)
checa("1 plano", len(planos) == 1)
p = planos[0]
checa("nao existe ainda", not p.existe)
checa("aplicavel", p.aplicavel, p.erro)
checa("nada escrito ainda (preparar e so leitura)", not (base / "src" / "novo.py").exists())
res = ex.aplicar(planos)
checa("status aplicado", res[0].status == "aplicado", res[0].detalhe)
checa("arquivo no disco", (base / "src" / "novo.py").read_text(encoding="utf-8") == "print(1)",
      repr((base / "src" / "novo.py").read_text(encoding="utf-8")))

print("\n-- 2. modificar existente + diff --")
r = parse(f"{F}python\n# kitty: file=src/app.py acao=modificar\ndef a():\n    return 2\n{F}")
p = ex.preparar(r.acoes)[0]
checa("existe", p.existe)
checa("diff tem -return 1", "-    return 1" in p.diff, repr(p.diff))
checa("diff tem +return 2", "+    return 2" in p.diff, repr(p.diff))
checa("contagem +1 -1", (p.adicionadas, p.removidas) == (1, 1), (p.adicionadas, p.removidas))
ex.aplicar([p])
checa("conteudo trocado", (base / "src" / "app.py").read_text(encoding="utf-8") == "def a():\n    return 2",
      repr((base / "src" / "app.py").read_text(encoding="utf-8")))
bkp = list((base / ".deepseek_ui" / "backups").rglob("app.py"))
checa("backup do original existe", bkp and "return 1" in bkp[0].read_text(encoding="utf-8"),
      [str(b) for b in bkp])

print("\n-- 3. conteudo identico e ignorado --")
r = parse(f"{F}python\n# kitty: file=src/app.py acao=modificar\ndef a():\n    return 2\n{F}")
p = ex.preparar(r.acoes)[0]
checa("sem_efeito", p.sem_efeito, p.avisos)
res = ex.aplicar([p])
checa("status ignorado", res[0].status == "ignorado", res[0].status)

print("\n-- 4. caminho fora da raiz e recusado --")
r = parse(f"{F}python\n# kitty: file=../fora.py acao=criar\nx\n{F}")
p = ex.preparar(r.acoes)[0]
checa("tem erro", bool(p.erro), p.erro)
checa("nao aplicavel", not p.aplicavel)
res = ex.aplicar([p])
checa("status recusado", res[0].status == "recusado", res[0].status)
checa("nada criado fora", not (base.parent / "fora.py").exists())

print("\n-- 5. aviso de truncamento --")
(base / "grande.py").write_text("x = 1\n" * 200, encoding="utf-8")
proj2 = Project(base); ex2 = Executor(proj2)
r = parse(f"{F}python\n# kitty: file=grande.py acao=modificar\nx = 1\n{F}")
p = ex2.preparar(r.acoes)[0]
checa("avisa truncamento", any("truncada" in a for a in p.avisos), p.avisos)
checa("aviso não bloqueia decisão manual", p.aplicavel)
checa("suspeita de truncamento exige revisão manual",
      not p.aplicavel_automaticamente)
res = ex2.aplicar([p])
checa("plano selecionado pelo usuário pode ser aplicado",
      res[0].status == "aplicado"
      and (base / "grande.py").read_text(encoding="utf-8") == "x = 1")
backup_grande = list((base / ".deepseek_ui" / "backups").rglob("grande.py"))
checa("original truncado continua recuperável no backup",
      backup_grande
      and backup_grande[0].read_text(encoding="utf-8") == "x = 1\n" * 200)

print("\n-- 6. modificar arquivo inexistente avisa --")
r = parse(f"{F}python\n# kitty: file=nao_existe.py acao=modificar\nx\n{F}")
p = ex2.preparar(r.acoes)[0]
checa("avisa que nao existe", any("não existe" in a for a in p.avisos), p.avisos)
checa("mas deixa criar", p.aplicavel)

print("\n-- 7. criar por cima avisa --")
r = parse(f"{F}python\n# kitty: file=src/app.py acao=criar\nnovo\n{F}")
p = ex2.preparar(r.acoes)[0]
checa("avisa sobrescrita", any("substituído" in a for a in p.avisos), p.avisos)

print("\n-- 8. apagar move para backup --")
r = parse(f"{F}text\n# kitty: file=velho.txt acao=apagar\n{F}")
p = ex2.preparar(r.acoes)[0]
checa("aplicavel", p.aplicavel, p.erro)
res = ex2.aplicar([p])
checa("sumiu do projeto", not (base / "velho.txt").exists())
achados = list((base / ".deepseek_ui" / "backups").rglob("velho.txt"))
checa("recuperavel do backup", achados and achados[0].read_text(encoding="utf-8") == "apagar isso",
      [str(a) for a in achados])

print("\n-- 9. apagar inexistente nao quebra --")
r = parse(f"{F}text\n# kitty: file=fantasma.txt acao=apagar\n{F}")
p = ex2.preparar(r.acoes)[0]
checa("sem_efeito", p.sem_efeito, p.avisos)

print("\n-- 10. cria pasta que falta --")
r = parse(f"{F}python\n# kitty: file=a/b/c/fundo.py acao=criar\nprint('fundo')\n{F}")
res = ex2.aplicar(ex2.preparar(r.acoes))
checa("criou arvore", (base / "a" / "b" / "c" / "fundo.py").is_file(), res[0].detalhe)

print("\n-- 11. varios arquivos no mesmo lote --")
r = parse(f"""{F}html
<!-- kitty: file=web/index.html acao=criar -->
<h1>oi</h1>
{F}
{F}css
/* kitty: file=web/style.css acao=criar */
body {{ color: red; }}
{F}""")
planos = ex2.preparar(r.acoes)
res = ex2.aplicar(planos)
checa("2 aplicados", all(x.status == "aplicado" for x in res), [x.status for x in res])
checa("html no disco", (base / "web" / "index.html").read_text(encoding="utf-8") == "<h1>oi</h1>")
checa("css no disco", (base / "web" / "style.css").read_text(encoding="utf-8") == "body { color: red; }")
lotes = list((base / ".deepseek_ui" / "backups").iterdir())
checa("relatorio legivel", "✓" in relatorio(res), relatorio(res))

print("\n-- 12. sem temporario sobrando --")
sobras = list(base.rglob(".kitty-*.tmp"))
checa("nenhum .kitty-*.tmp", not sobras, [str(s) for s in sobras])

print("\n-- 13. nao escreve por cima de link para fora --")
import subprocess
fora = base.parent / ("alvo_" + base.name)
fora.mkdir(exist_ok=True)
(fora / "segredo.txt").write_text("SENHA", encoding="utf-8")
j = subprocess.run(f'mklink /J "{base / "atalho"}" "{fora}"', shell=True,
                   capture_output=True, text=True)
if j.returncode == 0:
    r = parse(f"{F}text\n# kitty: file=atalho/segredo.txt acao=modificar\nINVADIDO\n{F}")
    p = Executor(Project(base)).preparar(r.acoes)[0]
    checa("junction recusada", bool(p.erro), p.erro)
    checa("segredo intacto", (fora / "segredo.txt").read_text(encoding="utf-8") == "SENHA")
else:
    print("  (mklink indisponivel, pulando)")

shutil.rmtree(base, ignore_errors=True)
shutil.rmtree(fora, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
