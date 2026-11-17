"""Vault bootstrap, note conventions, CRUD backups, and agent path access."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src.executor import Executor
from src.parser import Acao
from src.permissions import PermissionPolicy
from src.project import Project
from src.sandbox import SandboxError
from src.vault import (
    WorkspaceStore,
    atualizar_data_nota,
    conteudo_nota,
    garantir_vault,
    nome_arquivo_seguro,
)

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


with tempfile.TemporaryDirectory(prefix="vault_management_") as temp:
    base = Path(temp)
    projeto = base / "projeto"
    projeto.mkdir()
    vault = base / "notas"

    print("-- 1. inicialização segura do vault --")
    caminho = garantir_vault(vault, "Projeto exemplo")
    indice = caminho / "00 - Índice.md"
    agentes = caminho / "AGENTS.md"
    checa("cria raiz e nota central", indice.is_file())
    checa("índice é um esqueleto e não inventa fatos",
          "Propósito:** (a confirmar)" in indice.read_text(encoding="utf-8"))
    checa("cria padrão e regras de manutenção",
          (caminho / "Padrão de notas.md").is_file()
          and "ações normais" in agentes.read_text(encoding="utf-8"))
    checa("cria categorias com índices e modelos",
          (caminho / "Decisões" / "Índice.md").is_file()
          and (caminho / "Modelos" / "plano.md").is_file())
    agentes.write_text("instrução personalizada\n", encoding="utf-8")
    garantir_vault(vault, "Projeto exemplo")
    checa("bootstrap nunca sobrescreve notas existentes",
          agentes.read_text(encoding="utf-8") == "instrução personalizada\n")

    print("\n-- 2. formulário e metadados --")
    nota = conteudo_nota(
        "Plano de migração", "plano", 'arquitetura, risco: "alto"',
        "Contexto do pedido", "Passos validados.", hoje="2026-10-15")
    checa("nota usa frontmatter ISO, tags seguras e contexto",
          "criado: 2026-10-15" in nota
          and '  - "risco: \\"alto\\""' in nota
          and "Contexto do pedido" in nota)
    nome_seguro = nome_arquivo_seguro('Decisão: "Vault"?')
    checa("nome de arquivo remove caracteres inválidos",
          bool(nome_seguro)
          and not any(c in nome_seguro for c in '<>:"/\\|?*')
          and nome_seguro == nome_seguro.strip(" .-"))
    nota_atualizada = atualizar_data_nota(nota, "2026-10-16")
    checa("edição atualiza propriedade atualizado",
          "atualizado: 2026-10-16" in nota_atualizada
          and "criado: 2026-10-15" in nota_atualizada)

    print("\n-- 3. CRUD com sandbox e backup --")
    store = WorkspaceStore(vault, projeto, backup_prefix="_vault")
    store.create_folder("Notas/Teste")
    store.write_text("Notas/Teste/nota.md", "# inicial\n", create=True)
    store.write_text("Notas/Teste/nota.md", "# atualizada\n")
    backups = list((projeto / ".deepseek_ui" / "backups").rglob("nota.md"))
    checa("editar cria cópia de segurança", bool(backups))
    store.delete("Notas/Teste")
    checa("excluir pasta move conteúdo para backup",
          not (vault / "Notas" / "Teste").exists()
          and any((projeto / ".deepseek_ui" / "backups").rglob("Teste")))
    try:
        store.write_text("../fora.md", "não pode", create=True)
        escape_bloqueado = False
    except SandboxError:
        escape_bloqueado = True
    checa("recusa travessia para fora do vault", escape_bloqueado)

    print("\n-- 4. agente acessa vault externo pelo caminho virtual --")
    (vault / "Notas" / "guia.md").write_text("palavra-chave\n", encoding="utf-8")
    politica = PermissionPolicy(projeto, "folders", grants=[{
        "path": str(vault.resolve()), "read": True, "create": True,
        "edit": True, "delete": True,
    }])
    project = Project(projeto, politica)
    project.vault_root = vault.resolve()
    checa("árvore expõe o vault externo como vault/",
          "vault/Notas/guia.md" in project.arquivos())
    checa("leitura virtual chega ao arquivo vinculado",
          "palavra-chave" in project.ler("vault/Notas/guia.md"))
    checa("listagem e busca virtual funcionam",
          "guia.md" in project.listar("vault/Notas")
          and "vault/Notas/guia.md" in project.buscar(
              "palavra-chave", em="vault"))
    plano = Executor(project).preparar([
        Acao("modificar", "vault/Notas/guia.md", "conteúdo novo\n")])
    resultado = Executor(project).aplicar(plano)
    checa("ação do agente atualiza vault externo em backup isolado",
          resultado[0].status == "aplicado"
          and (vault / "Notas" / "guia.md").read_text(encoding="utf-8")
          == "conteúdo novo\n"
          and any((projeto / ".deepseek_ui" / "backups").rglob("guia.md")))

    critica = base / "protegida"
    critica.mkdir()
    with patch.dict("os.environ", {"WINDIR": str(critica),
                                   "SystemRoot": str(critica)}):
        projeto_auto = Project(
            projeto, PermissionPolicy(projeto, "project_auto"))
        projeto_auto.vault_root = critica.resolve()
        try:
            projeto_auto.resolver("vault/nota.md", "criar")
            vault_critico_bloqueado = False
        except SandboxError:
            vault_critico_bloqueado = True
    checa("auto do projeto mantém bloqueio de pastas críticas no vault",
          vault_critico_bloqueado)

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
