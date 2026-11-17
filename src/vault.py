"""Vault bootstrap and safe filesystem operations for project workspaces."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.backup import Backup
from src.project import IGNORAR
from src.sandbox import Sandbox, SandboxError


PASTAS_PADRAO = ("Decisões", "Diário", "Notas", "Planos", "Referência", "Modelos")

PADRAO_NOTAS = """\
# Padrão de notas

Notas em Markdown simples, uma ideia principal por nota. O vault é navegável
sem plugins: use títulos claros, pastas previsíveis e links internos
`[[Nome da nota]]`; prefira caminhos relativos com `/` para links ambíguos.

## Metadados

Use YAML no início de notas novas:

```yaml
---
tipo: nota
criado: YYYY-MM-DD
atualizado: YYYY-MM-DD
tags:
  - projeto
---
```

Use `status` apenas quando fizer sentido (por exemplo, em planos e decisões).
Datas são ISO `YYYY-MM-DD`. Atualize `atualizado` quando uma nota mudar. Não
grave segredos, credenciais ou dados pessoais desnecessários.

## Organização e manutenção

- `00 - Índice.md` é a página central: propósito, visão geral, estrutura,
  decisões, estado e links para notas importantes.
- Use `Decisões/`, `Planos/`, `Referência/`, `Notas/` e `Diário/` por tipo de
  conteúdo; evite criar pastas profundas sem necessidade.
- Ao criar ou mover uma nota, atualize os links do índice e evite links
  quebrados. Não duplique informação que já tem uma nota canônica.
- Registre fatos do projeto com contexto, fonte/evidência e data; diferencie
  fatos verificados de hipóteses e pendências.
- Registre apenas informação durável: decisões, arquitetura, riscos, planos,
  procedimentos e estado validado. Não registre cada pedido ou alteração
  rotineira.
"""

AGENTS_PADRAO = """\
# Instruções do projeto

Consulte `vault/00 - Índice.md` antes de trabalhar quando precisar de contexto
persistente do projeto. Use as notas vinculadas como fonte; confirme no código
quando uma afirmação puder ter ficado desatualizada.

Para cada pedido novo, avalie se há conhecimento durável que mereça entrar no
vault. Só proponha uma atualização quando houver decisão, arquitetura, risco,
plano, procedimento ou estado verificado relevante. Explique no texto da
resposta o contexto, o motivo e as notas que pretende criar/alterar; use a data
atual em `criado`/`atualizado`, mantenha `00 - Índice.md` e links consistentes,
e siga `vault/Padrão de notas.md`. Não registre tarefas rotineiras nem fatos
não verificados. Alterações no vault devem ser submetidas como ações normais
para revisão do usuário no aplicativo; nunca presuma autorização para gravar.
"""


def _quote_yaml(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def conteudo_indice(nome_projeto: str, hoje: str | None = None) -> str:
    hoje = hoje or date.today().isoformat()
    return f"""\
---
tipo: indice
projeto: {_quote_yaml(nome_projeto)}
criado: {hoje}
atualizado: {hoje}
tags:
  - projeto
---

# {nome_projeto}

> Página central do projeto. Preencha com fatos verificados; não trate os
> marcadores abaixo como informação já confirmada.

## Visão geral

- **Propósito:** (a confirmar)
- **Usuários/escopo:** (a confirmar)
- **Estado:** (a confirmar)

## Estrutura e arquitetura

- **Pontos de entrada:** (a confirmar)
- **Componentes principais:** (a confirmar)
- **Tecnologias:** (a confirmar)

## Como executar e verificar

- **Instalação/execução:** (a confirmar)
- **Testes e validações:** (a confirmar)

## Notas importantes

- [[Padrão de notas]]
- [[Estado atual]]
- Decisões: [[Decisões/Índice]]
- Planos: [[Planos/Índice]]
- Referências: [[Referência/Índice]]
- Notas: [[Notas/Índice]]
- Diário: [[Diário/Índice]]

## Pendências

- (a confirmar)

## Atualizações

- {hoje}: vault inicializado; conteúdo do projeto ainda precisa ser validado.
"""


def _modelo_nota(tipo: str) -> str:
    return f"""\
