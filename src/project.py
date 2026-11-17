"""Projeto aberto: a raiz autorizada e o mapa que o modelo recebe.

O mapa existe para economizar round trip. Cada pergunta ao DeepSeek custa
dezenas de segundos, então é mais barato mandar a árvore de uma vez do que
deixar o modelo descobrir a estrutura perguntando arquivo por arquivo.
"""

import fnmatch
import hashlib
import json
import os
from pathlib import Path

from src.backup import PASTA as PASTA_INTERNA
from src import caminhos
from src.permissions import PermissionPolicy
from src.sandbox import Sandbox, SandboxError

# Pastas que nunca interessam ao modelo e só gastariam o mapa.
IGNORAR = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".idea", ".vscode", "dist", "build", ".next", ".nuxt", "target",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "coverage",
    "chrome_profile", PASTA_INTERNA,
}

# Binário não vai para o mapa: o modelo não faz nada com ele e polui a lista.
EXT_BINARIA = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svgz",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".rar", ".exe", ".dll", ".so",
    ".dylib", ".pyc", ".pyo", ".class", ".jar", ".mp3", ".mp4", ".avi",
    ".mov", ".wav", ".ttf", ".otf", ".woff", ".woff2", ".db", ".sqlite",
}

ARQUIVO_CONFIG = ".workspace.json"


def _dentro(caminho: Path, raiz: Path) -> bool:
    try:
        Path(os.path.normcase(str(caminho))).relative_to(
            Path(os.path.normcase(str(raiz))))
        return True
    except ValueError:
        return False


def _link(caminho: Path) -> bool:
    return caminho.is_symlink() or (
        hasattr(caminho, "is_junction") and caminho.is_junction())


def _config_path() -> Path:
    """Onde fica o config do app.

    `DEEPSEEK_UI_CONFIG` existe para os testes apontarem para um arquivo
    descartável: sem isso, cada teste que abre uma pasta temporária sobrescrevia
    a última pasta de verdade do usuário — e no dia seguinte o app abria vazio.
    """
    override = os.environ.get("DEEPSEEK_UI_CONFIG")
    if override:
        return Path(override)
    return caminhos.arquivo_config()


def _ler_config() -> dict:
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _gravar_config(mudancas: dict):
    """Mescla, não substitui: gravar a raiz não pode apagar as outras chaves."""
    dados = _ler_config()
    dados.update(mudancas)
    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def carregar_tema() -> str | None:
    """Tema escolhido no app (nome de `theme.TEMAS`), se houver."""
    tema = _ler_config().get("tema")
    return tema if isinstance(tema, str) else None


def salvar_tema(nome: str):
    _gravar_config({"tema": nome})


def carregar_raiz() -> str | None:
    """Última pasta aberta, para reabrir sozinho na próxima execução."""
    return _ler_config().get("root")


def salvar_raiz(root: str):
    _gravar_config({"root": str(root)})
    adicionar_projeto_historico(str(root))


def historico_projetos() -> list[str]:
    """Pastas abertas recentemente, mais nova primeiro.

    Usado pelo painel remoto para listar projetos no celular — ele não tem
    como abrir um QFileDialog. Só diretórios que ainda existem são devolvidos.
    """
    bruto = _ler_config().get("historico_projetos", [])
    if not isinstance(bruto, list):
        return []
    validos = []
    for caminho in bruto:
        if not isinstance(caminho, str) or not caminho:
            continue
        p = Path(caminho)
        if p.is_dir():
            validos.append(str(p))
    return validos


def adicionar_projeto_historico(root: str, maximo: int = 12):
    """Coloca `root` no topo da lista de recentes, sem duplicar."""
    try:
        caminho = str(Path(root).resolve())
    except OSError:
        return
    atual = [c for c in historico_projetos() if c != caminho]
    atual.insert(0, caminho)
    _gravar_config({"historico_projetos": atual[:maximo]})


