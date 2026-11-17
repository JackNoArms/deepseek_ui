"""Prova empírica: dois Chrome em paralelo com Selenium.

Contexto (levantamento de 2026-10-16):

- `main.py` não tem lock de instância (`QSharedMemory`, `QLockFile`).
- `src/wrapper.py` monta `--user-data-dir={raiz do código}/chrome_profile` —
  derivado da pasta do próprio projeto, não global.
- `.deepseek_ui/session.json` (`src/session.py`) é por projeto.

Conclusão teórica: duas cópias do projeto em pastas diferentes devem rodar em
paralelo (cada uma com seu perfil de Chrome). Duas instâncias da MESMA pasta
brigam pelo mesmo `chrome_profile` e a segunda deve falhar.

Estes testes verificam o comportamento do Chrome/Selenium em si — o componente
com risco real. Não abrem chat.deepseek.com; só sobem o navegador.
"""

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def _opcoes(perfil):
    opcoes = Options()
    opcoes.add_argument("--headless=new")
    opcoes.add_argument(f"--user-data-dir={perfil}")
    opcoes.add_argument("--no-first-run")
    opcoes.add_argument("--no-default-browser-check")
    opcoes.add_argument("--disable-gpu")
    return opcoes


def test_dois_perfis_diferentes_rodam_em_paralelo(tmp_path):
    """Cenário 'duas cópias do projeto': cada raiz tem seu chrome_profile."""
    a = tmp_path / "copia_a" / "chrome_profile"
    b = tmp_path / "copia_b" / "chrome_profile"
    a.parent.mkdir()
    b.parent.mkdir()

    driver_a = webdriver.Chrome(options=_opcoes(a))
    driver_b = None
    try:
        driver_b = webdriver.Chrome(options=_opcoes(b))
        assert driver_a.session_id != driver_b.session_id
    finally:
        if driver_b is not None:
            driver_b.quit()
        driver_a.quit()


def test_mesmo_perfil_bloqueia_segundo(tmp_path):
    """Cenário 'duas instâncias da mesma pasta': o Chrome recusa o segundo."""
    perfil = tmp_path / "chrome_profile"
    driver_a = webdriver.Chrome(options=_opcoes(perfil))
    try:
        with pytest.raises(Exception) as info:
            webdriver.Chrome(options=_opcoes(perfil))
        mensagem = str(info.value).lower()
        assert (
            "session not created" in mensagem
            or "user data directory is already in use" in mensagem
        ), f"falhou por outro motivo: {info.value}"
        # Primeiro driver continua vivo — confirma que a falha foi do segundo.
        assert driver_a.session_id
    finally:
        driver_a.quit()