---
tipo: {tipo.lower()}
criado: "{{{{date:YYYY-MM-DD}}}}"
atualizado: "{{{{date:YYYY-MM-DD}}}}"
titulo: "{{{{title}}}}"
tags:
  - projeto
---

# {{{{title}}}}

## Contexto

(Preencha o contexto e a origem da informação.)

## Conteúdo

(Registre fatos, decisão, passos ou referências verificáveis.)

## Próximos passos

-

## Referências

-
"""


def _pagina_categoria(titulo: str, nome_projeto: str, hoje: str) -> str:
    return f"""\
---
tipo: indice
criado: {hoje}
atualizado: {hoje}
tags:
  - projeto
---

# {titulo}

Notas desta categoria no projeto [[{nome_projeto}]].

## Notas

-
"""


def garantir_vault(caminho: str | Path, nome_projeto: str) -> Path:
    """Create a useful starter vault without overwriting any existing content."""
    root = Path(caminho).expanduser().absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        raise SandboxError("A raiz do vault não pode ser symlink ou junction.")
    sandbox = Sandbox(root)
    hoje = date.today().isoformat()
    for pasta in PASTAS_PADRAO:
        sandbox.resolve(pasta).mkdir(exist_ok=True)

    padroes = {
        "00 - Índice.md": conteudo_indice(nome_projeto, hoje),
        "AGENTS.md": AGENTS_PADRAO,
        "Padrão de notas.md": PADRAO_NOTAS,
        "Estado atual.md": f"""\
---
tipo: estado
criado: {hoje}
atualizado: {hoje}
tags:
  - projeto
---

# Estado atual de {nome_projeto}

> Preencha após inspecionar e validar o projeto; não invente conclusões.

## O que existe

- (a confirmar)

## Verificações realizadas

- (a confirmar; inclua comando, data e resultado)

## Pendências e riscos

