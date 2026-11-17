"""Testa o parser, inclusive com a saida REAL capturada nas sondas da Fase 0."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
from src.parser import parse

ok = fail = 0

def checa(nome, cond, extra=""):
    global ok, fail
    if cond:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} {extra}")
        fail += 1

F = "```"

print("-- 1. saida REAL da sonda 3 (Fase 0) --")
real = f"""{F}python
print("ok")
{F}
{F}python:src/b.py:criar
print("ok")
{F}
{F}python
# kitty: file=src/c.py acao=criar
print("ok")
{F}"""
r = parse(real)
checa("2 acoes (cerca + comentario)", len(r.acoes) == 2, [a.caminho for a in r.acoes])
checa("1 bloco solto", r.blocos_soltos == 1, r.blocos_soltos)
if len(r.acoes) == 2:
    a, b = r.acoes
    checa("cerca -> src/b.py", a.caminho == "src/b.py", a.caminho)
    checa("cerca -> criar", a.verbo == "criar", a.verbo)
    checa("cerca -> lang python", a.lang == "python", a.lang)
    checa("comentario -> src/c.py", b.caminho == "src/c.py", b.caminho)
    checa("comentario -> criar", b.verbo == "criar", b.verbo)
    checa("linha kitty REMOVIDA do conteudo", b.conteudo == 'print("ok")', repr(b.conteudo))

print("\n-- 2. conteudo preservado (newline e indentacao) --")
r = parse(f"""{F}python
# kitty: file=src/calc.py acao=criar
def somar(a, b):
    # soma
    return a + b
{F}""")
esperado = 'def somar(a, b):\n    # soma\n    return a + b'
checa("conteudo exato", r.acoes[0].conteudo == esperado, repr(r.acoes[0].conteudo))

print("\n-- 3. prefixos de comentario por linguagem --")
for pref, lang, caminho in [("//", "js", "src/a.js"), ("--", "sql", "q.sql"),
                            ("<!--", "html", "i.html"), (";", "ini", "c.ini"),
                            ("#", "py", "a.py"), ("", "txt", "n.txt")]:
    r = parse(f"{F}{lang}\n{pref} kitty: file={caminho} acao=criar\nconteudo\n{F}")
    checa(f"prefixo {pref!r:6} -> {caminho}",
          len(r.acoes) == 1 and r.acoes[0].caminho == caminho
          and r.acoes[0].conteudo == "conteudo",
          [(a.caminho, a.conteudo) for a in r.acoes])

print("\n-- 4. html com fechamento --> --")
r = parse(f"{F}html\n<!-- kitty: file=i.html acao=criar -->\n<p>oi</p>\n{F}")
checa("html fecha comentario", len(r.acoes) == 1 and r.acoes[0].caminho == "i.html",
      [a.caminho for a in r.acoes])
checa("conteudo html limpo", r.acoes and r.acoes[0].conteudo == "<p>oi</p>",
      repr(r.acoes[0].conteudo) if r.acoes else None)

print("\n-- 5. verbos e sinonimos --")
for palavra, esperado_verbo in [("criar", "criar"), ("modificar", "modificar"),
                                ("editar", "modificar"), ("update", "modificar"),
                                ("apagar", "apagar"), ("delete", "apagar"),
                                ("ler", "ler"), ("read", "ler")]:
    r = parse(f"{F}python\n# kitty: file=a.py acao={palavra}\nx\n{F}")
    checa(f"{palavra:10} -> {esperado_verbo}",
          r.acoes and r.acoes[0].verbo == esperado_verbo,
          r.acoes[0].verbo if r.acoes else None)

print("\n-- 6. apagar nao carrega conteudo --")
r = parse(f"{F}python\n# kitty: file=velho.py acao=apagar\n{F}")
checa("apagar com conteudo None", r.acoes and r.acoes[0].conteudo is None,
      repr(r.acoes[0].conteudo) if r.acoes else None)

print("\n-- 7. shell vira rodar sem verbo explicito --")
r = parse(f"{F}bash\n# kitty: acao=rodar\npytest -q\n{F}")
checa("bash -> rodar", r.acoes and r.acoes[0].verbo == "rodar",
      r.acoes[0].verbo if r.acoes else None)

print("\n-- 8. acao so na prosa --")
r = parse("Terminei o que pediu.\n\n# kitty: acao=fim")
checa("acao=fim na prosa", len(r.acoes) == 1 and r.acoes[0].verbo == "fim",
      [(a.verbo, a.caminho) for a in r.acoes])
checa("resumo mantido", "Terminei" in r.resumo, repr(r.resumo))

r = parse("Vou precisar ver isso.\n# kitty: acao=ler file=src/app.py")
checa("acao=ler na prosa", len(r.acoes) == 1 and r.acoes[0].caminho == "src/app.py",
      [(a.verbo, a.caminho) for a in r.acoes])

print("\n-- 9. bloco comum NAO vira acao --")
r = parse(f"Exemplo:\n\n{F}python\nprint(1)\n{F}\n\nSo isso.")
checa("nenhuma acao", not r.tem_acao, [a.verbo for a in r.acoes])
checa("marcado como suspeito", r.suspeita, r.suspeita)
checa("resumo junta a prosa", "Exemplo" in r.resumo and "So isso" in r.resumo, repr(r.resumo))

print("\n-- 10. resposta so de texto nao e suspeita --")
r = parse("O bug esta no middleware, troque < por <=.")
checa("sem acao e sem bloco", not r.tem_acao and not r.suspeita, (r.tem_acao, r.suspeita))

print("\n-- 11. aspas no caminho --")
r = parse(f'{F}python\n# kitty: file="src/com espaco.py" acao=criar\nx\n{F}')
checa("caminho entre aspas", r.acoes and r.acoes[0].caminho == "src/com espaco.py",
      r.acoes[0].caminho if r.acoes else None)

print("\n-- 12. cerca sem verbo -> modificar --")
r = parse(f"{F}python:src/z.py\nx\n{F}")
checa("infere modificar", r.acoes and r.acoes[0].verbo == "modificar",
      r.acoes[0].verbo if r.acoes else None)
checa("origem inferido", r.acoes and r.acoes[0].origem == "inferido",
      r.acoes[0].origem if r.acoes else None)

print("\n-- 13. cerca aberta (streaming) --")
r = parse(f"{F}python\n# kitty: file=a.py acao=criar\nprint(1)")
checa("le bloco nao fechado", r.acoes and r.acoes[0].caminho == "a.py",
      [a.caminho for a in r.acoes])

print("\n-- 14. varios arquivos numa resposta --")
r = parse(f"""Criei tres.

