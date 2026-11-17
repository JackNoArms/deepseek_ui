"""Automação do chat.deepseek.com via Selenium.

Responsável por: abrir o Chrome com um perfil persistente (o login fica salvo),
ler o estado dos controles da página (DeepThink, Search), acioná-los,
enviar mensagens e devolver a resposta em Markdown.

Versão enxuta: só o que a UI simples precisa — sem editor, sem workspace.
"""

import json
import os
import subprocess
import threading
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.caminhos import pasta_perfil_chrome, raiz_recursos

# ------------------------------------------------------------------
# Scripts injetados na página
# ------------------------------------------------------------------

# Ordem importa: .ds-assistant-message-main-content é a RESPOSTA de fato.
# .ds-markdown também casa com o bloco de raciocínio do DeepThink
# (.ds-think-content), que precisa ser descartado — senão, enquanto o modelo
# "pensa", extraíamos o rascunho do raciocínio achando que era a resposta.
MESSAGE_SELECTORS = """['.ds-assistant-message-main-content', '.ds-markdown',
                        '.assistant-message-content', '.markdown-body', '.prose']"""

JS_PICK_NODES = """
function pickNodes(selectors) {
    for (const s of selectors) {
        const els = Array.from(document.querySelectorAll(s))
            .filter(el => !el.closest('.ds-think-content'));
        if (els.length) return els;
    }
    return [];
}
"""

# Converte um nó de resposta em Markdown: .md-code-block vira cerca ``` com a
# linguagem do banner, <code> inline vira `crase`, botões somem. O clone é
# inserido fora da tela antes de ler innerText — em nó solto o innerText degrada
# para textContent e cola os parágrafos.
JS_NODE_TO_MD = r"""
function nodeToMarkdown(node) {
    const clone = node.cloneNode(true);
    clone.querySelectorAll('.ds-think-content').forEach(e => e.remove());
    const NOISE = /(copy|download|copiar|baixar|copiado)/gi;
    function fence(lang, code) {
        const holder = document.createElement('div');
        holder.style.whiteSpace = 'pre';
        holder.textContent = '```' + lang + '\n' + code + '\n```';
        return holder;
    }
    clone.querySelectorAll('.md-code-block').forEach(block => {
        let lang = '';
        const banner = block.querySelector('.md-code-block-banner-wrap, .md-code-block-banner');
        if (banner) {
            // O DeepSeek corta a info string no primeiro espaço: de
            // "```python file=src/a.py" só sobra "python". Mas o PRIMEIRO token
            // vem inteiro, então "```python:src/a.py:criar" chega completo aqui.
            // Por isso pegamos o token todo, sem baixar a caixa (caminho é
            // sensível a maiúscula) e sem filtrar ':' e '/'.
            const raw = (banner.innerText || '').replace(NOISE, '').trim();
            const primeira = raw.split('\n')[0].trim();
            const m = primeira.match(/^\S+/);
            if (m && m[0].length <= 120) lang = m[0];
            banner.remove();
        }
        if (!lang) {
            const codeEl = block.querySelector('code');
            const m = codeEl && (codeEl.className || '').match(/language-([\w+#.-]+)/);
            if (m) lang = m[1];
        }
        const pre = block.querySelector('pre');
        const code = (pre ? pre.innerText : block.innerText).replace(/\s+$/, '');
        block.replaceWith(fence(lang, code));
    });
    clone.querySelectorAll('pre').forEach(pre => {
        pre.replaceWith(fence('', (pre.innerText || '').replace(/\s+$/, '')));
    });
    clone.querySelectorAll('code').forEach(c => {
        if (!c.closest('pre')) c.replaceWith(document.createTextNode('`' + c.innerText + '`'));
    });
    clone.querySelectorAll('button, [class*="copy"], [class*="download"]').forEach(e => e.remove());
    clone.style.position = 'fixed';
    clone.style.left = '-99999px';
    clone.style.top = '0';
    clone.style.width = '800px';
    document.body.appendChild(clone);
    let text = '';
    try { text = clone.innerText || ''; } finally { clone.remove(); }
    return text.replace(/\n{3,}/g, '\n\n').trim();
}
"""

JS_EXTRACT_LAST = (
    JS_NODE_TO_MD
    + JS_PICK_NODES
    + """
const nodes = pickNodes(%s);
if (!nodes.length) return null;   // ainda pensando: sem resposta para extrair
return nodeToMarkdown(nodes[nodes.length - 1]);
"""
    % MESSAGE_SELECTORS
)

# Captura as mensagens ATUALMENTE renderizadas (a lista é virtual: só o que está
# visível existe no DOM). Assistente = tem .ds-assistant-message-main-content.
JS_CAPTURE_VISIBLE = (
    JS_NODE_TO_MD
    + """
const out = [];
document.querySelectorAll('.ds-message').forEach(m => {
    const assist = m.querySelector('.ds-assistant-message-main-content');
    if (assist) {
        const md = nodeToMarkdown(assist);
        if (md) out.push({ role: 'assistant', content: md });
    } else {
        const t = (m.innerText || '').trim();
        if (t) out.push({ role: 'user', content: t });
    }
});
return out;
"""
)

JS_SCROLL_CHAT = """
const box = document.querySelector('.ds-virtual-list, [class*="scroll-area"], [class*="conversation"]')
         || document.scrollingElement;
if (!box) return null;
const mode = arguments[0];
if (mode === 'top') box.scrollTop = 0;
else if (mode === 'down') box.scrollTop = box.scrollTop + box.clientHeight * 0.8;
return { top: box.scrollTop, height: box.scrollHeight, client: box.clientHeight };
"""

# A textarea do DeepSeek é controlada pelo React: usa-se o setter nativo do
# prototype + evento 'input', senão o React ignora a mudança direta do value.
JS_SET_INPUT = r"""
const el = arguments[0], val = arguments[1];
const proto = el.tagName === 'TEXTAREA'
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
el.focus();
setter.call(el, val);
el.dispatchEvent(new Event('input', { bubbles: true }));
"""

