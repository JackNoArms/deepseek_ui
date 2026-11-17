"""Comandos contínuos em segundo plano (ADR-025) e regras do vault pelo cabeçalho."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src import processos
from src.parser import parse
from src.prompts import REGRAS_VAULT, cabecalho_agents, regras_vault
from src.runner import rodar

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


print("-- 1. reconhece comando que não termina --")
for c in ["npm run dev", "yarn dev", "pnpm start", "npm start", "bun run serve",
          "npx vite", "vite --port 3000", "next dev", "ng serve",
          "python -m http.server 8000", "uvicorn app:app --reload",
          "flask run", "python manage.py runserver", "docker compose up",
          "tsc --watch", "cd web && npm run dev", "ping 1.1.1.1 -t"]:
    checa(f"contínuo: {c}", processos.e_continuo(c))
for c in ["npm run build", "npm test", "npm install", "pytest -q", "echo oi",
          "git status", "docker compose up -d", "docker compose up --detach",
          "python main.py", "ping 1.1.1.1"]:
    checa(f"comum: {c}", not processos.e_continuo(c))

print("-- 2. pedido explícito e comandos internos --")
checa("fundo=sim", processos.pediu_fundo({"fundo": "sim"}))
checa("background True", processos.pediu_fundo({"background": True}))
checa("sem pedido", not processos.pediu_fundo({"acao": "rodar"}))
checa("@processos", processos.comando_interno("@processos") == ("processos", None))
checa("@saida 2", processos.comando_interno("@saida 2") == ("saida", 2))
checa("@saída 2 com acento", processos.comando_interno("@saída 2") == ("saida", 2))
checa("@parar 3", processos.comando_interno(" @parar 3 ") == ("parar", 3))
checa("echo @parar não é interno", processos.comando_interno("echo @parar 1") is None)

print("-- 3. protocolos levam o pedido de segundo plano --")
r = parse('```json\n{"response":"ok","actions":[{"action":"run","command":"npm run dev",'
          '"background":true}]}\n```', "json")
checa("json background", r.valida and r.acoes and r.acoes[0].extras.get("fundo") is True,
      (r.erro, [a.extras for a in r.acoes]))
r = parse('```json\n{"response":"ok","actions":[{"action":"run","command":"echo oi"}]}\n```', "json")
checa("json sem background continua valendo", r.valida and r.acoes[0].extras == {}, r.erro)
r = parse('```json\n{"response":"ok","actions":[{"action":"run","command":"x","background":3}]}\n```',
          "json")
checa("json background inválido recusado", not r.valida, r.erro)
r = parse('```xml\n<response><text>ok</text><actions><action type="run" background="true">'
          '<command><![CDATA[npm run dev]]></command></action></actions></response>\n```', "xml")
checa("xml background", r.valida and r.acoes and r.acoes[0].extras.get("fundo") is True,
      (r.erro, [a.extras for a in r.acoes]))
r = parse("```bash\n# kitty: acao=rodar fundo=sim\nnpm run dev\n```", "markdown")
checa("kitty fundo=sim", r.acoes and processos.pediu_fundo(r.acoes[0].extras),
      [a.extras for a in r.acoes])

print("-- 4. servidor sobe, fica vivo e não trava outros comandos --")
with tempfile.TemporaryDirectory(prefix="processos_") as tmp:
    raiz = Path(tmp)
    (raiz / "servidor.py").write_text(
        "import time\nprint('VITE ready', flush=True)\n"
        "print('Local: http://localhost:5173/', flush=True)\ntime.sleep(60)\n",
        encoding="utf-8")
    (raiz / "quieto.py").write_text(
        "import time\nprint('subindo', flush=True)\ntime.sleep(60)\n", encoding="utf-8")
    ger = processos.Gerenciador(raiz / "logs")

    inicio = time.monotonic()
    p1 = ger.iniciar(f"{PY} servidor.py", raiz)
    recebido = []
    motivo, pos = ger.esperar_pronto(p1, max_seg=15, ao_progredir=recebido.append)
    gasto = time.monotonic() - inicio
    checa("motivo pronto", motivo == "pronto", motivo)
    checa("voltou rápido (< 10 s)", gasto < 10, f"{gasto:.1f}s")
    checa("continua vivo depois de pronto", p1.vivo())
    checa("saída inicial chegou ao vivo", "localhost:5173" in "".join(recebido), recebido)
    checa("cauda do log tem o endereço", "localhost:5173" in p1.cauda(), p1.cauda())
    checa("posição lida avançou", pos > 0, pos)

    p2 = ger.iniciar(f"{PY} quieto.py", raiz)
    motivo2, _ = ger.esperar_pronto(p2, max_seg=15, silencio_seg=1.0)
    checa("silêncio depois de falar", motivo2 == "silencio", motivo2)
    checa("dois processos vivos ao mesmo tempo", len(ger.vivos()) == 2, ger.vivos())

    s = rodar("echo comando-comum", raiz, timeout=30)
    checa("comando comum roda com servidores no ar", s.ok and "comando-comum" in s.texto,
          s.resumo())

    lista = ger.executar_interno("processos", None)
    checa("@processos lista os dois", "1 · rodando" in lista and "2 · rodando" in lista, lista)
    saida = ger.executar_interno("saida", 1)
    checa("@saida 1 mostra o log", "localhost:5173" in saida, saida)
    checa("@saida sem número pede o número", "informe o número"
          in ger.executar_interno("saida", None))
    checa("@parar 9 inexistente", "não existe" in ger.executar_interno("parar", 9))
    parar = ger.executar_interno("parar", 1)
    checa("@parar 1 encerra", "encerrado" in parar and not p1.vivo(), parar)
    checa("o outro segue vivo", p2.vivo())
    ger.parar_todos()
    checa("parar_todos encerra o resto", not p2.vivo())

    p3 = ger.iniciar("echo fim-rapido", raiz)
    motivo3, _ = ger.esperar_pronto(p3, max_seg=15)
    checa("comando que termina volta como terminou", motivo3 == "terminou", motivo3)
    checa("código 0 e saída", p3.codigo == 0 and "fim-rapido" in p3.cauda(),
          (p3.codigo, p3.cauda()))

    try:
        ger.iniciar("echo x", raiz / "nao-existe")
        checa("pasta inexistente recusada", False, "não levantou")
    except processos.ComandoRecusado:
        checa("pasta inexistente recusada", True)

print("-- 5. regras do vault vêm do cabeçalho do AGENTS.md --")
checa("sem cabeçalho = texto de antes", regras_vault("") == REGRAS_VAULT)
checa("padrão aponta 00 - Índice", "vault/00 - Índice.md" in REGRAS_VAULT)
agents = ('---\nvault_id: x\nindice: "00 - Início.md"\npadrao: "00 - Padrão do Vault.md"\n'
          'passagem: "Billing/Passagem.md"   # comentário\n---\n# Instruções\n')
cab = cabecalho_agents(agents)
checa("cabeçalho lido", cab.get("indice") == "00 - Início.md"
      and cab.get("passagem") == "Billing/Passagem.md", cab)
regras = regras_vault(agents)
checa("índice do cabeçalho", "vault/00 - Início.md" in regras, regras)
checa("padrão do cabeçalho", "vault/00 - Padrão do Vault.md" in regras, regras)
checa("passagem do cabeçalho", "vault/Billing/Passagem.md" in regras, regras)
checa("caminho com .. é ignorado",
      "vault/00 - Índice.md" in regras_vault('---\nindice: "../segredo.md"\n---\n'))

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
