"""Os dois cenários pedidos: revisar N arquivos em fila, e caçar bug por busca."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from src.agent import Agente, Callbacks
from src.project import Project
from src.sandbox import SandboxError

ok = fail = 0
F = "```"

def checa(n, c, e=""):
    global ok, fail
    if c: print(f"  ok      {n}"); ok += 1
    else: print(f"  FALHOU  {n} -> {e}"); fail += 1


class FakeController:
    def __init__(self, respostas):
        self.respostas = list(respostas); self.enviadas = []
        self.is_connected = True
    def current_url(self): return None
    def send_message(self, texto, on_update=None, on_sent=None):
        self.enviadas.append(texto)
        if on_sent:
            on_sent()
        return self.respostas.pop(0) if self.respostas else f"{F}\n# kitty: acao=fim\n{F}"


class Espiao(Callbacks):
    def __init__(self):
        self.motivo = ""
        self.lidos = []
        self.confirmacoes_leitura = []
        self.permitir_leitura = True
    def leitura(self, rel): self.lidos.append(rel)
    def confirmar_leitura(self, acao, descricao):
        self.confirmacoes_leitura.append((acao.verbo, descricao))
        return self.permitir_leitura
    def confirmar_escrita(self, planos): return [p for p in planos if p.aplicavel]
    def confirmar_comando(self, acoes): return ""
    def fim(self, motivo): self.motivo = motivo


# ---------------------------------------------------------------- projeto
base = Path(tempfile.mkdtemp(prefix="inv_"))
(base / "textos").mkdir()
(base / "src" / "models").mkdir(parents=True)
(base / "src" / "util").mkdir(parents=True)

for i, corpo in enumerate([
        "O rato roeu a roupa do rei de Roma.",
        "Vender é mais dificil do que parece.",
        "Nós vai no mercado amanhã.",
        "A reunião foi remarcada pra sexta."], 1):
    (base / "textos" / f"texto{i}.txt").write_text(corpo + "\n", encoding="utf-8")

(base / "src" / "models" / "pedido.py").write_text(
    "class Pedido:\n"
    "    def calcularTotal(self):\n"
    "        return self.subtotal + self.frete\n", encoding="utf-8")
(base / "src" / "models" / "carrinho.py").write_text(
    "from .pedido import Pedido\n\n"
    "class Carrinho:\n"
    "    def total(self):\n"
    "        return self.pedido.calcularTotal()\n", encoding="utf-8")
(base / "src" / "util" / "fmt.py").write_text(
    "def moeda(v):\n    return f'R$ {v:.2f}'\n", encoding="utf-8")
(base / "README.md").write_text("# projeto\ncalcularTotal esta no models\n",
                                encoding="utf-8")

proj = Project(base)

print("-- 1. listar uma subpasta, nao o projeto inteiro --")
arvore = proj.listar("src/models")
checa("lista a subpasta", "pedido.py" in arvore and "carrinho.py" in arvore, arvore)
checa("nao traz o resto do projeto", "fmt.py" not in arvore and "texto1.txt" not in arvore,
      arvore)
checa("sem dir, traz tudo", "textos" in proj.listar(), proj.listar()[:200])
try:
    proj.listar("../fora")
    checa("listar fora e barrado", False, "passou")
except SandboxError:
    checa("listar fora e barrado", True)

print("\n-- 2. buscar acha onde o nome aparece --")
r = proj.buscar("calcularTotal")
checa("achou nos 3 arquivos", r.count("calcularTotal") >= 3, r)
checa("tem arquivo:linha", "src/models/pedido.py:2" in r, r)
checa("nao diferencia maiuscula", "calculartotal" in proj.buscar("CALCULARTOTAL").lower(), )
checa("ext filtra", "README.md" not in proj.buscar("calcularTotal", ext="py"),
      proj.buscar("calcularTotal", ext="py"))
checa("em= limita a pasta",
      "fmt.py" not in proj.buscar("def", em="src/models"),
      proj.buscar("def", em="src/models"))
checa("sem achado avisa", "Nenhum resultado" in proj.buscar("xyzinexistente"))

print("\n-- 3. FILA: 4 textos pedidos de uma vez, na ordem --")
pedido_lote = "\n".join(
    f"{F}\n# kitty: acao=ler file=textos/texto{i}.txt\n{F}" for i in (1, 2, 3, 4))
ctrl = FakeController([
    f"Vou ler os quatro.\n\n{pedido_lote}",
    f"Achei os erros.\n\n{F}\n# kitty: acao=fim\n{F}",
])
esp = Espiao()
ag = Agente(ctrl, proj, esp)
ag.rodar("revise os 4 textos da pasta textos e aponte os erros")

checa("2 rodadas so (leu em lote)", len(ag.passos) == 2, len(ag.passos))
checa("leu os 4", esp.lidos == ["textos/texto1.txt", "textos/texto2.txt",
                                "textos/texto3.txt", "textos/texto4.txt"], esp.lidos)
volta = ctrl.enviadas[1]
checa("os 4 conteudos voltaram numa mensagem so",
      all(t in volta for t in ["roeu a roupa", "mais dificil", "Nós vai", "remarcada"]),
      volta[:300])
checa("ordem preservada",
      volta.index("roeu a roupa") < volta.index("mais dificil")
      < volta.index("Nós vai") < volta.index("remarcada"))
checa("cada um marcado com o caminho", volta.count("Arquivo `textos/") == 4,
      volta.count("Arquivo `textos/"))

print("\n-- 4. CAÇA AO BUG: buscar -> listar -> ler -> corrigir --")
ctrl = FakeController([
    f"Onde esta esse metodo?\n\n{F}\n# kitty: acao=buscar termo=calcularTotal ext=py\n{F}",
    f"Vou ver a pasta e o arquivo.\n\n"
    f"{F}\n# kitty: acao=listar dir=src/models\n{F}\n"
    f"{F}\n# kitty: acao=ler file=src/models/pedido.py\n{F}",
    f"Achei: faltava o desconto.\n\n"
    f"{F}python\n# kitty: file=src/models/pedido.py acao=modificar\n"
    f"class Pedido:\n    def calcularTotal(self):\n"
    f"        return self.subtotal + self.frete - self.desconto\n{F}\n\n"
    f"{F}\n# kitty: acao=fim\n{F}",
])
esp = Espiao()
ag = Agente(ctrl, proj, esp)
ag.rodar("tem um bug no calculo do total, ache e corrija")

checa("3 rodadas", len(ag.passos) == 3, len(ag.passos))
checa("buscou primeiro", "busca por 'calcularTotal'" in esp.lidos[0], esp.lidos)
checa("resultado da busca voltou com arquivo:linha",
      "src/models/pedido.py:2" in ctrl.enviadas[1], ctrl.enviadas[1][:400])
checa("listou a subpasta", any("árvore de src/models" in x for x in esp.lidos), esp.lidos)
checa("leu o arquivo", "src/models/pedido.py" in esp.lidos, esp.lidos)
final = (base / "src" / "models" / "pedido.py").read_text(encoding="utf-8")
checa("corrigiu o arquivo", "desconto" in final, final)
checa("terminou", "concluída" in esp.motivo, esp.motivo)

print("\n-- 5. 'fim' junto com pedido de leitura NAO encerra cedo --")
ctrl = FakeController([
    f"{F}\n# kitty: acao=ler file=README.md\n{F}\n{F}\n# kitty: acao=fim\n{F}",
    f"Agora sim.\n\n{F}\n# kitty: acao=fim\n{F}",
])
esp = Espiao()
ag = Agente(ctrl, proj, esp)
ag.rodar("leia o readme e resuma")
checa("leu antes de encerrar", "README.md" in esp.lidos, esp.lidos)
checa("devolveu o conteudo", "calcularTotal esta no models" in ctrl.enviadas[1],
      ctrl.enviadas[1][:200])

print("\n-- 6. recusa de leitura não compartilha conteúdo --")
(base / "segredo.txt").write_text("CONTEUDO PRIVADO", encoding="utf-8")
ctrl = FakeController([
    f"{F}\n# kitty: acao=ler file=segredo.txt\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
esp = Espiao()
esp.permitir_leitura = False
Agente(ctrl, proj, esp).rodar("leia o segredo")
checa("pediu consentimento antes da leitura",
      esp.confirmacoes_leitura == [("ler", "segredo.txt")],
      esp.confirmacoes_leitura)
checa("recusa não adiciona conteúdo ao histórico enviado",
      "CONTEUDO PRIVADO" not in ctrl.enviadas[1]
      and "nenhum conteúdo foi enviado" in ctrl.enviadas[1],
      ctrl.enviadas[1])
checa("leitura recusada não aparece como leitura concluída",
      "segredo.txt" not in esp.lidos, esp.lidos)

print("\n-- 7. conteudo gigante vai inteiro, sem corte silencioso --")
(base / "enorme.txt").write_text("linha de enchimento\n" * 20000 + "ULTIMA LINHA",
                                 encoding="utf-8")
proj2 = Project(base)
ctrl = FakeController([
    f"{F}\n# kitty: acao=ler file=enorme.txt\n{F}\n"
    f"{F}\n# kitty: acao=ler file=README.md\n{F}",
    f"{F}\n# kitty: acao=fim\n{F}",
])
esp = Espiao()
ag = Agente(ctrl, proj2, esp)
ag.rodar("leia tudo")
volta = ctrl.enviadas[1]
checa("o gigante chegou inteiro", "ULTIMA LINHA" in volta and "cortado" not in volta,
      volta[-300:])
checa("o arquivo seguinte tambem foi", "README.md" in volta, volta[-300:])

print("\n-- 8. todos os pedidos da rodada sao atendidos --")
muitos = "\n".join(f"{F}\n# kitty: acao=ler file=textos/texto{(i % 4) + 1}.txt\n{F}"
                   for i in range(12))
ctrl = FakeController([muitos, f"{F}\n# kitty: acao=fim\n{F}"])
esp = Espiao()
ag = Agente(ctrl, proj, esp)
ag.rodar("leia tudo")
checa("os 12 pedidos", len(ag.passos[0].leituras) == 12, len(ag.passos[0].leituras))
checa("nada ficou para depois", "não couberam" not in ctrl.enviadas[1],
      ctrl.enviadas[1][:300])

shutil.rmtree(base, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
