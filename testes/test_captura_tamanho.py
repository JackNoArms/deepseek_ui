"""Captura pela API do site, erros de tamanho nos dois sentidos e fim dos tetos.

Caso que motivou: numa conversa longa o DOM congelou em `{"res` enquanto o site
terminava a resposta; o app esperava 20s de texto parado e devolvia o pedaço.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

import src.wrapper as wrapper_module
from src.agent import Agente, Callbacks
from src.parser import parse
from src.project import Project
from src.prompts import anexo, cerca, realimentar
from src.sandbox import SandboxError
from src.wrapper import (DeepSeekWrapper, ErroTamanho, avaliar_estado_api,
                         tamanho_js)

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


def estado(usuario_id=11, usuario_tam=None, resposta_id=12, status="FINISHED",
           texto="", enviado="pedido"):
    return {
        "sessao": "abc", "max_id": resposta_id or usuario_id,
        "usuario": {"id": usuario_id,
                    "tamanho": tamanho_js(enviado) if usuario_tam is None else usuario_tam},
        "resposta": None if resposta_id is None else {
            "id": resposta_id, "status": status, "tamanho": len(texto),
            "pensamento": 0, "texto": texto, "tokens": 1234, "incompleta": None},
    }


print("-- 1. avaliar_estado_api --")
fase, _ = avaliar_estado_api(estado(usuario_id=10), 10, "pedido")
checa("mensagem antiga ainda não é desta rodada", fase == "aguardando", fase)
fase, _ = avaliar_estado_api(estado(resposta_id=None), 10, "pedido")
checa("sem resposta ainda", fase == "aguardando", fase)
fase, r = avaliar_estado_api(estado(status="WIP"), 10, "pedido")
checa("WIP é gerando", fase == "gerando", fase)
fase, r = avaliar_estado_api(estado(status="FINISHED", texto="x"), 10, "pedido")
checa("FINISHED é pronta", fase == "pronta" and r["tokens"] == 1234, (fase, r))
fase, _ = avaliar_estado_api(estado(status="INCOMPLETE"), 10, "pedido")
checa("INCOMPLETE é cortada", fase == "cortada", fase)
fase, _ = avaliar_estado_api(estado(status="CONTEXT_LENGTH_EXCEEDED"), 10, "pedido")
checa("status que fala de tamanho é cortada", fase == "cortada", fase)
fase, _ = avaliar_estado_api(estado(status="NOVO_STATUS"), 10, "pedido")
checa("status novo é desconhecida", fase == "desconhecida", fase)

grande = "a" * 100_000
try:
    avaliar_estado_api(estado(usuario_tam=60_000, enviado=grande), 10, grande)
    checa("envio cortado levanta ErroTamanho", False, "não levantou")
except ErroTamanho as e:
    checa("envio cortado levanta ErroTamanho",
          e.lado == "envio" and e.enviado == 100_000 and e.recebido == 60_000, vars(e))
    checa("mensagem traz os dois tamanhos", "60.000" in str(e) and "100.000" in str(e),
          str(e))
fase, _ = avaliar_estado_api(
    estado(usuario_tam=tamanho_js("pedido"), enviado="  pedido\r\n"), 10, "  pedido\r\n")
checa("espaço aparado pelo site não é corte", fase == "pronta", fase)
emoji = "ação 😀" * 10
fase, _ = avaliar_estado_api(estado(enviado=emoji), 10, emoji)
checa("tamanho conta em UTF-16 como o JS", fase == "pronta", fase)


print("\n-- 2. espera da resposta: DOM congelado, servidor pronto --")
wrapper_module.API_DOM_PARADO = 0.1
wrapper_module.API_INTERVALO = 0.1


class WrapperFalso(DeepSeekWrapper):
    """Sem navegador: DOM e API vêm de roteiros."""

    def __init__(self, dom, api, timeouts=None):
        super().__init__()
        self.driver = object()   # não-nulo; qualquer chamada real falha e cai no default
        self.is_connected = True
        self.config = dict(self.config)
        self.config["timeouts"] = {
            "stable_seconds": 1, "completion_confirmations": 2,
            "unknown_completion_confirmations": 2, "response_wait": 30,
            **(timeouts or {})}
        self.dom = list(dom)
        self.api = list(api)
        self.consultas_api = 0

    def _extract_last(self):
        return self.dom.pop(0) if len(self.dom) > 1 else self.dom[0]

    def clicar_continuar(self):
        return False

    def _estado_api(self, incluir_texto=False):
        self.consultas_api += 1
        atual = self.api.pop(0) if len(self.api) > 1 else self.api[0]
        if atual is None:
            return None
        if not incluir_texto and atual.get("resposta"):
            atual = {**atual, "resposta": {**atual["resposta"], "texto": None}}
        return atual


completo = '```json\n{"response":"Ler o teste.","actions":[]}\n```'
congelado = '```json\n{"res\n```'
w = WrapperFalso(dom=["anterior", congelado],
                 api=[estado(status="WIP", texto='{"res'),
                      estado(status="FINISHED", texto=completo)])
parciais = []
volta = w._aguardar_resposta("pedido", "anterior", 10, parciais.append)
checa("devolve o texto do servidor, não o DOM congelado", volta == completo, volta)
checa("resposta é JSON válido", parse(volta, formato="json").valida)
checa("captura marcada como vinda da API",
      w.ultima_captura.get("fonte") == "api" and w.ultima_captura.get("tokens") == 1234,
      w.ultima_captura)

print("\n-- 3. resposta cortada pelo site vira ErroTamanho --")
w = WrapperFalso(dom=["anterior", congelado],
                 api=[estado(status="INCOMPLETE", texto='{"response":"metade')])
try:
    w._aguardar_resposta("pedido", "anterior", 10, None)
    checa("levantou ErroTamanho de resposta", False, "não levantou")
except ErroTamanho as e:
    checa("levantou ErroTamanho de resposta", e.lado == "resposta", e.lado)
    checa("guarda o pedaço que chegou", e.parcial == '{"response":"metade', e.parcial)
    checa("fala do limite de saída e dos tokens",
          "limite de saída" in str(e) and "1.234 tokens" in str(e), str(e))

print("\n-- 4. envio cortado é detectado na espera --")
w = WrapperFalso(dom=["anterior"], api=[estado(usuario_tam=10, enviado=grande)])
try:
    w._aguardar_resposta(grande, "anterior", 10, None)
    checa("levantou ErroTamanho de envio", False, "não levantou")
except ErroTamanho as e:
    checa("levantou ErroTamanho de envio", e.lado == "envio", e.lado)

print("\n-- 5. sem API, a heurística do DOM continua valendo --")
w = WrapperFalso(dom=["anterior", "resposta inteira"], api=[None])
volta = w._aguardar_resposta("pedido", "anterior", None, None)
checa("DOM decide quando a API não existe", volta == "resposta inteira", volta)
checa("nem tentou a API", w.consultas_api == 0, w.consultas_api)
w = WrapperFalso(dom=["anterior", "resposta inteira"], api=[None])
volta = w._aguardar_resposta("pedido", "anterior", 10, None)
checa("API caiu no meio: DOM assume", volta == "resposta inteira", volta)

print("\n-- 6. sem progresso nenhum vira erro, não resposta pela metade --")
w = WrapperFalso(dom=["anterior"], api=[estado(usuario_id=10, resposta_id=None)],
                 timeouts={"response_wait": 1.5})
try:
    w._aguardar_resposta("pedido", "anterior", 10, None)
    checa("estourou por falta de progresso", False, "não levantou")
except ErroTamanho:
    checa("estourou por falta de progresso", False, "virou ErroTamanho")
except RuntimeError as e:
    checa("estourou por falta de progresso", "sem avançar" in str(e), str(e))

print("\n-- 6b. site recusa o envio por tamanho (toast real de 2026-10-16) --")
TOAST = "Conteúdo muito longo (13%). Encurte e tente novamente."


class InputFalso:
    def __init__(self):
        self.value = ""
    def clear(self):
        self.value = ""
    def get_property(self, nome):
        return self.value if nome == "value" else None
    def send_keys(self, tecla):
        pass


class DriverFalso:
    def execute_script(self, script, *args):
        if script == wrapper_module.JS_SET_INPUT:
            args[0].value = args[1]


class WrapperRecusa(DeepSeekWrapper):
    def __init__(self):
        super().__init__()
        self.driver = DriverFalso()
        self.is_connected = True
        self.cliques_enviar = 0
    def _submission_confirmed(self, *args):
        return False
    def avisos_site(self):
        return [TOAST]


w = WrapperRecusa()
campo = InputFalso()
try:
    w._submit_message(campo, "x" * 3_000_000)
    checa("recusa vira ErroTamanho de envio", False, "não levantou")
except ErroTamanho as e:
    checa("recusa vira ErroTamanho de envio", e.lado == "envio", e.lado)
    checa("erro traz o tamanho e o aviso do site",
          "3.000.000" in str(e) and TOAST in str(e), str(e))
    checa("campo do site esvaziado", campo.value == "", len(campo.value))
checa("aviso genérico não é tamanho",
      not wrapper_module._menciona_tamanho("Servidor ocupado, tente mais tarde"))
checa("rate limit não é tamanho",
      not wrapper_module._menciona_tamanho("Rate limit reached"))

print("\n-- 7. agente: erros de tamanho --")


class Espiao(Callbacks):
    def __init__(self):
        self.motivo = ""
        self.respostas = []
    def resposta(self, passo, lido): self.respostas.append(lido)
    def fim(self, motivo): self.motivo = motivo


class ControllerErro:
    def __init__(self, roteiro, captura=None):
        self.roteiro = list(roteiro)
        self.enviadas = []
        self.ultima_captura = captura or {}
    def send_message(self, texto, on_update=None, on_sent=None):
        self.enviadas.append(texto)
        if on_sent:
            on_sent()
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


base = Path(tempfile.mkdtemp(prefix="tam_"))
(base / "a.txt").write_text("conteúdo", encoding="utf-8")
proj = Project(base)
FIM = '```json\n{"response":"ok","actions":[{"action":"done"}]}\n```'

esp = Espiao()
ctrl = ControllerErro([ErroTamanho("envio", "guardou 10 de 100", enviado=100, recebido=10)])
Agente(ctrl, proj, esp, formato="json").rodar("tarefa")
checa("envio cortado interrompe a tarefa", "interrompida" in esp.motivo
      and "guardou 10 de 100" in esp.motivo, esp.motivo)
checa("só uma tentativa de envio", len(ctrl.enviadas) == 1, len(ctrl.enviadas))
checa("bolha da rodada fechada com o erro",
      esp.respostas and not esp.respostas[0].valida, esp.respostas)

esp = Espiao()
ctrl = ControllerErro([ErroTamanho("resposta", "cortada em 5", parcial="metade"), FIM])
Agente(ctrl, proj, esp, formato="json").rodar("tarefa")
checa("resposta cortada pede partes menores ao modelo",
      len(ctrl.enviadas) == 2 and "partes menores" in ctrl.enviadas[1], ctrl.enviadas[-1][:200])
checa("depois segue e conclui", "concluída" in esp.motivo, esp.motivo)

esp = Espiao()
ctrl = ControllerErro([ErroTamanho("resposta", "x", parcial="")] * 4)
Agente(ctrl, proj, esp, formato="json").rodar("tarefa")
checa("cortes seguidos param no teto de erros", "interrompida" in esp.motivo
      and len(ctrl.enviadas) == 4, (esp.motivo, len(ctrl.enviadas)))

esp = Espiao()
ctrl = ControllerErro(['```json\n{"response": "sem fechar\n```', FIM],
                      captura={"fonte": "api"})
Agente(ctrl, proj, esp, formato="json").rodar("tarefa")
checa("JSON inválido vindo do servidor culpa o conteúdo, não a captura",
      "exatamente o que o DeepSeek guardou" in ctrl.enviadas[1]
      and "captura da resposta tiver vindo incompleta" not in ctrl.enviadas[1],
      ctrl.enviadas[1][:300])

esp = Espiao()
ctrl = ControllerErro(['```json\n{"response": "sem fechar\n```', FIM],
                      captura={"fonte": "dom"})
Agente(ctrl, proj, esp, formato="json").rodar("tarefa")
checa("JSON inválido vindo do DOM ainda admite captura incompleta",
      "captura da resposta tiver vindo incompleta" in ctrl.enviadas[1],
      ctrl.enviadas[1][:300])

print("\n-- 8. sem tetos de tamanho --")
(base / "gigante.txt").write_text("x" * 5_000_000 + "FIM", encoding="utf-8")
checa("ler devolve o arquivo inteiro", proj.ler("gigante.txt").endswith("FIM"))
(base / "binario.dat").write_bytes(b"\x00\x01\x02" * 100)
try:
    proj.ler("binario.dat")
    checa("binário é recusado com motivo", False, "leu")
except SandboxError as e:
    checa("binário é recusado com motivo", "binário" in str(e), str(e))
for i in range(450):
    (base / f"arq{i:03}.txt").write_text("x", encoding="utf-8")
mapa = Project(base).mapa()
checa("mapa sem corte", "cortado" not in mapa and "arq449.txt" in mapa, mapa[-200:])
checa("limite explícito ainda funciona", "cortado em 10" in Project(base).mapa(limite=10))
(base / "linhas.txt").write_text("alvo\n" * 500, encoding="utf-8")
achados = Project(base).buscar("alvo")
checa("busca sem teto de achados", achados.startswith("500 linha(s)"), achados[:80])

json_gigante = '```json\n{"response":"' + "y" * 6_000_000 + '","actions":[]}\n```'
checa("parser aceita bloco de 6 MB", parse(json_gigante, formato="json").valida)

print("\n-- 9. cerca não fecha antes da hora --")
readme = "texto\n```python\nprint(1)\n```\nfim"
bloco = cerca(readme)
checa("cerca maior que as crases do conteúdo",
      bloco.startswith("````\n") and bloco.endswith("\n````"), bloco)
checa("anexo usa a cerca segura", "````\n" + readme in anexo("README.md", readme))
checa("relatório também", "````" in realimentar("saída com ``` dentro"))
checa("conteúdo sem crases mantém 3", cerca("abc") == "```\nabc\n```", cerca("abc"))

print("\n-- 10. todo JS injetado compila --")
# Selenium embrulha o script numa função; erro de sintaxe vira `default`
# calado no `_js`. Foi assim que a detecção de "gerando" ficou morta.
import shutil as _sh
import subprocess
if _sh.which("node"):
    for nome in sorted(k for k in dir(wrapper_module) if k.startswith("JS_")):
        arquivo = base / f"{nome}.js"
        arquivo.write_text("(async function () {\n" + getattr(wrapper_module, nome)
                           + "\n});\n", encoding="utf-8")
        proc = subprocess.run(["node", "--check", str(arquivo)],
                              capture_output=True, text=True)
        checa(f"{nome} compila", proc.returncode == 0, proc.stderr[-300:])
else:
    print("  (node ausente: verificação de sintaxe pulada)")

shutil.rmtree(base, ignore_errors=True)
print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
