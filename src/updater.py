"""Atualização do app: checar, baixar e aplicar o instalador novo.

Módulo puro Python — não importa Qt. Os três consumidores são:

1. `window.py` — agenda checagem (boot + 6 h), mostra banner, chama
   `aplicar()` quando ocioso.
2. `testes/test_updater.py` — mocka `urllib.request.urlopen` e
   `subprocess.Popen` para testar cada etapa.
3. `publicar_release.bat` — usa `sha256_arquivo()` para gerar o
   manifesto de um release.

O que o cliente **não** faz de propósito:

- Não confia no `.exe` sem `sha256` conferido. Se divergir, o arquivo é
  descartado e a atualização é abortada com erro visível.
- Não atualiza se a versão local é mais antiga que `min_versao_compat`
  do manifesto (o Inno pode não conseguir subir por cima).
- Não busca quando a URL é o placeholder `SEU_USUARIO/...` — evita 404
  de log a cada boot antes de você configurar o repositório.
- Não bloqueia a UI: quem chama faz as operações custosas em `QThread`
  e devolve progresso por sinal.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from src import caminhos
from src.__version__ import __version__ as APP_VERSION

URL_MANIFESTO_PADRAO = (
    "https://github.com/SEU_USUARIO/deepseek-ui/"
    "releases/latest/download/manifest.json"
)
PLACEHOLDER = "SEU_USUARIO"
TIMEOUT_BUSCA = 6.0
TIMEOUT_BAIXAR = 60.0
TAMANHO_MAX_MANIFESTO = 1024 * 1024  # 1 MB — manifesto honesto cabe em 10 KB
TAMANHO_BLOCO = 1024 * 1024


class ManifestoErro(Exception):
    """Qualquer falha do updater que mereça mensagem ao usuário.

    Rede, 404, JSON inválido, sha256 errado, URL placeholder: todos
    viram `ManifestoErro(motivo)` com `motivo` curto e legível. A UI
    decide se mostra ou só loga em DEBUG (ex.: 404 em checagem
    automática de fundo = silencioso).
    """

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class Manifesto:
    versao: str
    url: str
    sha256: str
    notas: str = ""
    min_versao_compat: str = ""


@dataclass(frozen=True)
class Config:
    ultima_checagem: str = ""
    versao_ignorada: str = ""
    ignorada_ate: str = ""
    url_manifesto: str = ""


# ----------------- versões -----------------

def eh_placeholder(url: str) -> bool:
    return PLACEHOLDER in (url or "")


def _parse_versao(v: str) -> tuple[tuple[int, int, int], tuple[int, str]]:
    """Devolve ((major, minor, patch), (é_release, pre_lexicográfico)).

    Pre-release (1.1.0-rc1) perde para a release (1.1.0) porque o
    segundo elemento do par é (1, "") na release e (0, "rc1") na
    pré-release. Build metadata (+build5) é ignorado, como em PEP 440.
    """
    v = (v or "").strip()
    v = v.split("+", 1)[0]
    pre = ""
    base = v
    if "-" in v:
        base, pre = v.split("-", 1)
    partes: list[int] = []
    for p in base.split("."):
        try:
            partes.append(int(p))
        except ValueError:
            partes.append(0)
    while len(partes) < 3:
        partes.append(0)
    tri = (partes[0], partes[1], partes[2])
    pref = (1, "") if not pre else (0, pre)
    return tri, pref


def comparar_versoes(a: str, b: str) -> int:
    """Semântica suficiente do PEP 440 para o updater:

        1.1.1 > 1.1.0 > 1.1.0-rc1 > 1.0.99; +build é ignorado.

    Devolve -1, 0 ou 1.
    """
    pa, pra = _parse_versao(a)
    pb, prb = _parse_versao(b)
    if pa != pb:
        return 1 if pa > pb else -1
    if pra != prb:
        return 1 if pra > prb else -1
    return 0


# ----------------- manifesto -----------------

def buscar_manifesto(url: str | None = None,
                     timeout: float = TIMEOUT_BUSCA) -> Manifesto:
    """`GET` no manifesto remoto. Levanta `ManifestoErro` em qualquer falha.

    O manifesto é um JSON pequeno:

        {
          "versao": "1.1.1",
          "url": "https://.../DeepSeekUI-Setup-1.1.1.exe",
          "sha256": "<64 hex>",
          "notas": "...",
          "min_versao_compat": "1.0.0"
        }
    """
    url = (url or URL_MANIFESTO_PADRAO).strip()
    if not url:
        raise ManifestoErro("URL de atualização vazia.")
    if eh_placeholder(url):
        raise ManifestoErro(
            "URL de atualização ainda é o placeholder; configure o repositório "
            "em Tema → Configurar URL de atualização.")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"DeepSeekUI/{APP_VERSION}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read(TAMANHO_MAX_MANIFESTO + 1)
    except urllib.error.HTTPError as e:
        raise ManifestoErro(f"HTTP {e.code} ao buscar manifesto.")
    except urllib.error.URLError as e:
        motivo = getattr(e, "reason", e)
        raise ManifestoErro(f"Rede indisponível: {motivo}.")
    except OSError as e:
        raise ManifestoErro(f"Falha de rede ao buscar manifesto: {e}")

    if len(bruto) > TAMANHO_MAX_MANIFESTO:
        raise ManifestoErro("Manifesto grande demais; recusado.")
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ManifestoErro(f"Manifesto inválido (JSON): {e}")
    if not isinstance(dados, dict):
        raise ManifestoErro("Manifesto inválido: raiz não é objeto.")
    faltando = [c for c in ("versao", "url", "sha256")
                if not str(dados.get(c) or "").strip()]
    if faltando:
        raise ManifestoErro(
            f"Manifesto inválido: faltam campos {', '.join(faltando)}.")
    sha = str(dados["sha256"]).strip().lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ManifestoErro("Manifesto inválido: sha256 malformado.")
    url_exe = str(dados["url"]).strip()
    if not (url_exe.startswith("https://") or url_exe.startswith("http://")):
        raise ManifestoErro(
            "Manifesto inválido: URL do instalador não é http(s).")
    return Manifesto(
        versao=str(dados["versao"]).strip(),
        url=url_exe,
        sha256=sha,
        notas=str(dados.get("notas") or "").strip(),
        min_versao_compat=str(dados.get("min_versao_compat") or "").strip(),
    )


def verificar(manifesto: Manifesto, minha_versao: str = APP_VERSION) -> str:
    """Devolve `'atualizar'` | `'ok'` | `'bloqueado_antigo'`.

    `'bloqueado_antigo'` significa: existe versão mais nova, mas a sua é
    antiga demais para o Inno subir por cima. O usuário precisa baixar
    manualmente.
    """
    if manifesto.min_versao_compat and comparar_versoes(
            minha_versao, manifesto.min_versao_compat) < 0:
        return "bloqueado_antigo"
    if comparar_versoes(manifesto.versao, minha_versao) <= 0:
        return "ok"
    return "atualizar"


# ----------------- download -----------------

def baixar(url: str, destino: Path,
           ao_progredir=None,
           timeout: float = TIMEOUT_BAIXAR) -> Path:
    """Baixa `url` para `destino` via `.part` + `os.replace` atômico.

    `ao_progredir(baixado, total)` é chamado a cada 1 MB com os bytes já
    baixados e o total informado por `Content-Length` (0 se ausente).
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"DeepSeekUI/{APP_VERSION}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            with parcial.open("wb") as f:
                baixado = 0
                while True:
                    bloco = resp.read(TAMANHO_BLOCO)
                    if not bloco:
                        break
                    f.write(bloco)
                    baixado += len(bloco)
                    if ao_progredir is not None:
                        try:
                            ao_progredir(baixado, total)
                        except Exception:
                            pass
    except urllib.error.HTTPError as e:
        parcial.unlink(missing_ok=True)
        raise ManifestoErro(f"HTTP {e.code} ao baixar instalador.")
    except (urllib.error.URLError, OSError) as e:
        parcial.unlink(missing_ok=True)
        raise ManifestoErro(f"Falha ao baixar instalador: {e}")

    os.replace(parcial, destino)
    return destino