- (a confirmar)
""",
    }
    for pasta in ("Decisões", "Diário", "Notas", "Planos", "Referência"):
        padroes[f"{pasta}/Índice.md"] = _pagina_categoria(
            pasta, nome_projeto, hoje)
    for tipo, pasta in (
        ("nota", "Notas"),
        ("decisao", "Decisões"),
        ("plano", "Planos"),
        ("referencia", "Referência"),
    ):
        padroes[f"Modelos/{tipo}.md"] = _modelo_nota(tipo)

    for rel, conteudo in padroes.items():
        destino = sandbox.resolve(rel)
        try:
            with destino.open("x", encoding="utf-8", newline="") as arquivo:
                arquivo.write(conteudo)
        except FileExistsError:
            continue
    return root.resolve(strict=True)


def nome_arquivo_seguro(titulo: str) -> str:
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", titulo).strip(" .-")
    nome = re.sub(r"\s+", " ", nome)
    if not nome or nome.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Informe um título que possa ser usado como nome de arquivo.")
    return nome


def conteudo_nota(titulo: str, tipo: str, tags: str = "", contexto: str = "",
                  conteudo: str = "", hoje: str | None = None) -> str:
    hoje = hoje or date.today().isoformat()
    titulo = " ".join(titulo.split())
    if not titulo:
        raise ValueError("O título da nota não pode ficar vazio.")
    tag_list = []
    for tag in tags.split(","):
        tag = tag.strip().lstrip("#")
        if tag and tag not in tag_list:
            tag_list.append(tag)
    tag_yaml = "".join(
        f"  - {_quote_yaml(tag)}\n" for tag in tag_list) or '  - "projeto"\n'
    linhas = [
        "---",
        f"tipo: {tipo.lower()}",
        f"criado: {hoje}",
        f"atualizado: {hoje}",
        "tags:",
        tag_yaml.rstrip("\n"),
        "---",
        "",
        f"# {titulo.strip()}",
        "",
        "## Contexto",
        "",
        contexto.strip() or "(Contexto a preencher.)",
        "",
        "## Conteúdo",
        "",
        conteudo.strip() or "(Conteúdo a preencher.)",
        "",
        "## Próximos passos",
        "",
        "- ",
        "",
        "## Referências",
        "",
        "- ",
        "",
    ]
    return "\n".join(linhas)


def atualizar_data_nota(texto: str, hoje: str | None = None) -> str:
    """Refresh an existing YAML `atualizado` property, without inventing YAML."""
    hoje = hoje or date.today().isoformat()
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?=\r?\n|\Z)", texto, re.DOTALL)
    if not match:
        return texto
    frontmatter = match.group(1)
    if re.search(r"(?m)^atualizado\s*:", frontmatter):
        novo_frontmatter = re.sub(
            r"(?m)^atualizado\s*:.*$", f"atualizado: {hoje}", frontmatter, count=1)
    else:
        novo_frontmatter = f"{frontmatter}\natualizado: {hoje}"
    return texto[:match.start(1)] + novo_frontmatter + texto[match.end(1):]


@dataclass(frozen=True)
class WorkspaceEntry:
    path: str
    is_dir: bool


class WorkspaceStore:
    """Bounded tree and atomic CRUD, with recoverable backups."""

    def __init__(self, root: str | Path, backup_root: str | Path,
                 backup_prefix: str = "", project_tree: bool = False):
        self.root = Path(root).resolve(strict=True)
        self.sandbox = Sandbox(self.root)
        self.backup = Backup(backup_root)
        self.backup_prefix = backup_prefix.strip("/")
        self.project_tree = project_tree

    def _resolve(self, rel: str) -> Path:
        if self.project_tree:
            partes = rel.replace("\\", "/").split("/")
            ignorada = next((parte for parte in partes if parte in IGNORAR), None)
            if ignorada:
                raise SandboxError(f"A pasta interna do app não é editável pela árvore: {ignorada}")
        return self.sandbox.resolve(rel)

    def entries(self) -> list[WorkspaceEntry]:
        found: list[WorkspaceEntry] = []

        def visit(folder: Path, prefix: str = ""):
            try:
                items = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            except OSError as error:
                raise OSError(f"Não consegui listar {folder}: {error}") from error
            for item in items:
                if item.is_symlink() or (
                        hasattr(item, "is_junction") and item.is_junction()):
                    continue
                rel = f"{prefix}/{item.name}".strip("/")
                if item.is_dir():
                    if self.project_tree and item.name in IGNORAR:
                        continue
                    found.append(WorkspaceEntry(rel, True))
                    visit(item, rel)
                else:
                    found.append(WorkspaceEntry(rel, False))

        visit(self.root)
        return found

    def read_text(self, rel: str) -> str:
        path = self._resolve(rel)
        if not path.is_file():
            raise SandboxError(f"Não é um arquivo: {rel}")
        try:
            if path.stat().st_size > self.sandbox.max_bytes:
                raise SandboxError(
                    f"Arquivo grande demais para editar pela interface: {rel}")
            return path.read_text(encoding="utf-8")
        except UnicodeError as error:
            raise SandboxError(f"O arquivo não é texto UTF-8: {rel}") from error
        except OSError as error:
            raise OSError(f"Não consegui ler {rel}: {error}") from error

    def create_folder(self, rel: str):
        path = self._resolve(rel)
        if path.exists():
            raise FileExistsError(f"Já existe: {rel}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"A pasta pai não existe: {path.parent}")
        path.mkdir()

    def write_text(self, rel: str, content: str, *, create: bool = False):
        path = self._resolve(rel)
        self.sandbox.check_size(content, rel)
        if path.exists() and path.is_dir():
            raise IsADirectoryError(f"É uma pasta: {rel}")
        if create and path.exists():
            raise FileExistsError(f"Já existe: {rel}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"A pasta pai não existe: {path.parent}")
        if path.is_file():
            self.backup.salvar(path, self._backup_rel(rel))
        fd, temporary = tempfile.mkstemp(
            dir=str(path.parent), prefix=".deepseek-ui-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as arquivo:
                arquivo.write(content)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def delete(self, rel: str):
        path = self._resolve(rel)
        if not path.exists():
            raise FileNotFoundError(f"Não existe: {rel}")
        if path == self.root:
            raise SandboxError("Não é permitido excluir a raiz.")
        if path.is_dir() and any(path.iterdir()):
            # Moving a directory to the backup preserves all its descendants.
            self.backup.mover(path, self._backup_rel(rel))
        else:
            self.backup.mover(path, self._backup_rel(rel))

    def _backup_rel(self, rel: str) -> str:
        return f"{self.backup_prefix}/{rel}".strip("/")
