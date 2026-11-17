"""Testa resolução de caminhos e permissões por escopo."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from src.permissions import PermissionPolicy
from src.sandbox import SandboxError
from src.session import ProjectSession
from src.executor import Executor
from src.parser import Acao
from src.project import Project

ok = fail = 0


def checa(nome, condicao, detalhe=""):
    global ok, fail
    if condicao:
        print(f"  ok      {nome}")
        ok += 1
    else:
        print(f"  FALHOU  {nome} -> {detalhe}")
        fail += 1


def recusa(nome, callback):
    try:
        callback()
    except SandboxError:
        checa(nome, True)
    else:
        checa(nome, False, "esperava SandboxError")


with tempfile.TemporaryDirectory(prefix="permissions_") as temp:
    base = Path(temp)
    projeto = base / "projeto"
    externa = base / "externa"
    projeto.mkdir()
    externa.mkdir()
    (projeto / "app.py").write_text("x = 1", encoding="utf-8")
    (externa / "dados.txt").write_text("dados", encoding="utf-8")

    print("-- 1. perfil padrão restrito ao projeto --")
    policy = PermissionPolicy(projeto)
    checa("lê caminho relativo do projeto",
          policy.resolve("app.py", "ler") == (projeto / "app.py").resolve())
    checa("escrita no projeto segue autorizada para revisão",
          policy.resolve("novo.py", "criar") == (projeto / "novo.py").resolve())
    recusa("recusa travessia", lambda: policy.resolve("../externa/dados.txt", "ler"))
    recusa("recusa caminho absoluto externo",
           lambda: policy.resolve(str(externa / "dados.txt"), "ler"))
    checa("perfil exige confirmação", policy.requires_confirmation)
    checa("consentimento de leitura vem ativo por padrão",
          policy.requires_read_confirmation)
    antiga = PermissionPolicy.from_dict(projeto, {"mode": "project_confirm"})
    checa("configuração antiga também exige consentimento",
          antiga.requires_read_confirmation)

    print("\n-- 1b. perfil automático restrito ao projeto --")
    automatico_projeto = PermissionPolicy(projeto, "project_auto")
    checa("auto aceita leitura e CRUD no projeto sem confirmar comandos",
          all(automatico_projeto.resolve("app.py", operacao)
              == (projeto / "app.py").resolve()
              for operacao in ("ler", "criar", "modificar", "apagar"))
          and not automatico_projeto.requires_file_confirmation
          and not automatico_projeto.requires_read_confirmation
          and automatico_projeto.requires_command_confirmation)
    recusa("auto de projeto ainda recusa caminho absoluto externo",
           lambda: automatico_projeto.resolve(str(externa / "dados.txt"), "ler"))

    print("\n-- 2. permissões granulares por pasta --")
    policy = PermissionPolicy(projeto, "folders", [
        {"path": str(projeto), "read": True, "create": True,
         "edit": False, "delete": False},
        {"path": str(externa), "read": True, "create": False,
         "edit": True, "delete": False},
    ])
    checa("lê raiz explicitamente permitida",
          policy.resolve("app.py", "ler") == (projeto / "app.py").resolve())
    checa("cria na raiz permitida",
          policy.resolve("novo.py", "criar") == (projeto / "novo.py").resolve())
    recusa("nega edição quando desmarcada",
           lambda: policy.resolve("app.py", "modificar"))
    checa("lê pasta externa permitida",
          policy.resolve(str(externa / "dados.txt"), "ler")
          == (externa / "dados.txt").resolve())
    checa("edita pasta externa permitida",
          policy.resolve(str(externa / "novo.txt"), "modificar")
          == (externa / "novo.txt").resolve())
    checa("grant por pasta substitui confirmação arquivo a arquivo",
          not policy.requires_file_confirmation)
    checa("comandos ficam automáticos em Pastas escolhidas",
          not policy.requires_command_confirmation)
    recusa("nega exclusão externa",
           lambda: policy.resolve(str(externa / "dados.txt"), "apagar"))
    recusa("editar não concede criar",
           lambda: policy.resolve(str(externa / "nova-nota.md"), "criar"))
    recusa("nega caminho externo sem concessão",
           lambda: policy.resolve(str(base / "sem-permissao.txt"), "ler"))
    plano = Executor(Project(projeto, policy)).preparar([
        Acao("modificar", str(externa / "dados.txt"), "alterado")])
    checa("executor prepara alteração externa autorizada",
          len(plano) == 1 and plano[0].aplicavel,
          plano[0].erro if plano else "nenhum plano")
    resultado = Executor(Project(projeto, policy)).aplicar(plano)
    checa("alteração externa mantém backup",
          resultado[0].status == "aplicado"
          and (externa / "dados.txt").read_text(encoding="utf-8") == "alterado"
          and list((projeto / ".deepseek_ui" / "backups").rglob("dados.txt")))

    print("\n-- 3. mapa/lista/busca respeitam grants de leitura --")
    (projeto / "permitida").mkdir()
    (projeto / "privada").mkdir()
    (projeto / "permitida" / "publico.txt").write_text(
        "texto autorizado", encoding="utf-8")
    (projeto / "privada" / "segredo.txt").write_text(
        "texto privado", encoding="utf-8")
    somente_subpasta = PermissionPolicy(projeto, "folders", [
        {"path": str(projeto), "read": False, "create": False,
         "edit": False, "delete": False},
        {"path": str(projeto / "permitida"), "read": True, "create": False,
         "edit": False, "delete": False},
    ])
    projeto_limitado = Project(projeto, somente_subpasta)
    mapa_limitado = projeto_limitado.mapa()
    checa("mapa expõe apenas arquivos com grant de leitura",
          "publico.txt" in mapa_limitado and "segredo.txt" not in mapa_limitado,
          mapa_limitado)
    checa("busca da raiz não devolve conteúdo sem grant",
          "texto autorizado" in projeto_limitado.buscar("texto")
          and "texto privado" not in projeto_limitado.buscar("texto"))
    recusa("listar subpasta sem grant de leitura",
           lambda: projeto_limitado.listar("privada"))

    (externa / "visivel.txt").write_text("fora autorizada", encoding="utf-8")
    pasta_oculta = externa / "oculta"
    pasta_oculta.mkdir()
    (pasta_oculta / "negado.txt").write_text("fora privada", encoding="utf-8")
    policy_externa = PermissionPolicy(projeto, "folders", [
        {"path": str(externa), "read": True, "create": False,
         "edit": False, "delete": False},
        {"path": str(pasta_oculta), "read": False, "create": False,
         "edit": False, "delete": False},
    ])
    arvore_externa = Project(projeto, policy_externa).listar(str(externa))
    checa("listagem externa também filtra grants mais específicos",
          "visivel.txt" in arvore_externa and "negado.txt" not in arvore_externa,
          arvore_externa)

    print("\n-- 4. acesso amplo e diretórios críticos do Windows --")
    critico = base / "sistema-protegido"
    critico.mkdir()
    with patch.dict(os.environ, {"WINDIR": str(critico), "SystemRoot": str(critico)}):
        amplo = PermissionPolicy(projeto, "computer_confirm")
        amplo_auto = PermissionPolicy(projeto, "computer_auto")
    checa("modo amplo com confirmação",
          amplo.resolve(str(externa / "dados.txt"), "ler")
          == (externa / "dados.txt").resolve()
          and amplo.requires_confirmation)
    checa("modo amplo sem confirmação",
          amplo_auto.resolve(str(externa / "novo.txt"), "criar")
          == (externa / "novo.txt").resolve()
          and not amplo_auto.requires_confirmation)
    recusa("modo amplo bloqueia diretório crítico",
           lambda: amplo_auto.resolve(str(critico / "kernel.sys"), "modificar"))
    drive = base.drive or os.environ.get("SystemDrive", "C:")
    raiz_sistema = Path(drive + "\\")
    with patch.dict(os.environ, {"SystemDrive": drive}):
        policy_raiz_sistema = PermissionPolicy(projeto, "computer_auto")
    recusa("modo amplo bloqueia arquivos na raiz do disco do sistema",
           lambda: policy_raiz_sistema.resolve(
               str(raiz_sistema / "arquivo-sistema.test"), "criar"))
    try:
        with patch.dict(os.environ, {"WINDIR": str(critico),
                                     "SystemRoot": str(critico)}):
            PermissionPolicy(projeto, "folders", [
                {"path": str(critico), "read": True, "create": True,
                 "edit": True, "delete": True}])
    except SandboxError:
        checa("recusa cadastrar pasta crítica", True)
    else:
        checa("recusa cadastrar pasta crítica", False)

    print("\n-- 5. persistência sem apagar sessão/vault --")
    policy = PermissionPolicy(projeto, "folders", [
        {"path": str(projeto), "read": True, "create": False,
         "edit": False, "delete": False},
    ], confirm_reads=False)
    sessao = ProjectSession(projeto)
    sessao.salvar_vault(str(externa))
    sessao.salvar_url("https://chat.deepseek.com/a/chat/s/"
                      "3f2a9c10-1b4d-4e77-9c3a-5d6e7f801122")
    config = policy.to_dict()
    checa("salva permissões",
          sessao.salvar_permissoes(config))
    nova = ProjectSession(projeto)
    restaurada = PermissionPolicy.from_dict(projeto, nova.permissoes())
    checa("modo e grants restaurados",
          restaurada.to_dict() == config and nova.vault_path() == str(externa.resolve())
          and nova.url() is not None
          and not restaurada.requires_read_confirmation)

print(f"\n==> {ok} corretos, {fail} falhas")
sys.exit(1 if fail else 0)