def sha256_arquivo(arquivo: Path) -> str:
    h = hashlib.sha256()
    with Path(arquivo).open("rb") as f:
        for bloco in iter(lambda: f.read(TAMANHO_BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def verificar_hash(arquivo: Path, sha256_esperado: str) -> bool:
    esperado = (sha256_esperado or "").strip().lower()
    if len(esperado) != 64:
        return False
    try:
        return sha256_arquivo(arquivo) == esperado
    except OSError:
        return False


def baixar_e_verificar(manifesto: Manifesto, pasta_destino: Path,
                      ao_progredir=None) -> Path:
    """Baixa + confere hash. Falhou o hash, apaga e levanta.

    O nome do arquivo tem a versão, então duas tentativas seguidas não
    sobrescrevem uma à outra antes da verificação.
    """
    destino = Path(pasta_destino) / f"DeepSeekUI-Setup-{manifesto.versao}.exe"
    baixar(manifesto.url, destino, ao_progredir=ao_progredir)
    if not verificar_hash(destino, manifesto.sha256):
        try:
            destino.unlink()
        except OSError:
            pass
        raise ManifestoErro(
            "sha256 do instalador não confere; arquivo descartado.")
    return destino


# ----------------- aplicar -----------------

def aplicar(setup_path: Path, relaunch: bool = True) -> subprocess.Popen:
    """Spawna o instalador novo em modo silencioso e devolve o `Popen`.

    O chamador deve chamar `QApplication.quit()` logo em seguida — o Inno
    com `/CLOSEAPPLICATIONS` mata o processo antigo antes de sobrescrever.
    `relaunch=True` passa `/RELAUNCH` para o `.iss` reabrir o app novo
    (o `.iss` precisa aceitar essa flag; ver ADR-024).
    """
    setup = Path(setup_path)
    if not setup.is_file():
        raise ManifestoErro(f"Instalador não encontrado: {setup}")
    args = [str(setup), "/SILENT", "/CLOSEAPPLICATIONS",
            "/NORESTART", "/SUPPRESSMSGBOXES"]
    if relaunch:
        args.append("/RELAUNCH=1")
    flags = 0
    if sys.platform == "win32":
        flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.Popen(args, creationflags=flags)


# ----------------- config do usuário -----------------

def _arquivo_config() -> Path:
    return caminhos.pasta_dados() / "updater.json"


def carregar_config() -> Config:
    arquivo = _arquivo_config()
    if not arquivo.is_file():
        return Config()
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    if not isinstance(dados, dict):
        return Config()
    return Config(
        ultima_checagem=str(dados.get("ultima_checagem") or ""),
        versao_ignorada=str(dados.get("versao_ignorada") or ""),
        ignorada_ate=str(dados.get("ignorada_ate") or ""),
        url_manifesto=str(dados.get("url_manifesto") or ""),
    )


def salvar_config(cfg: Config) -> bool:
    arquivo = _arquivo_config()
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps({
            "ultima_checagem": cfg.ultima_checagem,
            "versao_ignorada": cfg.versao_ignorada,
            "ignorada_ate": cfg.ignorada_ate,
            "url_manifesto": cfg.url_manifesto,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return False
    return True


def url_efetiva(cfg: Config | None = None) -> str:
    """URL do manifesto: override do usuário se houver, senão o placeholder."""
    cfg = cfg or carregar_config()
    if cfg.url_manifesto:
        return cfg.url_manifesto
    return URL_MANIFESTO_PADRAO
