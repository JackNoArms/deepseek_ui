"""Teste MANUAL contra o chat.deepseek.com real: tamanho de envio e de resposta.

Não entra no `rodar_tudo.py` (não começa com `test_`): precisa do Chrome com
login salvo em `chrome_profile/` e cria conversas novas na conta.

    python testes/real_tamanhos_deepseek.py captura [minimizado|coberto|minimiza-no-meio|visivel] [N]
        Resposta longa com o Chrome escondido do jeito escolhido. Compara o que
        o app capturou com o texto que o próprio site guardou (API de histórico).
        N > 0 enche a conversa com N rodadas antes, para simular tarefa longa.

    python testes/real_tamanhos_deepseek.py envio 50000 200000
        Uma conversa nova por tamanho. Confere se o site guardou a mensagem
        inteira e se o modelo enxergou o marcador do fim do texto.

A conferência usa um JS próprio deste arquivo, independente do wrapper, para
não validar o app com o mesmo código que está sendo testado.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parser import parse
from src.wrapper import DeepSeekWrapper

JS_ULTIMAS = r"""
const done = arguments[arguments.length - 1];
(async () => {
    try {
        const id = (location.pathname.match(/\/s\/([^/?#]+)/) || [])[1];
        if (!id) return done({erro: 'sem conversa na URL'});
        let token = '';
        try { token = JSON.parse(localStorage.getItem('userToken')).value || ''; } catch (e) {}
        const resp = await fetch('/api/v0/chat/history_messages?chat_session_id=' + id,
            {headers: token ? {authorization: 'Bearer ' + token} : {}});
        const dados = (await resp.json()).data.biz_data;
        const msgs = dados.chat_messages || [];
        const usuario = msgs.filter(m => m.role === 'USER').pop();
        const modelo = msgs.filter(m => m.role === 'ASSISTANT').pop();
        const junta = (m, tipo) => (m ? m.fragments : [])
            .filter(f => f.type === tipo).map(f => f.content || '').join('');
        done({
            usuario: junta(usuario, 'REQUEST'),
            resposta: junta(modelo, 'RESPONSE'),
            status: modelo && modelo.status,
            tokens: modelo && modelo.accumulated_token_usage,
        });
    } catch (e) { done({erro: String(e)}); }
})();
"""


def site(w):
    w.driver.set_script_timeout(60)
    return w.driver.execute_async_script(JS_ULTIMAS)


def conversa_nova(w):
    w.driver.get("https://chat.deepseek.com/")
    time.sleep(4)
    w.new_chat()
    time.sleep(2)


def _cobrir_tela(segundos):
    """Janela sem borda, em tela cheia e sempre no topo, num processo à parte."""
    codigo = (
        "import sys\n"
        "from PyQt6.QtCore import Qt, QTimer\n"
        "from PyQt6.QtWidgets import QApplication, QLabel\n"
        "a = QApplication(sys.argv)\n"
        "w = QLabel('cobrindo o Chrome para o teste de captura')\n"
        "w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)\n"
        "w.showFullScreen()\n"
        f"QTimer.singleShot({int(segundos * 1000)}, a.quit)\n"
        "a.exec()\n")
    import subprocess
    return subprocess.Popen([sys.executable, "-c", codigo])


def encher_conversa(w, rodadas):
    """Conversa longa: lista virtual com muitas mensagens, como numa tarefa real."""
    linha = "contexto de teste 0123456789 abcdefghij ABCDEFGHIJ\n"
    for i in range(rodadas):
        texto = (f"Rodada de enchimento {i + 1}. Ignore o texto abaixo e responda "
                 f"apenas: OK {i + 1}\n\n" + linha * 400)
        inicio = time.time()
        resposta = w.send_message(texto)
        print(f"enchimento {i + 1}/{rodadas} em {time.time() - inicio:.1f}s: "
              f"{resposta[:40]!r} fonte={w.ultima_captura.get('fonte')} "
              f"tokens={w.ultima_captura.get('tokens')}", flush=True)


def captura(w, modo="minimizado", encher=0):
    conversa_nova(w)
    if encher:
        encher_conversa(w, encher)
    pedido = (
        "Teste de captura. Responda SOMENTE com um bloco de código rotulado json "
        "contendo o objeto {\"response\": TEXTO, \"actions\": []}, em que TEXTO "
        "são os números inteiros de 1 a 1500, em ordem, separados por vírgula e "
        "espaço. Não escreva nada fora do bloco.")
    capa = None
    if modo == "minimizado":
        w.driver.minimize_window()
    elif modo == "coberto":
        capa = _cobrir_tela(240)
        time.sleep(2)
    elif modo == "minimiza-no-meio":
        import threading

        def minimizar():
            time.sleep(6)
            with w._lock:
                w.driver.minimize_window()
            print("Chrome minimizado no meio da resposta")
        threading.Thread(target=minimizar, daemon=True).start()
    print(f"modo {modo}; enviando…")
    inicio = time.time()
    try:
        capturado = w.send_message(pedido)
    finally:
        if capa is not None:
            capa.kill()
        w.driver.maximize_window()
    print(f"send_message voltou em {time.time() - inicio:.1f}s; "
          f"captura={getattr(w, 'ultima_captura', None)}")
    time.sleep(3)
    s = site(w)
    if s.get("erro"):
        print("API do site falhou:", s["erro"])
        return False
    lido = parse(capturado, formato="json")
    print(f"capturado pelo app: {len(capturado)} chars, JSON válido={lido.valida} {lido.erro}")
    print(f"guardado pelo site: {len(s['resposta'])} chars, status={s['status']}, tokens={s['tokens']}")
    print("início capturado:", repr(capturado[:80]))
    print("fim capturado:   ", repr(capturado[-80:]))
    iguais = capturado.strip() == (s["resposta"] or "").strip()
    print("RESULTADO:", "OK, captura idêntica ao site" if iguais
          else "FALHA, captura diferente do texto do site")
    return iguais


def envio(w, tamanho):
    conversa_nova(w)
    marcador = f"FIM-{tamanho}-{int(time.time()) % 100000}"
    cabeca = (f"Teste de envio de {tamanho} caracteres. Ignore o enchimento. "
              "Responda apenas com o marcador que aparece na última linha.\n\n")
    linha = "enchimento 0123456789 abcdefghij ABCDEFGHIJ\n"
    corpo = (linha * (tamanho // len(linha) + 1))
    texto = cabeca + corpo[: max(0, tamanho - len(cabeca) - len(marcador) - 1)] + "\n" + marcador
    print(f"\n== envio de {len(texto)} caracteres")
    inicio = time.time()
    try:
        resposta = w.send_message(texto)
    except Exception as e:
        print(f"send_message levantou {type(e).__name__}: {e}")
        return False
    print(f"send_message voltou em {time.time() - inicio:.1f}s")
    time.sleep(3)
    s = site(w)
    if s.get("erro"):
        print("API do site falhou:", s["erro"])
        return False
    guardado = s["usuario"] or ""
    print(f"site guardou {len(guardado)} de {len(texto)} chars; "
          f"status={s['status']} tokens={s['tokens']}")
    print("resposta:", repr(resposta[:200]))
    ok = len(guardado.strip()) >= len(texto.strip()) and marcador in resposta
    print("RESULTADO:", "OK" if ok else "FALHA")
    return ok


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("captura", "envio"):
        print(__doc__)
        return 2
    w = DeepSeekWrapper()
    if not w.open():
        print("Não conectou (login pendente?)")
        return 1
    try:
        if sys.argv[1] == "captura":
            ok = captura(w, sys.argv[2] if len(sys.argv) > 2 else "minimizado",
                         int(sys.argv[3]) if len(sys.argv) > 3 else 0)
        else:
            ok = all([envio(w, int(n)) for n in sys.argv[2:] or ["50000"]])
    finally:
        w.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