# Quando a resposta é longa demais, o DeepSeek corta e põe um botão "Continuar"
# no fim da mensagem. Sem clicar nele, a resposta fica pela metade.
#
# DOM conferido no navegador (DevTools, 2026-09-15):
#   <div role="button" class="ds-button ds-button--outlinedNeutral …" tabindex="0">
#     <span class="ds-button__content">Continuar</span>
#
# Casa pelo TEXTO, não pela classe: as classes do DeepSeek são geradas e mudam
# a cada build (`_6eef0b0`), o rótulo não. O botão primário é excluído porque é
# o de enviar/parar — esse nunca deve ser clicado por engano.
JS_BOTAO_CONTINUAR = """
function botaoContinuar() {
    const ALVOS = ['continuar', 'continue', '\\u7ee7\\u7eed'];
    // Uma linha só: string JS entre aspas simples não pode quebrar linha, e o
    // SyntaxError fazia todo script que inclui este trecho falhar calado.
    const finais = Array.from(document.querySelectorAll(
        '.ds-assistant-message-main-content, .ds-markdown, .assistant-message-content, '
        + '.markdown-body, .prose'))
        .filter(el => !el.closest('.ds-think-content'));
    const ultimoFinal = finais[finais.length - 1];
    if (!ultimoFinal) return null;
    for (const b of document.querySelectorAll('div[role="button"], button')) {
        if (b.closest('.ds-think-content')) continue;
        const depoisDoFinal = ultimoFinal.compareDocumentPosition(b)
            & Node.DOCUMENT_POSITION_FOLLOWING;
        if (!depoisDoFinal) continue;
        const cls = typeof b.className === 'string' ? b.className : '';
        if (/ds-button--primary/.test(cls)) continue;
        const t = (b.innerText || '').trim().toLowerCase();
        if (ALVOS.includes(t) && b.offsetParent !== null) return b;
    }
    return null;
}
"""

# O clique tem que ser o do SELENIUM, não o do JS.
#
# `el.click()` em JavaScript dispara um evento sintético, e o React desta página
# escuta pointerdown/mousedown — ele simplesmente ignora. Confirmado no DeepSeek
# real: achar o botão por JS funciona, clicar por JS não faz nada. O clique do
# Selenium é nativo do navegador e aciona o handler de verdade.
#
# XPath validado em uso real: pega o <span> pelo rótulo e sobe para o
# div[role=button] que é o pai direto dele.
XPATH_CONTINUAR = (
    "//*[self::button or @role='button']"
    "[.//*[contains(normalize-space(.),'Continuar') or"
    " contains(normalize-space(.),'Continue') or contains(normalize-space(.),'继续')]"
    "][not(ancestor::*[contains(@class,'ds-think-content')])]"
)

# Só para o FALLBACK, quando o clique nativo não dá (botão coberto por outro
# elemento, por exemplo). Melhor tentar do que desistir da resposta.
JS_CLICAR_CONTINUAR = (
    JS_BOTAO_CONTINUAR
    + """
const b = botaoContinuar();
if (!b) return false;
b.click();
return true;
"""
)

JS_MARCAR_REGENERAR_PARADO = r"""
const nodes = Array.from(document.querySelectorAll('*')).filter(el => {
    return el.offsetParent !== null
        && (el.innerText || el.textContent || '').trim().toLowerCase() === 'parado';
});
if (!nodes.length) return false;

let node = nodes[nodes.length - 1];
for (let i = 0; i < 12 && node; i++, node = node.parentElement) {
    const buttons = Array.from(node.querySelectorAll('button, [role="button"]'))
        .filter(el => el.offsetParent !== null)
        .filter(el => !/(copiar|copy|baixar|download)/i.test(
            (el.getAttribute('aria-label') || '') + ' ' +
            (el.innerText || el.textContent || '')));
    if (buttons.length >= 2) {
        buttons[1].setAttribute('data-regenerar-parado', 'true');
        return true;
    }
}
return false;
"""

MAX_REGENERAR_PARADO = 3
SEND_CONFIRM_TIMEOUT = 2
SEND_RETRY_TIMEOUT = 8

# Verdadeiro enquanto o DeepSeek ainda gera. Enquanto gera, o botão de enviar
# vira "parar" (ícone de quadrado). Vários sinais porque o DOM muda com o tempo.
JS_IS_GENERATING = (
    JS_BOTAO_CONTINUAR
    + """
// "Continuar" na tela = resposta cortada, ainda não acabou. Sem isto o app
// concluiria o turno no intervalo entre o corte e o clique — a página fica
// ociosa ali, e a resposta voltaria pela metade.
if (botaoContinuar()) return true;

const byLabel = document.querySelector(
    '[aria-label*="Stop" i], [aria-label*="Parar" i], [class*="stop-btn"], [class*="ds-stop"]');
if (byLabel && byLabel.offsetParent !== null) return true;

// O botão primário troca o ícone: a seta (enviar) começa em "M8..." e o
// quadrado (parar) começa em "M2..." — conferido no DOM real (2026-10-16).
// Tem que ser o primário do COMPOSER: o primeiro da página pode ser outro, e
// aí a leitura dava sempre null.
const PRIMARIO = 'div[role="button"].ds-button--primary, button.ds-button--primary';
let btn = null;
for (let el = document.querySelector('textarea'); el && !btn; el = el.parentElement)
    btn = el.querySelector(PRIMARIO);
btn = btn || document.querySelector(PRIMARIO);
if (btn) {
    const p = btn.querySelector('svg path');
    const d = p ? (p.getAttribute('d') || '') : '';
    if (d.startsWith('M2')) return true;   // quadrado = parar = gerando
    if (d.startsWith('M8')) return false;  // seta = enviar = ocioso
}
return null;  // desconhecido -> quem chama decide pela estabilidade
"""
)

# DOM real do chat.deepseek.com:
#   toggles: <div tabindex="0" aria-pressed="true" class="ds-toggle-button ...--selected">
JS_FIND_TOGGLE = """
function findToggle(names) {
    const cands = document.querySelectorAll(
        '[class*="ds-toggle-button"], div[role="button"], button, [aria-pressed]');
    let best = null;
    for (const el of cands) {
        const t = (el.innerText || '').trim().toLowerCase();
        if (!t || t.length > 30) continue;
        if (!names.some(n => t === n || t.startsWith(n))) continue;
        // O mais interno vence: o rótulo pode repetir em contêineres acima.
        if (!best || best.contains(el)) best = el;
    }
    return best;
}

function stateOf(el) {
    if (!el) return null;
    const pressed = el.getAttribute('aria-pressed');
    if (pressed !== null) return pressed === 'true';
    const cls = typeof el.className === 'string' ? el.className : '';
    return /(--selected|--active|is-active|checked)/i.test(cls);
}

function isDisabled(el) {
    if (!el) return true;
    const cls = typeof el.className === 'string' ? el.className : '';
    return el.hasAttribute('disabled')
        || el.getAttribute('aria-disabled') === 'true'
        || /--disabled/i.test(cls);
}
"""