def auto_conectar() -> bool:
    """Abrir o Chrome sozinho ao iniciar, quando há conversa para retomar.

    Ligado por padrão. Para desligar, ponha `"auto_conectar": false` no
    `.workspace.json` na raiz do app.
    """
    return bool(_ler_config().get("auto_conectar", True))


class Project:
    """Raiz do projeto, contexto de arquivos e política de acesso associada."""

    def __init__(self, root, permissions: PermissionPolicy | None = None):
        self.permissions = permissions or PermissionPolicy(root)
        self.sandbox = self.permissions.project
        self.root = self.sandbox.root
        if Path(root).resolve(strict=True) != self.root:
            raise ValueError("A política de permissões pertence a outro projeto.")
        vault_local = self.root / "vault"
        self.vault_root = vault_local.resolve() if vault_local.is_dir() else None
        self._gitignore = self._ler_gitignore()

    @property
    def nome(self) -> str:
        return self.root.name

    def resolver(self, caminho: str, operacao: str) -> Path:
        virtual = (caminho.replace("\\", "/").strip("/")
                   if isinstance(caminho, str) else "")
        if self.vault_root is not None and (
                virtual == "vault" or virtual.startswith("vault/")):
            relativo = virtual[len("vault"):].lstrip("/")
            if not relativo and operacao in {"criar", "modificar", "apagar"}:
                raise SandboxError("A raiz do vault não pode ser alterada como arquivo.")
            destino = (self.vault_root if not relativo else
                       Sandbox(self.vault_root).resolve(relativo))
            self.permissions.check_not_blocked(destino)
            if self.permissions.mode == "folders":
                destino = self.permissions.resolve(str(destino), operacao)
            return destino
        return self.permissions.resolve(caminho, operacao)

    def relativo(self, caminho: Path) -> str:
        destino = Path(caminho).resolve(strict=False)
        if _dentro(destino, self.root):
            return self.sandbox.relative(destino)
        if self.vault_root and _dentro(destino, self.vault_root):
            return f"vault/{destino.relative_to(self.vault_root).as_posix()}".rstrip("/")
        return str(destino)

    def caminho_backup(self, caminho: Path) -> str:
        destino = Path(caminho).resolve(strict=False)
        if _dentro(destino, self.root):
            return self.sandbox.relative(destino)
        if self.vault_root and _dentro(destino, self.vault_root):
            return f"_vault/{destino.relative_to(self.vault_root).as_posix()}"

        raiz_autorizada = next(
            (Path(g["path"]) for g in self.permissions.grants
             if _dentro(destino, Path(g["path"]))),
            Path(destino.anchor))
        chave = hashlib.sha256(
            os.path.normcase(str(raiz_autorizada)).encode("utf-8")).hexdigest()[:12]
        relativo = destino.relative_to(raiz_autorizada).as_posix()
        return f"_externos/{chave}/{relativo}"

    def contexto_permissoes(self) -> str:
        policy = self.permissions
        if policy.mode == "folders":
            linhas = ["Pastas e operações autorizadas:"]
            for regra in policy.grants:
                operacoes = [nome for nome, chave in (
                    ("ler", "read"), ("criar", "create"), ("modificar", "edit"),
                    ("apagar", "delete")) if regra[chave]]
                if operacoes:
                    linhas.append(f"- {regra['path']}: {', '.join(operacoes)}")
            linhas.append(
                "Para esses diretórios, use o caminho absoluto exibido acima. "
                "O app recusará operações não concedidas.")
            linhas.append(
                "Comandos rodam sem confirmação num shell completo a partir da "
                "raiz do projeto; os grants não confinam os efeitos de processos.")
            return "\n".join(linhas)
        if policy.mode.startswith("computer_"):
            return (
                "Acesso amplo ativo. Use caminhos absolutos fora da raiz do "
                "projeto quando precisar; diretórios críticos do Windows seguem "
                "bloqueados pelo app.")
        return "Acesso restrito à raiz do projeto; use caminhos relativos."

    def _pode_ler(self, caminho: Path) -> bool:
        if self.permissions.mode != "folders":
            return True
        alvo = self.relativo(caminho)
        try:
            self.resolver(alvo, "ler")
        except SandboxError:
            return False
        return True

    # ---------------- ignore ----------------

    def _ler_gitignore(self) -> list[str]:
        """Padrões do .gitignore, de forma APROXIMADA.

        Suporta glob simples e pasta/. Não implementa negação (!), nem a
        semântica completa de '**' do git. É um filtro de ruído para o mapa,
        não uma reimplementação do git.
        """
        caminho = self.root / ".gitignore"
        if not caminho.is_file():
            return []
        padroes = []
        try:
            for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#") or linha.startswith("!"):
                    continue
                padroes.append(linha.rstrip("/").lstrip("/"))
        except OSError:
            return []
        return padroes

    def _ignorado(self, nome: str, rel: str, is_dir: bool) -> bool:
        if nome in IGNORAR:
            return True
        if not is_dir and Path(nome).suffix.lower() in EXT_BINARIA:
            return True
        for p in self._gitignore:
            if fnmatch.fnmatch(nome, p) or fnmatch.fnmatch(rel, p):
                return True
        return False

    # ---------------- leitura ----------------

    def arquivos(self, limite: int | None = None) -> list[str]:
        """Todo arquivo de texto do projeto, em caminho relativo com '/'.

        `limite` só existe para quem quer parar cedo; o padrão é varrer tudo.
        """
        achados = []
        virtual_vault = bool(
            self.vault_root
            and self.vault_root != (self.root / "vault").resolve(strict=False))
        for pasta, subpastas, nomes in os.walk(self.root):
            base = Path(pasta)
            rel_base = base.relative_to(self.root).as_posix()
            rel_base = "" if rel_base == "." else rel_base
            # poda in-place: os.walk não desce no que foi tirado daqui
            subpastas[:] = sorted(
                d for d in subpastas
                if not self._ignorado(d, f"{rel_base}/{d}".lstrip("/"), True)
                and not _link(base / d)
                and not (virtual_vault and self.vault_root
                         and (base / d).resolve(strict=False) == self.vault_root)
            )
            for nome in sorted(nomes):
                rel = f"{rel_base}/{nome}".lstrip("/")
                if self._ignorado(nome, rel, False):
                    continue
                achados.append(rel)
                if limite is not None and len(achados) >= limite:
                    return achados
        if virtual_vault and self.vault_root:
            for pasta, subpastas, nomes in os.walk(self.vault_root):
                base = Path(pasta)
                rel_base = base.relative_to(self.vault_root).as_posix()
                rel_base = "" if rel_base == "." else rel_base
                subpastas[:] = sorted(
                    d for d in subpastas
                    if not self._ignorado(
                        d, f"vault/{rel_base}/{d}".strip("/"), True)
                    and not _link(base / d)
                )
                for nome in sorted(nomes):
                    rel_local = f"{rel_base}/{nome}".strip("/")
                    if self._ignorado(nome, f"vault/{rel_local}", False):
                        continue
                    achados.append(f"vault/{rel_local}")
                    if limite is not None and len(achados) >= limite:
                        return achados
        return achados

    def mapa(self, limite: int | None = None) -> str:
        """Árvore do projeto em texto, pronta para colar no prompt.

        Inteira por padrão. Com `limite`, corta e avisa no fim.
        """
        limite_busca = (None if limite is None or self.permissions.mode == "folders"
                        else limite + 1)
        arquivos = self.arquivos(limite=limite_busca)
        if self.permissions.mode == "folders":
            autorizados = []
            for rel in arquivos:
                try:
                    self.resolver(rel, "ler")
                except SandboxError:
                    continue
                autorizados.append(rel)
            arquivos = autorizados
        cortou = limite is not None and len(arquivos) > limite
        if cortou:
            arquivos = arquivos[:limite]

        linhas = [f"{self.nome}/"]
        vistos = set()
        for rel in arquivos:
            partes = rel.split("/")
            for i in range(len(partes) - 1):
                pasta = "/".join(partes[: i + 1])
                if pasta not in vistos:
                    vistos.add(pasta)
                    linhas.append("  " * (i + 1) + partes[i] + "/")
            # +1 porque o nível 0 é a linha da própria raiz
            linhas.append("  " * (len(partes[:-1]) + 1) + partes[-1])
        if cortou:
            linhas.append(f"... (cortado em {limite} arquivos)")
        return "\n".join(linhas)

    def listar(self, rel: str | None = None, limite: int | None = None) -> str:
        """Árvore de uma subpasta. Sem `rel`, o projeto inteiro.

        Num projeto grande, devolver tudo a cada pedido gasta contexto à toa —
        o modelo normalmente quer olhar um canto só.
        """
        if not rel or rel in (".", "/", self.nome):
            return self.mapa(limite=limite)

        pasta = self.resolver(rel, "ler")
        if not pasta.is_dir():
            raise SandboxError(f"Não é uma pasta: {rel}")

        if self.vault_root and _dentro(pasta, self.vault_root):
            return self._listar_externo(pasta, limite)
        if not _dentro(pasta, self.root):
            return self._listar_externo(pasta, limite)

        base = self.sandbox.relative(pasta)
        linhas = [f"{base}/"]
        for atual, subpastas, nomes in os.walk(pasta):
            aqui = Path(atual)
            rel_aqui = self.sandbox.relative(aqui)
            subpastas[:] = sorted(
                d for d in subpastas
                if not self._ignorado(d, f"{rel_aqui}/{d}", True)
                and not _link(aqui / d)
                and self._pode_ler(aqui / d))
            nivel = 0 if aqui == pasta else len(
                Path(rel_aqui).relative_to(base).parts)
            if aqui != pasta:
                linhas.append("  " * nivel + aqui.name + "/")
            for nome in sorted(nomes):
                if self._ignorado(nome, f"{rel_aqui}/{nome}", False):
                    continue
                if not self._pode_ler(aqui / nome):
                    continue
                linhas.append("  " * (nivel + 1) + nome)
                if limite is not None and len(linhas) > limite:
                    linhas.append(f"... (cortado em {limite} linhas)")
                    return "\n".join(linhas)
        return "\n".join(linhas)

    def _listar_externo(self, pasta: Path, limite: int | None) -> str:
        linhas = [f"{self.relativo(pasta)}/"]
        for atual, subpastas, nomes in os.walk(pasta):
            base = Path(atual)
            subpastas[:] = sorted(
                d for d in subpastas
                if not self._ignorado(d, str(base / d), True)
                and not _link(base / d)
                and self._pode_ler(base / d))
            nivel = len(base.relative_to(pasta).parts)
            if base != pasta:
                linhas.append("  " * nivel + base.name + "/")
            for nome in sorted(nomes):
                if self._ignorado(nome, str(base / nome), False):
                    continue
                if not self._pode_ler(base / nome):
                    continue
                linhas.append("  " * (nivel + 1) + nome)
                if limite is not None and len(linhas) > limite:
                    linhas.append(f"... (cortado em {limite} linhas)")
                    return "\n".join(linhas)
        return "\n".join(linhas)

    def buscar(self, termo: str, em: str | None = None, ext: str | None = None,
               max_achados: int | None = None,
               max_bytes: int | None = None) -> str:
        """Procura `termo` no conteúdo dos arquivos. É o `grep` do agente.

        Nativo, sem shell: funciona em qualquer máquina e não depende de
        comando nenhum estar instalado.
        Busca literal e sem diferenciar maiúscula — é o que serve para caçar o
        nome de uma classe ou de uma função.
        """
        alvo = (termo or "").strip()
        if not alvo:
            raise SandboxError("Busca sem termo.")

        raiz = self.resolver(em, "ler") if em else self.root
        if not raiz.exists():
            raise SandboxError(f"Não existe: {em}")
        sufixo = ("." + ext.lstrip(".").lower()) if ext else None

        alvo_min = alvo.lower()
        achados, lidos, arquivos_com_achado = [], 0, 0
        if raiz.is_file():
            candidatos = [raiz]
        elif _dentro(raiz, self.root):
            candidatos = []
            for rel in self.arquivos():
                try:
                    caminho = self.resolver(rel, "ler")
                except SandboxError:
                    continue
                if (raiz == self.root or raiz == caminho
                        or raiz in caminho.parents):
                    candidatos.append(caminho)
        else:
            candidatos = [Path(p) for p in self._arquivos_externos(raiz)]

        for caminho in candidatos:
            if not caminho.is_file():
                continue
            try:
                permissao_caminho = self.relativo(caminho)
                self.resolver(permissao_caminho, "ler")
            except SandboxError:
                continue
            if sufixo and caminho.suffix.lower() != sufixo:
                continue
            try:
                tamanho = caminho.stat().st_size
                texto = caminho.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "\x00" in texto[:8192]:
                continue
            lidos += tamanho
            rel = self.relativo(caminho)
            achou_aqui = False
            for n, linha in enumerate(texto.splitlines(), 1):
                if alvo_min in linha.lower():
                    achou_aqui = True
                    achados.append(f"{rel}:{n}: {linha.strip()}")
                    if max_achados is not None and len(achados) >= max_achados:
                        achados.append(f"… (parei em {max_achados} achados)")
                        return self._fim_busca(alvo, achados, arquivos_com_achado + 1)
            if achou_aqui:
                arquivos_com_achado += 1
            if max_bytes is not None and lidos > max_bytes:
                achados.append("… (parei: muito conteúdo varrido)")
                break
        return self._fim_busca(alvo, achados, arquivos_com_achado)

    @staticmethod
    def _fim_busca(termo, achados, n_arquivos):
        if not achados:
            return f"Nenhum resultado para '{termo}'."
        return (f"{len(achados)} linha(s) em {n_arquivos} arquivo(s) para '{termo}':\n\n"
                + "\n".join(achados))

    def ler(self, rel: str, max_bytes: int | None = None) -> str:
        """Conteúdo de um arquivo do projeto, já validado pelo sandbox.

        Inteiro por padrão: o que não couber no envio aparece como erro de
        tamanho com os números, em vez de um corte silencioso. Com `max_bytes`
        o corte vem marcado no texto. Binário é recusado — virar texto só
        produziria lixo.
        """
        caminho = self.resolver(rel, "ler")
        if not caminho.is_file():
            raise SandboxError(f"Arquivo não existe: {rel}")

        texto = caminho.read_text(encoding="utf-8", errors="replace")
        if "\x00" in texto[:8192]:
            raise SandboxError(f"Arquivo binário, não dá para enviar como texto: {rel}")
        if max_bytes is not None and len(texto) > max_bytes:
            cortado = texto[:max_bytes]
            linhas = cortado.count("\n") + 1
            return (cortado
                    + f"\n\n… (cortado nas primeiras {linhas} linhas; "
                      f"o arquivo tem {len(texto)} caracteres)")
        return texto

    def existe(self, rel: str) -> bool:
        try:
            return self.resolver(rel, "ler").is_file()
        except SandboxError:
            return False

    def _arquivos_externos(self, raiz: Path, limite: int | None = None) -> list[str]:
        achados = []
        for pasta, subpastas, nomes in os.walk(raiz):
            base = Path(pasta)
            subpastas[:] = sorted(
                d for d in subpastas
                if not self._ignorado(d, str(base / d), True)
                and not _link(base / d))
            for nome in sorted(nomes):
                caminho = base / nome
                if self._ignorado(nome, str(caminho), False):
                    continue
                if not self._pode_ler(caminho):
                    continue
                achados.append(str(caminho))
                if limite is not None and len(achados) >= limite:
                    return achados
        return achados
