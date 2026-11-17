"""Confirma que o DeepSeek aceitou o envio antes de iniciar a espera da resposta."""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch

from selenium.webdriver.common.keys import Keys

import src.wrapper as wrapper_module
from src.wrapper import DeepSeekWrapper, JS_CAPTURE_VISIBLE, JS_IS_GENERATING, JS_SET_INPUT


ok = fail = 0


def checa(nome, condicao, detalhe: object = ""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


class FakeInput:
    def __init__(self, driver, aceita_enter=False):
        self.driver = driver
        self.value = ""
        self.aceita_enter = aceita_enter
        self.digitadas = []

    def clear(self):
        self.value = ""

    def get_property(self, nome):
        return self.value if nome == "value" else None

    def send_keys(self, tecla):
        self.digitadas.append(tecla)
        if tecla == Keys.RETURN and self.aceita_enter:
            self.driver.messages.append(self.value)
            self.value = ""


class FakeButton:
    def __init__(self, driver, submete=True):
        self.driver = driver
        self.submete = submete
        self.cliques = 0

    def click(self):
        self.cliques += 1
        if self.submete:
            self.driver.messages.append(self.driver.input.value)
            self.driver.input.value = ""


class FakeDriver:
    """Imita o <textarea> real: CRLF e CR viram LF; `limite` corta o texto.

    Antes o fake guardava o texto como veio, e por isso nenhum teste pegou o
    falso "não aceitou o texto inteiro" com quebras do Windows (o Chrome real
    normaliza — conferido em 2026-10-20).
    """

    def __init__(self, aceita_enter=False, submete_no_clique=True, limite=None):
        self.messages = []
        self.input = FakeInput(self, aceita_enter)
        self.button = FakeButton(self, submete_no_clique)
        self.limite = limite

    def execute_script(self, script, element, text):
        if script == JS_SET_INPUT:
            valor = text.replace("\r\n", "\n").replace("\r", "\n")
            element.value = valor[:self.limite] if self.limite else valor


class FakeWait:
    def __init__(self, driver, timeout):
        _ = timeout
        self.driver = driver

    def until(self, condition):
        _ = condition
        return self.driver.button


def prepara_wrapper(driver):
    wrapper = DeepSeekWrapper.__new__(DeepSeekWrapper)
    wrapper.driver = driver
    wrapper._lock = threading.RLock()
    wrapper.config = {
        "selectors": {"css": {"send_button": "button.send"}},
        "timeouts": {"element_wait": 1},
    }
    wrapper._get_selector = lambda key: (
        ("button.send", "css selector") if key == "send_button" else
        ("textarea.input", "css selector")
    )

    def js(script, *args, default=None):
        _ = args
        if script == JS_CAPTURE_VISIBLE:
            return [
                {"role": "user", "content": message}
                for message in driver.messages
            ]
        if script == JS_IS_GENERATING:
            return False
        return default

    wrapper._js = js
    wrapper._visible_user_messages = lambda: list(driver.messages)
    return wrapper


print("-- confirmação do envio ao DeepSeek --")
with patch.object(wrapper_module, "WebDriverWait", FakeWait):
    driver = FakeDriver(aceita_enter=False, submete_no_clique=True)
    wrapper = prepara_wrapper(driver)
    with patch.object(wrapper_module, "SEND_CONFIRM_TIMEOUT", 0), \
            patch.object(wrapper_module, "SEND_RETRY_TIMEOUT", 0):
        wrapper._submit_message(driver.input, "mensagem enviada")
    checa("fallback clica Enviar quando Enter é ignorado",
          driver.button.cliques == 1, driver.button.cliques)
    checa("conteúdo aparece como mensagem do usuário",
          driver.messages == ["mensagem enviada"], driver.messages)

    driver = FakeDriver(aceita_enter=True)
    wrapper = prepara_wrapper(driver)
    with patch.object(wrapper_module, "SEND_CONFIRM_TIMEOUT", 0):
        wrapper._submit_message(driver.input, "envio por Enter")
    checa("não duplica quando Enter já foi aceito",
          driver.button.cliques == 0 and driver.messages == ["envio por Enter"],
          (driver.button.cliques, driver.messages))

    driver = FakeDriver(aceita_enter=False, submete_no_clique=False)
    wrapper = prepara_wrapper(driver)
    with patch.object(wrapper_module, "SEND_CONFIRM_TIMEOUT", 0), \
            patch.object(wrapper_module, "SEND_RETRY_TIMEOUT", 0):
        try:
            wrapper._submit_message(driver.input, "não enviado")
            falhou_explicitamente = False
        except RuntimeError as error:
            falhou_explicitamente = "não confirmou o envio" in str(error)
    checa("falha explícita se nenhum método envia",
          falhou_explicitamente, driver.messages)

print("\n-- quebras de linha do Windows (saída de comando) --")
with patch.object(wrapper_module, "WebDriverWait", FakeWait):
    comando = ("Resultado do que você pediu:\r\n$ dir SentraLauncher-v2.1.apk\r\n"
               + "linha de saída\r\n" * 300 + "barra\rprogresso\r\nfim")
    driver = FakeDriver(aceita_enter=True)
    wrapper = prepara_wrapper(driver)
    try:
        with patch.object(wrapper_module, "SEND_CONFIRM_TIMEOUT", 0):
            wrapper._submit_message(driver.input, comando)
        erro = None
    except RuntimeError as e:
        erro = str(e)
    checa("texto com \\r\\n não acusa campo incompleto", erro is None, erro)
    checa("mensagem enviada inteira (com quebras normalizadas)",
          driver.messages == [comando.replace("\r\n", "\n").replace("\r", "\n")],
          len(driver.messages[0]) if driver.messages else driver.messages)

    driver = FakeDriver(aceita_enter=True, limite=100)
    wrapper = prepara_wrapper(driver)
    try:
        wrapper._submit_message(driver.input, "x" * 500)
        erro = ""
    except RuntimeError as e:
        erro = str(e)
    checa("campo cortado de verdade ainda acusa, com os números",
          "não aceitou o texto inteiro" in erro and "100 de 500" in erro, erro)

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