JS_READ_STATE = (
    JS_FIND_TOGGLE
    + """
const dt = findToggle(['deepthink', 'pensamento profundo', 'deep think']);
const se = findToggle(['search', 'pesquisa', 'busca']);
return {
    deepthink: stateOf(dt),
    search: stateOf(se),
    deepthink_available: !!dt && !isDisabled(dt),
    search_available: !!se && !isDisabled(se)
};
"""
)

# Clica no toggle localizado pelo texto (fallback quando o XPath do config falha).
JS_CLICK_TOGGLE = (
    JS_FIND_TOGGLE
    + """
const el = findToggle(arguments[0]);
if (!el || isDisabled(el)) return false;
el.click();
return true;
"""
)

# Os itens da barra lateral são <a href="/a/chat/s/ID">, então dá para pegar
# título e URL sem clicar em cada um.
JS_LIST_CONVERSATIONS = r"""
const out = [];
document.querySelectorAll('a[href*="/a/chat/s/"]').forEach(a => {
    const lines = (a.innerText || '').trim().split(String.fromCharCode(10));
    const t = (lines[0] || '').trim();
    const href = a.getAttribute('href') || '';
    if (t && href) out.push({ title: t.slice(0, 80), url: new URL(href, location.origin).href });
});
return out;
"""

JS_NEW_CHAT = (
    "const b = Array.from(document.querySelectorAll('div'))"
    ".find(el => el.innerText === 'New chat' || el.innerText === 'Nova conversa');"
    "if (b) { b.click(); return true; } return false;"
)

# O DOM não é fonte confiável do texto final: numa conversa longa a bolha em
# streaming parou de ser redesenhada logo no começo (`{"res`) enquanto o site
# terminava a resposta — confirmado em 2026-10-16 comparando a captura do app
# com o histórico do servidor. A API que a própria página usa para carregar o
# histórico devolve o Markdown cru de cada mensagem e o status da geração.
#
# Resposta da API (conferida no site real):
#   data.biz_data.chat_session.current_message_id   folha do ramo exibido
#   data.biz_data.chat_messages[]: message_id, parent_id, role USER|ASSISTANT,
#       status (FINISHED, …), accumulated_token_usage, incomplete_message,
#       fragments[]: {type: REQUEST|THINK|RESPONSE|…, content}
#
# Segue o ramo atual da folha até a raiz, para ignorar respostas regeneradas.
# O texto do usuário volta só como tamanho em UTF-16 (o mesmo `length` do JS),
# porque pode ter megabytes e só serve para conferir se chegou inteiro.
JS_API_ESTADO = r"""
const done = arguments[arguments.length - 1];
const incluirTexto = !!arguments[0];
(async () => {
    try {
        const m = location.pathname.match(/\/s\/([^/?#]+)/);
        if (!m) return done({sem_conversa: true});
        let token = '';
        try { token = JSON.parse(localStorage.getItem('userToken') || '{}').value || ''; } catch (e) {}
        const resp = await fetch(
            '/api/v0/chat/history_messages?chat_session_id=' + encodeURIComponent(m[1]),
            {headers: token ? {authorization: 'Bearer ' + token} : {}, cache: 'no-store'});
        if (!resp.ok) return done({erro: 'HTTP ' + resp.status});
        const corpo = await resp.json();
        const dados = corpo && corpo.data && corpo.data.biz_data;
        if (!dados || !Array.isArray(dados.chat_messages))
            return done({erro: 'formato inesperado da API de histórico'});
        const msgs = dados.chat_messages;
        const porId = new Map(msgs.map(x => [x.message_id, x]));
        let id = dados.chat_session && dados.chat_session.current_message_id;
        if (!porId.has(id)) id = msgs.length ? msgs[msgs.length - 1].message_id : null;
        const ramo = [], vistos = new Set();
        while (id != null && porId.has(id) && !vistos.has(id)) {
            vistos.add(id);
            ramo.push(porId.get(id));
            id = porId.get(id).parent_id;
        }
        ramo.reverse();
        const texto = (msg, tipo) => (msg.fragments || [])
            .filter(f => f.type === tipo).map(f => f.content || '').join('');
        let iu = -1;
        for (let i = ramo.length - 1; i >= 0; i--) if (ramo[i].role === 'USER') { iu = i; break; }
        const usuario = iu >= 0 ? ramo[iu] : null;
        const respostas = ramo.slice(iu + 1).filter(x => x.role === 'ASSISTANT');
        const ultima = respostas[respostas.length - 1] || null;
        const corpoResposta = respostas.map(r => texto(r, 'RESPONSE')).join('');
        const pensamento = respostas.map(r => texto(r, 'THINK')).join('');
        done({
            sessao: m[1],
            max_id: msgs.reduce((a, x) => Math.max(a, x.message_id || 0), 0),
            usuario: usuario ? {
                id: usuario.message_id,
                tamanho: texto(usuario, 'REQUEST').length,
            } : null,
            resposta: ultima ? {
                id: ultima.message_id,
                status: String(ultima.status || ''),
                tamanho: corpoResposta.length,
                pensamento: pensamento.length,
                texto: incluirTexto ? corpoResposta : null,
                tokens: ultima.accumulated_token_usage || null,
                incompleta: ultima.incomplete_message || null,
            } : null,
        });
    } catch (e) { done({erro: String(e)}); }
})();
"""

# Avisos que o site mostra fora das mensagens (toast, alerta). Entram na
# mensagem de erro: quando o site recusa um envio, o motivo costuma estar ali.
JS_AVISOS_SITE = r"""
const out = [];
document.querySelectorAll(
    '[role="alert"], [class*="toast"], [class*="Toast"], [class*="notification"],'
    + ' [class*="message-error"], [class*="ds-notice"]').forEach(el => {
    if (el.offsetParent === null) return;
    const t = (el.innerText || '').trim();
    if (t && t.length < 400 && !out.includes(t)) out.push(t);
});
return out;
"""

STATUS_PRONTA = {"FINISHED"}
STATUS_CORTADA = {"INCOMPLETE"}
STATUS_GERANDO = {"", "WIP", "PENDING", "GENERATING", "IN_PROGRESS", "STREAMING"}
# Palavras que, num aviso do site ou num status desconhecido, indicam limite de
# tamanho — de mensagem, de resposta ou do contexto da conversa. "limit" sozinho
# fica de fora: "rate limit" é excesso de pedidos, não de tamanho.
# Recusa real do site com 3 milhões de caracteres (2026-10-16): toast
# "Conteúdo muito longo (13%). Encurte e tente novamente." e "Excedido em 13%".
PISTAS_TAMANHO = ("length", "too long", "too large", "exceed", "shorten",
                  "muito longo", "muito longa", "longa demais", "longo demais",
                  "grande demais", "excedido", "encurte", "comprimento",
                  "context", "contexto", "tokens", "incomplete", "长")

