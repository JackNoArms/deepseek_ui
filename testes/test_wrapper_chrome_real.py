"""Envio pelo `_submit_message` num Chrome de verdade (headless).

O fake de `test_wrapper_envio.py` só imita o `<textarea>`; aqui é o próprio
Chrome que normaliza as quebras de linha. Caso real de 2026-10-20: resultado
de comando com CRLF (~5.900 caracteres) recusado com "o campo não aceitou o
texto inteiro" — o texto estava inteiro, só com LF no lugar de CRLF.
"""

import tempfile
import threading
from urllib.parse import quote

import pytest
from selenium import webdriver

from src.wrapper import DeepSeekWrapper

PAGINA = """<!doctype html><meta charset="utf-8">
<textarea id="entrada"></textarea><button class="send">enviar</button>
<script>
window.enviadas = [];
const t = document.getElementById('entrada');
t.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    window.enviadas.push(t.value);
    t.value = '';
  }
});
</script>"""


@pytest.fixture(scope="module")
def chrome():
    opcoes = webdriver.ChromeOptions()
    opcoes.add_argument("--headless=new")
    opcoes.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='wrapper_real_')}")
    driver = webdriver.Chrome(options=opcoes)
    yield driver
    driver.quit()


def _wrapper(driver):
    w = DeepSeekWrapper.__new__(DeepSeekWrapper)
    w.driver = driver
    w._lock = threading.RLock()
    w.config = {"selectors": {"css": {"send_button": "button.send"}},
                "timeouts": {"element_wait": 2}}
    w._visible_user_messages = lambda: None
    return w


def _enviar(chrome, texto):
    chrome.get("data:text/html;charset=utf-8," + quote(PAGINA))
    campo = chrome.find_element("id", "entrada")
    _wrapper(chrome)._submit_message(campo, texto)
    return chrome.execute_script("return window.enviadas")


def test_saida_de_comando_com_crlf_e_enviada_inteira(chrome):
    texto = ("Resultado do que você pediu:\r\n\r\n```\r\n$ dir SentraLauncher-v2.1.apk\r\n"
             + "".join(f"classes{i}.dex            {i * 1000}\r\n" for i in range(150))
             + "INFORMAÇÕES: não foi possível localizar arquivos\r\n"
             + "java version \"21.0.10\" 2026-01-20 LTS\r\n```")
    assert len(texto) > 5000
    enviadas = _enviar(chrome, texto)
    assert enviadas == [texto.replace("\r\n", "\n")]


def test_cr_solto_de_barra_de_progresso(chrome):
    enviadas = _enviar(chrome, "baixando 10%\rbaixando 100%\r\nfeito")
    assert enviadas == ["baixando 10%\nbaixando 100%\nfeito"]


def test_texto_comum_continua_igual(chrome):
    texto = "pergunta normal\ncom acentuação, emoji 🚀 e tab\tok"
    assert _enviar(chrome, texto) == [texto]