{F}html
<!-- kitty: file=index.html acao=criar -->
<h1>oi</h1>
{F}

{F}css
/* kitty: file=style.css acao=criar */
body {{ color: red; }}
{F}

{F}js
// kitty: file=app.js acao=criar
console.log(1);
{F}""")
checa("3 acoes", len(r.acoes) == 3, [a.caminho for a in r.acoes])
checa("caminhos certos",
      [a.caminho for a in r.acoes] == ["index.html", "style.css", "app.js"],
      [a.caminho for a in r.acoes])
checa("css limpo", r.acoes[1].conteudo == "body { color: red; }" if len(r.acoes) > 1 else False,
      repr(r.acoes[1].conteudo) if len(r.acoes) > 1 else None)

print("\n-- 15. pedido de decisao do usuario --")
r = parse(f"""Preciso confirmar uma escolha antes de continuar.

{F}text
# kitty: acao=decidir
{{"question":"Qual abordagem devo seguir?","options":["A","B"]}}
{F}""")
checa("decisao Markdown reconhecida", r.valida and len(r.acoes) == 1
      and r.acoes[0].verbo == "decidir", r.erro)
checa("pergunta e opcoes normalizadas",
      r.acoes[0].extras == {"pergunta": "Qual abordagem devo seguir?",
                            "opcoes": ["A", "B"]},
      r.acoes[0].extras if r.acoes else None)
checa("bloco de decisao removido do resumo",
      "Preciso confirmar" in r.resumo and '"question"' not in r.resumo,
      r.resumo)
invalida = parse(f"""{F}text
# kitty: acao=decidir
{{"question":"Qual?","options":["A","A"]}}
{F}""")
checa("opcoes duplicadas rejeitadas", not invalida.valida and not invalida.acoes,
      invalida.erro)
invalida = parse("# kitty: acao=decidir")
checa("decisao Markdown sem bloco rejeitada", not invalida.valida,
      invalida.erro)

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