# Intervalo entre consultas à API enquanto o DOM está parado. O histórico de uma
# conversa longa tem centenas de KB; consultar a cada leitura do DOM seria
# desperdício, e só interessa quando a tela parou de mudar.
API_INTERVALO = 3.0
# Texto parado na tela por este tempo já justifica perguntar à API se acabou.
API_DOM_PARADO = 2.5


def normalizar_quebras(texto: str) -> str:
    """Quebras de linha como a caixa de texto do navegador guarda: só LF.

    O `<textarea>` troca CRLF e CR por LF ao receber o valor. Saída de comando
    no Windows vem com CRLF; sem normalizar antes, a conferência "o campo
    aceitou o texto inteiro?" via diferença onde não havia e recusava o envio
    (conferido no Chrome em 2026-10-20).
    """
    return texto.replace("\r\n", "\n").replace("\r", "\n")


class ErroTamanho(RuntimeError):
    """O site não aceitou ou cortou algo por tamanho.

    `lado` é "envio" (a mensagem não chegou inteira ao DeepSeek) ou "resposta"
    (a resposta foi cortada pelo limite de saída do site). Os tamanhos estão em
    caracteres; `parcial` guarda o que chegou da resposta cortada.
    """

    def __init__(self, lado: str, mensagem: str, *, enviado: int | None = None,
                 recebido: int | None = None, parcial: str = ""):
        super().__init__(mensagem)
        self.lado = lado
        self.enviado = enviado
        self.recebido = recebido
        self.parcial = parcial


def tamanho_js(texto: str) -> int:
    """Tamanho como o `String.length` do JS conta: unidades UTF-16."""
    return len((texto or "").encode("utf-16-le")) // 2


def _menciona_tamanho(texto: str) -> bool:
    baixo = (texto or "").lower()
    return any(pista in baixo for pista in PISTAS_TAMANHO)


def _n(valor) -> str:
    """Número com separador de milhar brasileiro."""
    return f"{int(valor or 0):,}".replace(",", ".")


