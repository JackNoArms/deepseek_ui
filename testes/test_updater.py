"""Testes do updater — pytest. Mocka rede e subprocesso, isola dados."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.updater import (
    Config,
    Manifesto,
    ManifestoErro,
    URL_MANIFESTO_PADRAO,
    aplicar,
    baixar,
    baixar_e_verificar,
    buscar_manifesto,
    carregar_config,
    comparar_versoes,
    eh_placeholder,
    salvar_config,
    sha256_arquivo,
    url_efetiva,
    verificar,
    verificar_hash,
)


# ----------------- fixtures -----------------

@pytest.fixture
def dados_isolados(tmp_path, monkeypatch):
    destino = tmp_path / "dados"
    monkeypatch.setenv("DEEPSEEK_UI_DADOS", str(destino))
    return destino


class FakeHTTPResp(io.BytesIO):
    """`urlopen` devolve um objeto que precisa ser context manager."""

    def __init__(self, dados: bytes, content_length=None):
        super().__init__(dados)
        self.headers = {
            "Content-Length": str(
                content_length if content_length is not None else len(dados)),
        }

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _resp(dados, *, content_length=None):
    if isinstance(dados, dict):
        bruto = json.dumps(dados).encode("utf-8")
    elif isinstance(dados, str):
        bruto = dados.encode("utf-8")
    else:
        bruto = dados
    return FakeHTTPResp(bruto, content_length=content_length)


MANIFESTO_OK = {
    "versao": "1.1.1",
    "url": "https://github.com/u/r/releases/download/v1.1.1/DeepSeekUI-Setup-1.1.1.exe",
    "sha256": "a" * 64,
    "notas": "corrige x",
    "min_versao_compat": "1.0.0",
}


# ----------------- versões -----------------

class TestCompararVersoes:
    def test_iguais(self):
        assert comparar_versoes("1.1.0", "1.1.0") == 0

    def test_patch_maior(self):
        assert comparar_versoes("1.1.1", "1.1.0") == 1

    def test_patch_menor(self):
        assert comparar_versoes("1.0.99", "1.1.0") == -1

    def test_patch_ausente_vale_zero(self):
        assert comparar_versoes("1.1", "1.1.0") == 0

    def test_prerelease_antes_da_release(self):
        assert comparar_versoes("1.1.0-rc1", "1.1.0") == -1
        assert comparar_versoes("1.1.0", "1.1.0-rc1") == 1

    def test_prereleases_entre_si(self):
        assert comparar_versoes("1.1.0-rc1", "1.1.0-rc2") == -1

    def test_build_metadata_ignorado(self):
        assert comparar_versoes("1.1.0+build5", "1.1.0") == 0

    def test_malformada_nao_estoura(self):
        # 'abc' vira 0.0.0, então é menor que 1.0.0
        assert comparar_versoes("abc", "1.0.0") == -1


# ----------------- buscar manifesto -----------------

class TestBuscarManifesto:
    def test_ok(self):
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(MANIFESTO_OK)):
            m = buscar_manifesto("https://exemplo.test/manifest.json")
        assert m.versao == "1.1.1"
        assert m.sha256 == "a" * 64
        assert m.min_versao_compat == "1.0.0"
        assert m.notas == "corrige x"
        assert m.url.endswith("DeepSeekUI-Setup-1.1.1.exe")

    def test_url_placeholder_levanta(self):
        with pytest.raises(ManifestoErro) as exc:
            buscar_manifesto(URL_MANIFESTO_PADRAO)
        motivo = exc.value.motivo.lower()
        assert "placeholder" in motivo or "configur" in motivo

    def test_url_vazia_levanta(self):
        with pytest.raises(ManifestoErro):
            buscar_manifesto("")

    def test_404_levanta(self):
        err = urllib.error.HTTPError(
            "https://exemplo.test/m.json", 404, "Not Found", {}, None)
        with patch("src.updater.urllib.request.urlopen", side_effect=err):
            with pytest.raises(ManifestoErro) as exc:
                buscar_manifesto("https://exemplo.test/manifest.json")
        assert "404" in exc.value.motivo

    def test_rede_indisponivel_levanta(self):
        with patch("src.updater.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("timed out")):
            with pytest.raises(ManifestoErro):
                buscar_manifesto("https://exemplo.test/manifest.json")

    def test_json_invalido_levanta(self):
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(b"not json")):
            with pytest.raises(ManifestoErro) as exc:
                buscar_manifesto("https://exemplo.test/manifest.json")
        assert "json" in exc.value.motivo.lower()

    def test_raiz_nao_objeto_levanta(self):
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(b"[]")):
            with pytest.raises(ManifestoErro):
                buscar_manifesto("https://exemplo.test/manifest.json")

    def test_falta_campo_levanta(self):
        payload = dict(MANIFESTO_OK)
        del payload["sha256"]
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(payload)):
            with pytest.raises(ManifestoErro) as exc:
                buscar_manifesto("https://exemplo.test/manifest.json")
        assert "sha256" in exc.value.motivo

    def test_sha256_malformado_levanta(self):
        payload = dict(MANIFESTO_OK, sha256="xyz")
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(payload)):
            with pytest.raises(ManifestoErro):
                buscar_manifesto("https://exemplo.test/manifest.json")

    def test_url_nao_http_levanta(self):
        payload = dict(MANIFESTO_OK, url="file:///etc/passwd")
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(payload)):
            with pytest.raises(ManifestoErro):
                buscar_manifesto("https://exemplo.test/manifest.json")

    def test_manifesto_grande_levanta(self):
        grande = b"x" * (1024 * 1024 + 5)
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(grande)):
            with pytest.raises(ManifestoErro) as exc:
                buscar_manifesto("https://exemplo.test/manifest.json")
        assert "grande" in exc.value.motivo.lower()


# ----------------- verificar -----------------

class TestVerificar:
    def test_atualizar_quando_maior(self):
        m = Manifesto(versao="1.1.1", url="https://x", sha256="a" * 64)
        assert verificar(m, "1.1.0") == "atualizar"

    def test_ok_quando_igual(self):
        m = Manifesto(versao="1.1.0", url="https://x", sha256="a" * 64)
        assert verificar(m, "1.1.0") == "ok"

    def test_ok_quando_menor(self):
        m = Manifesto(versao="1.0.0", url="https://x", sha256="a" * 64)
        assert verificar(m, "1.1.0") == "ok"

    def test_bloqueia_quando_min_compat(self):
        m = Manifesto(versao="2.0.0", url="https://x", sha256="a" * 64,
                      min_versao_compat="1.5.0")
        assert verificar(m, "1.1.0") == "bloqueado_antigo"

    def test_nao_bloqueia_quando_min_compat_atingido(self):
        m = Manifesto(versao="2.0.0", url="https://x", sha256="a" * 64,
                      min_versao_compat="1.0.0")
        assert verificar(m, "1.1.0") == "atualizar"


# ----------------- baixar / hash -----------------

class TestBaixar:
    def test_baixa_com_progresso(self, tmp_path):
        dados = b"conteudo-instalador" * 100_000  # ~1.8 MB, 2 blocos de 1 MB
        progressos = []

        def prog(baixado, total):
            progressos.append((baixado, total))

        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(dados)):
            destino = tmp_path / "setup.exe"
            resultado = baixar(
                "https://exemplo.test/x.exe", destino, ao_progredir=prog)

        assert resultado == destino
        assert destino.read_bytes() == dados
        assert len(progressos) >= 2
        assert progressos[-1][0] == len(dados)
        assert progressos[-1][1] == len(dados)

    def test_sem_callback_funciona(self, tmp_path):
        dados = b"abc"
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(dados)):
            destino = tmp_path / "setup.exe"
            baixar("https://exemplo.test/x.exe", destino)
        assert destino.read_bytes() == dados

    def test_falha_de_rede_limpa_parcial(self, tmp_path):
        with patch("src.updater.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("boom")):
            destino = tmp_path / "setup.exe"
            with pytest.raises(ManifestoErro):
                baixar("https://exemplo.test/x.exe", destino)
        assert not destino.exists()
        assert not (tmp_path / "setup.exe.part").exists()

    def test_callback_que_explode_nao_derruba_download(self, tmp_path):
        dados = b"abcdef"
        def prog(_b, _t):
            raise RuntimeError("boom do chamador")
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(dados)):
            destino = tmp_path / "setup.exe"
            baixar("https://exemplo.test/x.exe", destino, ao_progredir=prog)
        assert destino.read_bytes() == dados


class TestHash:
    def test_sha256_bate(self, tmp_path):
        arquivo = tmp_path / "a.bin"
        arquivo.write_bytes(b"hello")
        assert sha256_arquivo(arquivo) == (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")

    def test_verificar_hash_ok(self, tmp_path):
        arquivo = tmp_path / "a.bin"
        arquivo.write_bytes(b"hello")
        assert verificar_hash(arquivo, sha256_arquivo(arquivo)) is True

    def test_verificar_hash_falha(self, tmp_path):
        arquivo = tmp_path / "a.bin"
        arquivo.write_bytes(b"hello")
        assert verificar_hash(arquivo, "0" * 64) is False

    def test_verificar_hash_esperado_malformado(self, tmp_path):
        arquivo = tmp_path / "a.bin"
        arquivo.write_bytes(b"hello")
        assert verificar_hash(arquivo, "abc") is False

    def test_verificar_hash_arquivo_inexistente(self, tmp_path):
        assert verificar_hash(tmp_path / "nada", "a" * 64) is False


class TestBaixarEVerificar:
    def test_baixa_e_verifica_ok(self, tmp_path):
        conteudo = b"instalador-fake" * 1000
        sha = hashlib.sha256(conteudo).hexdigest()
        m = Manifesto(
            versao="1.1.1",
            url="https://exemplo.test/x.exe",
            sha256=sha,
        )
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(conteudo)):
            destino = baixar_e_verificar(m, tmp_path)
        assert destino.name == "DeepSeekUI-Setup-1.1.1.exe"
        assert destino.read_bytes() == conteudo

    def test_hash_errado_apaga_e_levanta(self, tmp_path):
        conteudo = b"instalador-fake"
        m = Manifesto(
            versao="1.1.1",
            url="https://exemplo.test/x.exe",
            sha256="0" * 64,
        )
        with patch("src.updater.urllib.request.urlopen",
                   return_value=_resp(conteudo)):
            with pytest.raises(ManifestoErro) as exc:
                baixar_e_verificar(m, tmp_path)
        assert "sha256" in exc.value.motivo.lower()
        assert not (tmp_path / "DeepSeekUI-Setup-1.1.1.exe").exists()


# ----------------- aplicar -----------------

class TestAplicar:
    def test_levanta_se_setup_nao_existe(self, tmp_path):
        with pytest.raises(ManifestoErro):
            aplicar(tmp_path / "nao-existe.exe")

    def test_argumentos_esperados(self, tmp_path):
        setup = tmp_path / "setup.exe"
        setup.write_bytes(b"MZ")
        with patch("src.updater.subprocess.Popen") as mock_popen:
            aplicar(setup, relaunch=True)
        args, kwargs = mock_popen.call_args
        argv = args[0]
        assert argv[0].endswith("setup.exe")
        for flag in ("/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART",
                     "/SUPPRESSMSGBOXES", "/RELAUNCH=1"):
            assert flag in argv
        # Em Windows, Popen recebe as flags de detach
        if sys.platform == "win32":
            assert kwargs["creationflags"] != 0

    def test_sem_relaunch(self, tmp_path):
        setup = tmp_path / "setup.exe"
        setup.write_bytes(b"MZ")
        with patch("src.updater.subprocess.Popen") as mock_popen:
            aplicar(setup, relaunch=False)
        argv = mock_popen.call_args[0][0]
        assert "/RELAUNCH=1" not in argv


# ----------------- config -----------------

class TestConfig:
    def test_sem_arquivo_devolve_padrao(self, dados_isolados):
        assert carregar_config() == Config()

    def test_round_trip(self, dados_isolados):
        cfg = Config(
            ultima_checagem="2026-10-26T12:00:00",
            versao_ignorada="1.1.1",
            ignorada_ate="2026-10-27T12:00:00",
            url_manifesto="https://exemplo.test/manifest.json",
        )
        assert salvar_config(cfg) is True
        assert carregar_config() == cfg

    def test_arquivo_corrompido_devolve_padrao(self, dados_isolados):
        dados_isolados.mkdir(parents=True, exist_ok=True)
        (dados_isolados / "updater.json").write_text(
            "{ not json", encoding="utf-8")
        assert carregar_config() == Config()

    def test_cria_pasta_pai_ao_salvar(self, dados_isolados):
        # dados_isolados ainda não existe
        assert not dados_isolados.exists()
        assert salvar_config(Config(ultima_checagem="x")) is True
        assert dados_isolados.exists()


class TestUrlEfetiva:
    def test_sem_override_usa_placeholder(self, dados_isolados):
        assert url_efetiva() == URL_MANIFESTO_PADRAO

    def test_override(self, dados_isolados):
        salvar_config(Config(url_manifesto="https://exemplo.test/m.json"))
        assert url_efetiva() == "https://exemplo.test/m.json"


# ----------------- placeholder -----------------

def test_placeholder_detectado():
    assert eh_placeholder(URL_MANIFESTO_PADRAO) is True


def test_url_real_nao_e_placeholder():
    real = "https://github.com/fulano/deepseek-ui/releases/latest/download/manifest.json"
    assert eh_placeholder(real) is False