def avaliar_estado_api(estado: dict, id_antes: int, enviado: str):
    """Interpreta o histórico do servidor para a mensagem recém-enviada.

    Devolve `(fase, resposta)`, com `fase` em:
      "aguardando"   o servidor ainda não registrou a mensagem ou a resposta
      "gerando"      a resposta está sendo escrita
      "pronta"       terminou normalmente
      "cortada"      terminou cortada por tamanho
      "desconhecida" status que este app não conhece

    Levanta `ErroTamanho("envio")` quando o site guardou menos texto do que foi
    enviado: a resposta que vier depois é a um pedido truncado.
    """
    usuario = estado.get("usuario") or {}
    resposta = estado.get("resposta") or {}
    id_usuario = usuario.get("id") or 0
    if id_usuario <= id_antes:
        return "aguardando", None

    # O site pode aparar espaços nas pontas e trocar \r\n por \n; isso não é
    # corte. Corte de limite leva um pedaço grande, então a folga é pequena.
    esperado = tamanho_js((enviado or "").replace("\r\n", "\n").strip())
    guardado = usuario.get("tamanho") or 0
    if esperado - guardado > max(16, esperado // 1000):
        raise ErroTamanho(
            "envio",
            f"O DeepSeek guardou só {_n(guardado)} dos {_n(esperado)} caracteres "
            "enviados: a mensagem foi cortada pelo site na ida. A resposta "
            "seria a um pedido incompleto, por isso foi descartada.",
            enviado=esperado, recebido=guardado)

    if (resposta.get("id") or 0) <= id_usuario:
        return "aguardando", None
    status = (resposta.get("status") or "").strip().upper()
    if status in STATUS_GERANDO:
        return "gerando", resposta
    if status in STATUS_PRONTA:
        return "pronta", resposta
    if status in STATUS_CORTADA or _menciona_tamanho(status):
        return "cortada", resposta
    return "desconhecida", resposta


def resposta_tem_cerca_aberta(texto: str) -> bool:
    """Retorna se o streaming terminou dentro de um bloco Markdown."""
    return (texto or "").count("```") % 2 == 1

TOGGLE_NAMES = {
    "deepthink": ["deepthink", "pensamento profundo", "deep think"],
    "search": ["search", "pesquisa", "busca"],
}


class DeepSeekWrapper:
    def __init__(self, config_path="config.json"):
        self.config = self._load_config(config_path)
        self.driver = None
        self.wait = None
        self.is_connected = False
        # True quando o navegador abriu mas a página está no login: o Chrome
        # fica aberto para o usuário entrar na conta e mandar conectar de novo.
        self.needs_login = False
        self._deepthink_state = False
        self._search_state = False
        # O driver é tocado pela thread de envio e pela thread de polling.
        self._lock = threading.RLock()
        # Como a última resposta foi obtida: fonte ("api" ou "dom"), status do
        # site, tokens da conversa e tamanhos enviado/guardado.
        self.ultima_captura = {}
        # Avisos do site vistos durante o último envio (o toast some rápido).
        self._avisos_envio = []

    def _load_config(self, config_path):
        base_dir = str(raiz_recursos())
        for path in (os.path.join(base_dir, config_path), config_path,
                     os.path.join(os.getcwd(), config_path)):
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {config_path}")

    def _get_selector(self, key):
        sels = self.config["selectors"]
        if key in sels.get("css", {}):
            return sels["css"][key], By.CSS_SELECTOR
        if key in sels.get("xpath", {}):
            return sels["xpath"][key], By.XPATH
        raise KeyError(f"Seletor '{key}' não encontrado")

    def _js(self, script, *args, default=None):
        if not self.driver:
            return default
        try:
            with self._lock:
                return self.driver.execute_script(script, *args)
        except Exception:
            return default

    # ---------------- ciclo de vida ----------------

    def open(self, headless=False):
        """Abre o Chrome e espera a página do chat ficar pronta.

        Se a caixa de texto não aparecer dentro de `login_wait`, o navegador é
        MANTIDO aberto e `needs_login` vira True — é o caso do primeiro uso, em
        que o site mostra a tela de login. O usuário entra na conta e chama
        `open()` de novo: o driver já existente é reaproveitado.
        """
        if self.driver is None:
            options = Options()
            if headless:
                options.add_argument("--headless")
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            # Perfil próprio (login salvo entre execuções): na pasta do
            # código-fonte, ou nos dados do usuário na versão instalada.
            options.add_argument(f"--user-data-dir={pasta_perfil_chrome()}")

            try:
                # Sem janela de console do chromedriver no app sem console.
                servico = Service(popen_kw={
                    "creation_flags": getattr(subprocess, "CREATE_NO_WINDOW", 0)})
                self.driver = webdriver.Chrome(options=options, service=servico)
                self.wait = WebDriverWait(self.driver, self.config["timeouts"]["element_wait"])
            except Exception as e:
                print(f"Erro ao abrir o navegador: {type(e).__name__} - {e}")
                self.driver = None
                return False

        try:
            with self._lock:
                if "deepseek.com" not in (self.driver.current_url or ""):
                    self.driver.get(self.config["url"])
        except Exception as e:
            # Janela fechada na mão, driver morto: joga fora e recomeça do zero.
            print(f"Sessão do navegador perdida: {type(e).__name__} - {e}")
            self.close()
            return False

        return self._wait_ready()

    def _wait_ready(self):
        selector, by = self._get_selector("page_ready")
        timeout = self.config["timeouts"].get("login_wait", 25)
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector)))
        except TimeoutException:
            self.needs_login = True
            self.is_connected = False
            return False
        except Exception as e:
            print(f"Erro ao preparar a página: {type(e).__name__} - {e}")
            self.close()
            return False

        self.needs_login = False
        self.is_connected = True
        self._dismiss_popups()
        state = self.read_state()
        self._deepthink_state = bool(state.get("deepthink"))
        self._search_state = bool(state.get("search"))
        return True

    def _dismiss_popups(self):
        try:
            selector, by = self._get_selector("dismiss_popup")
            self.driver.find_element(by, selector).click()
            time.sleep(0.5)
        except Exception:
            pass

    def close(self):
        with self._lock:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
            self.is_connected = False
            self.needs_login = False

    # ---------------- controles da página ----------------

    def _click_btn(self, key, timeout=6):
        # Timeout curto: estes controles ou já estão na tela ou não existem
        # naquele contexto, dependendo do estado da conversa.
        try:
            selector, by = self._get_selector(key)
            with self._lock:
                WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((by, selector))
                ).click()
            return True
        except TimeoutException:
            return False
        except Exception as e:
            print(f"Erro em {key}: {e}")
            return False

    def _toggle(self, key, names):
        ok = self._click_btn(key)
        if not ok:
            # XPath do config falhou: tenta localizar pelo texto do botão.
            ok = bool(self._js(JS_CLICK_TOGGLE, names, default=False))
        if ok:
            time.sleep(0.4)
        return ok

    def toggle_deepthink(self):
        ok = self._toggle("deepthink_toggle", TOGGLE_NAMES["deepthink"])
        if ok:
            self._deepthink_state = bool(self.read_state().get("deepthink"))
        return ok

    def toggle_search(self):
        ok = self._toggle("search_toggle", TOGGLE_NAMES["search"])
        if ok:
            self._search_state = bool(self.read_state().get("search"))
        return ok

    def read_state(self):
        """Lê DeepThink e Search da página numa única chamada JS."""
        state = self._js(JS_READ_STATE, default=None) or {}
        if state.get("deepthink") is None:
            state["deepthink"] = self._deepthink_state
        if state.get("search") is None:
            state["search"] = self._search_state
        self._deepthink_state = bool(state["deepthink"])
        self._search_state = bool(state["search"])
        return state

    # ---------------- conversas ----------------

    def current_url(self):
        if not self.driver:
            return None
        try:
            with self._lock:
                return self.driver.current_url
        except Exception:
            return None

    def list_conversations(self, limit=100):
        """Lista as conversas da barra lateral: [{title, url}]."""
        if not self.is_connected:
            return []
        convs = self._js(JS_LIST_CONVERSATIONS, default=[]) or []
        seen, unique = set(), []
        for c in convs:
            if c["url"] not in seen:
                seen.add(c["url"])
                unique.append(c)
        return unique[:limit]

    def new_chat(self):
        """Envia Ctrl+J para iniciar uma conversa nova no DeepSeek."""
        driver = self.driver
        if not self.is_connected or driver is None:
            return False
        try:
            url_anterior = driver.current_url
        except Exception as e:
            print(f"Não consegui conferir a conversa atual: {e}")
            return False

        def conversa_nova(driver):
            if driver.current_url != url_anterior:
                return True
            mensagens = self._js(JS_CAPTURE_VISIBLE, default=None)
            return mensagens is not None and not any(
                mensagem["role"] == "user" for mensagem in mensagens)

        try:
            with self._lock:
                (ActionChains(driver)
                 .key_down(Keys.CONTROL)
                 .send_keys("j")
                 .key_up(Keys.CONTROL)
                 .perform())
            try:
                WebDriverWait(driver, 3).until(conversa_nova)
                return True
            except TimeoutException:
                pass
        except Exception as e:
            print(f"Falha ao enviar Ctrl+J para nova conversa: {e}")

        # Mantém compatibilidade caso o atalho deixe de ser suportado pelo site.
        ok = bool(self._js(JS_NEW_CHAT, default=False))
        if not ok:
            return False
        try:
            WebDriverWait(driver, 3).until(conversa_nova)
            return True
        except TimeoutException:
            return False

    def open_conversation(self, url):
        if not self.is_connected:
            return False
        try:
            with self._lock:
                self.driver.get(url)
            selector, by = self._get_selector("input_box")
            self.wait.until(EC.presence_of_element_located((by, selector)))
            self._dismiss_popups()
            return True
        except Exception as e:
            print(f"Erro ao abrir conversa: {e}")
            return False

    def extract_history(self, max_steps=60):
        """Lê o histórico da conversa aberta como [{role, content}, ...].

        A lista do DeepSeek é virtual (só o visível existe no DOM), então rola do
        topo até o fim juntando mensagens únicas em ordem. Best-effort.
        """
        if not self.is_connected:
            return []
        result, seen = [], set()

        def collect():
            for m in (self._js(JS_CAPTURE_VISIBLE, default=[]) or []):
                key = (m["role"], m["content"][:120])
                if key not in seen:
                    seen.add(key)
                    result.append(m)

        try:
            self._js(JS_SCROLL_CHAT, "top")
            time.sleep(0.6)
            collect()
            last_top = -1
            for _ in range(max_steps):
                info = self._js(JS_SCROLL_CHAT, "down")
                time.sleep(0.35)
                collect()
                if not info:
                    break
                if info["top"] <= last_top or info["top"] + info["client"] >= info["height"] - 4:
                    break
                last_top = info["top"]
        except Exception as e:
            print(f"Erro ao ler histórico: {e}")
        return result

    # ---------------- anexos ----------------

    def anexar(self, caminho: str) -> bool:
        """Sobe um arquivo de verdade para o DeepSeek pelo <input type=file>.

        É assim que imagem entra na conversa: não dá para colar imagem no texto,
        ela precisa virar upload. O input costuma estar escondido, mas
        `send_keys` funciona mesmo em elemento invisível.
        """
        if not self.is_connected or not self.driver:
            raise RuntimeError("Navegador não conectado.")
        if not os.path.isfile(caminho):
            raise RuntimeError(f"Arquivo não encontrado: {caminho}")
        try:
            selector, by = self._get_selector("attach_button")
            with self._lock:
                inputs = self.driver.find_elements(by, selector)
                if not inputs:
                    print("Nenhum input[type=file] na página.")
                    return False
                inputs[-1].send_keys(os.path.abspath(caminho))
            # Dá tempo do upload aparecer: enviar antes disso manda sem o anexo.
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"Erro ao anexar: {e}")
            return False

    # ---------------- resposta cortada ----------------

    def clicar_continuar(self) -> bool:
        """Clica no "Continuar" que aparece quando a resposta é cortada.

        Devolve True se clicou. Tenta o clique nativo do Selenium primeiro — é o
        único que o React desta página respeita (ver comentário do XPath).
        """
        if not self.driver:
            return False
        try:
            with self._lock:
                self.driver.implicitly_wait(0)
                try:
                    botoes = self.driver.find_elements(By.XPATH, XPATH_CONTINUAR)
                    for botao in botoes:
                        try:
                            if not botao.is_displayed():
                                continue
                            botao.click()
                            return True
                        except Exception:
                            # Coberto, fora da tela ou já trocado pelo React:
                            # tenta o próximo, e no fim cai no fallback por JS.
                            continue
                finally:
                    self.driver.implicitly_wait(
                        self.config["timeouts"].get("implicit", 10))
        except Exception as e:
            print(f"Erro ao procurar 'Continuar': {e}")

        return bool(self._js(JS_CLICAR_CONTINUAR, default=False))

    def tem_continuar(self) -> bool:
        return bool(self._js(JS_BOTAO_CONTINUAR + "return !!botaoContinuar();",
                             default=False))

    def clicar_regenerar_parado(self) -> bool:
        if not self.driver:
            return False
        try:
            if not self._js(JS_MARCAR_REGENERAR_PARADO, default=False):
                return False
            with self._lock:
                self.driver.implicitly_wait(0)
                try:
                    botao = self.driver.find_element(
                        By.CSS_SELECTOR, '[data-regenerar-parado="true"]')
                    if not botao.is_displayed():
                        return False
                    botao.click()
                    return True
                finally:
                    self.driver.implicitly_wait(
                        self.config["timeouts"].get("implicit", 10))
        except Exception as e:
            print(f"Erro ao regenerar resposta parada: {e}")
            return False
        finally:
            self._js(
                "document.querySelectorAll('[data-regenerar-parado=\"true\"]').forEach("
                "el => el.removeAttribute('data-regenerar-parado'));",
                default=None)

    # ---------------- mensagens ----------------

    def _extract_last(self):
        return self._js(JS_EXTRACT_LAST, default=None)

    def _estado_api(self, incluir_texto=False):
        """Histórico da conversa segundo o servidor, ou None se não deu."""
        if not self.driver:
            return None
        try:
            with self._lock:
                self.driver.set_script_timeout(60)
                estado = self.driver.execute_async_script(
                    JS_API_ESTADO, bool(incluir_texto))
        except Exception as e:
            print(f"API de histórico indisponível: {type(e).__name__} - {e}")
            return None
        if not isinstance(estado, dict):
            return None
        if estado.get("erro"):
            print(f"API de histórico indisponível: {estado['erro']}")
            return None
        return estado

    def avisos_site(self) -> list[str]:
        return [str(t) for t in (self._js(JS_AVISOS_SITE, default=[]) or [])]

    def extract_last_response(self):
        """Rele a última resposta sem enviar outra mensagem.

        Prefere o texto guardado pelo servidor; o DOM fica de reserva.
        """
        estado = self._estado_api(incluir_texto=True) or {}
        texto = (estado.get("resposta") or {}).get("texto")
        return texto or self._extract_last()

    def _visible_user_messages(self):
        messages = self._js(JS_CAPTURE_VISIBLE, default=None)
        if messages is None:
            return None
        return [
            str(message.get("content") or "").strip()
            for message in messages
            if message.get("role") == "user"
        ]

    def _submission_confirmed(
        self, input_box, text, previous_messages, generating_before
    ):
        try:
            value = input_box.get_property("value")
        except Exception:
            value = None
        if text.strip() and value == "":
            return True

        current_messages = self._visible_user_messages()
        if current_messages is not None and previous_messages is not None:
            if len(current_messages) > len(previous_messages):
                last_message = current_messages[-1]
                if not text.strip() or text.strip() in last_message:
                    return True

        generating_now = self._js(JS_IS_GENERATING, default=None)
        return generating_now is True and generating_before is not True

    def _wait_for_submission(
        self, input_box, text, previous_messages, generating_before, timeout
    ):
        deadline = time.monotonic() + timeout
        while True:
            if self._submission_confirmed(
                input_box, text, previous_messages, generating_before
            ):
                return True
            # O toast de recusa some em segundos: guarda enquanto está na tela.
            for aviso in self.avisos_site():
                if aviso not in self._avisos_envio:
                    self._avisos_envio.append(aviso)
            if any(_menciona_tamanho(a) for a in self._avisos_envio):
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.2, remaining))

    def _submit_message(self, input_box, text):
        driver = self.driver
        if driver is None:
            raise RuntimeError("Navegador não conectado.")
        text = normalizar_quebras(text)
        previous_messages = self._visible_user_messages()
        generating_before = self._js(JS_IS_GENERATING, default=None)
        self._avisos_envio = []
        with self._lock:
            input_box.clear()
            driver.execute_script(JS_SET_INPUT, input_box, text)
            no_campo = input_box.get_property("value") or ""
            if no_campo != text:
                raise self._erro_envio(
                    "O campo de mensagem do DeepSeek não aceitou o texto inteiro "
                    f"(ficou com {_n(len(no_campo))} de {_n(len(text))} "
                    "caracteres).", text)
            input_box.send_keys(Keys.END)
            try:
                input_box.send_keys(Keys.RETURN)
            except Exception:
                pass

        send_wait = min(
            10, self.config["timeouts"].get("element_wait", 10)
        )
        if self._wait_for_submission(
            input_box, text, previous_messages, generating_before,
            SEND_CONFIRM_TIMEOUT
        ):
            return
        if any(_menciona_tamanho(a) for a in self._avisos_envio):
            erro = self._erro_envio("O DeepSeek recusou a mensagem por tamanho.", text)
            # Não deixa megabytes parados no campo do site.
            self._js(JS_SET_INPUT, input_box, "")
            raise erro

        send_selector, send_by = self._get_selector("send_button")
        try:
            with self._lock:
                WebDriverWait(driver, send_wait).until(
                    EC.element_to_be_clickable((send_by, send_selector))
                ).click()
        except Exception as error:
            raise self._erro_envio(
                "O DeepSeek não confirmou o envio por Enter nem disponibilizou "
                "o botão Enviar.", text) from error

        if not self._wait_for_submission(
            input_box, text, previous_messages, generating_before,
            min(send_wait, SEND_RETRY_TIMEOUT)
        ):
            raise self._erro_envio(
                "O DeepSeek não confirmou o envio da mensagem. "
                "O texto permaneceu no campo e não apareceu na conversa.", text)

    def _erro_envio(self, motivo: str, text: str) -> RuntimeError:
        """Erro de envio com o tamanho da mensagem e o que o site avisou.

        Vira `ErroTamanho` quando o aviso do site fala de tamanho; senão o
        tamanho vai junto mesmo assim, para quem lê poder julgar.
        """
        tamanho = tamanho_js(text)
        detalhe = f"{motivo} Mensagem de {_n(tamanho)} caracteres."
        avisos = list(getattr(self, "_avisos_envio", []))
        avisos += [a for a in self.avisos_site() if a not in avisos]
        if avisos:
            detalhe += " Aviso do site: " + " | ".join(avisos)
        if any(_menciona_tamanho(aviso) for aviso in avisos):
            return ErroTamanho("envio", detalhe, enviado=tamanho)
        return RuntimeError(detalhe)

    def send_message(self, text, on_update=None, on_sent=None):
        """Envia `text` e devolve a resposta em Markdown.

        `on_update(parcial)` é chamado durante a geração, para stream na UI.
        `on_sent()` só é chamado após confirmar que o DeepSeek aceitou a mensagem.
        """
        if not self.is_connected or not self.driver:
            raise RuntimeError("Navegador não conectado.")
        text = normalizar_quebras(text or "")
        wait = self.wait
        if wait is None:
            raise RuntimeError("Navegador ainda não está pronto para enviar.")

        # Texto da última resposta ANTES de enviar. Detectar por contagem de
        # mensagens falha na lista virtual do DeepSeek (só renderiza uma janela);
        # detectar pela MUDANÇA do texto é robusto.
        text_before = self._extract_last() or ""
        # Maior id de mensagem no servidor antes do envio: tudo acima dele é
        # desta rodada. Conversa nova (sem id na URL) começa do zero. Sem API,
        # a rodada inteira fica só no DOM.
        antes = self._estado_api()
        id_antes = None if antes is None else int(antes.get("max_id") or 0)
        self.ultima_captura = {"fonte": "dom", "enviado": tamanho_js(text)}

        input_selector, by = self._get_selector("input_box")
        try:
            with self._lock:
                input_box = wait.until(EC.presence_of_element_located((by, input_selector)))
            self._submit_message(input_box, text)
        except TimeoutException:
            raise RuntimeError("Campo de entrada não encontrado.")
        if on_sent:
            on_sent()
        return self._aguardar_resposta(text, text_before, id_antes, on_update)

    def _aguardar_resposta(self, text, text_before, id_antes, on_update):
        """Espera a resposta da mensagem que acabou de ser enviada.

        O DOM alimenta o streaming na tela e clica em "Continuar"/"Regenerar".
        Quem decide que acabou, e com qual texto, é a API do histórico: o DOM
        pode congelar no meio. Sem API, vale a heurística antiga de estabilidade.

        Não há prazo total — resposta grande pode demorar o quanto precisar. O
        que encerra por tempo é passar `response_wait` segundos sem progresso
        nenhum, nem na tela nem no servidor.
        """
        timeouts = self.config["timeouts"]
        sem_progresso_max = timeouts.get("response_wait", 300)
        # Heurística do DOM: o texto PARA DE CRESCER por `stable_seconds`
        # seguidos e o DOM confirma várias vezes que a geração acabou.
        interval = 0.6
        stable_needed = max(1, int(round(timeouts.get("stable_seconds", 5) / interval)))
        completion_needed = max(2, int(timeouts.get("completion_confirmations", 3)))
        unknown_completion_needed = max(
            completion_needed,
            int(timeouts.get("unknown_completion_confirmations", 8)))

        usar_api = id_antes is not None
        agora = time.monotonic()
        ultimo_progresso = dom_mudou_em = agora
        ultima_api, tamanho_api, api_aguardando_desde = 0.0, -1, None
        fase, resposta_api = "aguardando", None
        last_text, stable, idle_confirmations, seen_new = "", 0, 0, False
        # Pedaços já fechados por um "Continuar". Se a continuação vier numa
        # bolha NOVA, o _extract_last() passa a ver só ela — os pedaços anteriores
        # ficam guardados aqui e a resposta é remontada no fim.
        pedacos, regeneracoes = [], 0
        # "Continuar" sem teto fixo: para só quando cliques seguidos não fazem
        # a resposta crescer — aí o botão está preso, não há mais o que vir.
        continuar_sem_ganho, tamanho_no_continuar = 0, -1
        debug_stream = os.environ.get("DEEPSEEK_DEBUG") == "1"

        while True:
            if time.monotonic() - ultimo_progresso > sem_progresso_max:
                parcial = self._juntar(pedacos, last_text)
                raise RuntimeError(
                    f"O DeepSeek ficou {int(sem_progresso_max)}s sem avançar a "
                    f"resposta ({_n(len(parcial))} caracteres recebidos até aqui"
                    + (f"; status no site: {resposta_api.get('status')}"
                       if resposta_api else "")
                    + ").")
            time.sleep(interval)
            if debug_stream:
                print("[stream] extract:start", flush=True)
            current = self._extract_last() or ""
            if debug_stream:
                print(f"[stream] extract:end len={len(current)}", flush=True)

            regenerou = (regeneracoes < MAX_REGENERAR_PARADO
                         and self.clicar_regenerar_parado())
            if debug_stream:
                print(f"[stream] regenerar={regenerou} total={regeneracoes}",
                      flush=True)
            if regenerou:
                regeneracoes += 1
                last_text, stable, idle_confirmations = "", 0, 0
                ultimo_progresso = dom_mudou_em = time.monotonic()
                time.sleep(1.2)
                continue

            # Aguarda a RESPOSTA NOVA aparecer.
            if not seen_new and current and current != text_before:
                seen_new = True

            if seen_new and current and current != last_text:
                last_text = current
                stable = 0
                idle_confirmations = 0
                ultimo_progresso = dom_mudou_em = time.monotonic()
                if on_update:
                    try:
                        on_update(self._juntar(pedacos, current))
                    except Exception:
                        pass
            elif seen_new and current:
                stable += 1

            # Resposta longa demais: o site corta e mostra "Continuar". Clicar
            # é o que faz o resto vir — sem isso o texto para aqui, a página
            # fica ociosa e o app concluiria com metade da resposta.
            if ((seen_new or fase != "aguardando") and continuar_sem_ganho < 3
                    and self.clicar_continuar()):
                tamanho_atual = len(self._juntar(pedacos, last_text))
                continuar_sem_ganho = (continuar_sem_ganho + 1
                                       if tamanho_atual <= tamanho_no_continuar
                                       else 0)
                tamanho_no_continuar = tamanho_atual
                if last_text:
                    pedacos.append(last_text)
                last_text, stable, idle_confirmations = "", 0, 0
                ultimo_progresso = dom_mudou_em = time.monotonic()
                if on_update:
                    try:
                        on_update(self._juntar(pedacos, "") + "\n\n⏳ continuando…")
                    except Exception:
                        pass
                time.sleep(1.2)   # deixa a próxima parte começar a aparecer
                continue

            # Servidor: só quando a tela parou de mudar (ou ainda não mostrou
            # nada novo). É o que pega o DOM congelado no começo da resposta.
            agora = time.monotonic()
            if (usar_api and agora - dom_mudou_em >= API_DOM_PARADO
                    and agora - ultima_api >= API_INTERVALO):
                ultima_api = agora
                estado = self._estado_api()
                if estado is None:
                    usar_api = False
                else:
                    fase, resposta_api = avaliar_estado_api(estado, id_antes, text)
                    # Pensamento do DeepThink também é progresso: sem isso um
                    # raciocínio longo estouraria o tempo sem resposta.
                    andamento = ((resposta_api or {}).get("tamanho", 0)
                                 + (resposta_api or {}).get("pensamento", 0))
                    if resposta_api and andamento > tamanho_api:
                        tamanho_api = andamento
                        ultimo_progresso = agora
                    if debug_stream:
                        print(f"[stream] api fase={fase} resposta={resposta_api}",
                              flush=True)
                    if fase == "aguardando":
                        api_aguardando_desde = api_aguardando_desde or agora
                    else:
                        api_aguardando_desde = None
                    if fase in ("pronta", "desconhecida"):
                        texto = self._texto_final_api(id_antes, text)
                        if texto:
                            return texto
                        # Terminou sem texto de resposta no servidor (status
                        # novo, só raciocínio…): o DOM decide daqui em diante.
                        usar_api = False
                    elif fase == "cortada" and (continuar_sem_ganho >= 3
                                                or not self.tem_continuar()):
                        texto = self._texto_final_api(id_antes, text) or ""
                        motivo = resposta_api.get("incompleta")
                        raise ErroTamanho(
                            "resposta",
                            "A resposta passou do limite de saída do DeepSeek e "
                            f"foi cortada em {_n(len(texto))} caracteres "
                            f"(status {resposta_api.get('status')}"
                            + (f": {motivo}" if motivo else "")
                            + (f"; contexto com {_n(resposta_api['tokens'])} tokens"
                               if resposta_api.get("tokens") else "")
                            + ").",
                            recebido=len(texto), parcial=texto)

            # `generating` vem do DOM. Uma leitura isolada de ocioso pode ser
            # apenas a transição entre dois trechos; só confirmamos após várias.
            generating = self._js(JS_IS_GENERATING, default=None)
            if generating is False:
                idle_confirmations += 1
            elif generating is None:
                # Algumas versões do DOM não expõem o botão primário. Nesse
                # caso, a estabilidade continua válida, mas com uma margem
                # maior para não encerrar durante uma pausa do streaming.
                idle_confirmations += 1
            else:
                idle_confirmations = 0
            required_confirmations = (completion_needed if generating is False
                                      else unknown_completion_needed)
            if debug_stream:
                print(
                    f"[stream] len={len(current)} new={seen_new} stable={stable} "
                    f"idle={idle_confirmations}/{required_confirmations} "
                    f"generating={generating!r} continuar={self.tem_continuar()} "
                    f"aberta={resposta_tem_cerca_aberta(last_text)} api={usar_api}",
                    flush=True)
            dom_diz_pronta = (last_text and stable >= stable_needed
                              and idle_confirmations >= required_confirmations
                              and not resposta_tem_cerca_aberta(last_text))
            # Com a API funcionando o DOM nunca encerra sozinho: foi assim que
            # respostas voltaram cortadas. Exceção: o servidor nunca registrou a
            # rodada (API desatualizada) enquanto a tela já mostra tudo pronto.
            if (dom_diz_pronta and usar_api and api_aguardando_desde
                    and time.monotonic() - api_aguardando_desde > 20):
                usar_api = False
            if dom_diz_pronta and not usar_api:
                return self._juntar(pedacos, last_text)

    def _texto_final_api(self, id_antes, text) -> str:
        """Texto exato da resposta guardado pelo servidor; registra a captura."""
        estado = self._estado_api(incluir_texto=True)
        if estado is None:
            return ""
        fase, resposta = avaliar_estado_api(estado, id_antes, text)
        if not resposta:
            return ""
        usuario = estado.get("usuario") or {}
        self.ultima_captura = {
            "fonte": "api",
            "status": resposta.get("status"),
            "tokens": resposta.get("tokens"),
            "enviado": tamanho_js(text),
            "guardado": usuario.get("tamanho"),
            "tamanho": resposta.get("tamanho"),
            "fase": fase,
        }
        return resposta.get("texto") or ""

    @staticmethod
    def _juntar(pedacos: list[str], atual: str) -> str:
        """Remonta a resposta cortada por "Continuar".

        O DeepSeek tanto pode CONTINUAR a mesma bolha quanto abrir uma nova. Se
        continuou a mesma, `atual` já contém o pedaço anterior inteiro — colar de
        novo duplicaria tudo. Por isso cada pedaço só entra se ainda não estiver
        dentro do texto atual.
        """
        if not pedacos:
            return atual
        partes = [p for p in pedacos if p and p not in atual]
        partes.append(atual)
        return "\n".join(p for p in partes if p)
