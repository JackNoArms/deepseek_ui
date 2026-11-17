; Instalador do DeepSeek UI (Inno Setup 6). Rodar pelo build.bat, que passa
; a versão:  ISCC /DAppVersion=1.0.0 instalador\deepseek_ui.iss
;
; Instala por usuário, sem administrador, em %LOCALAPPDATA%\Programs\DeepSeek UI.
; Os dados do usuário (login do DeepSeek, pareamento do celular, config, log)
; ficam em %LOCALAPPDATA%\DeepSeek UI (ver src/caminhos.py) e sobrevivem à
; desinstalação, a menos que a pessoa peça para apagar.
;
; Modo de atualização (usado pelo updater, ver ADR-024):
;   DeepSeekUI-Setup-<versao>.exe /SILENT /CLOSEAPPLICATIONS /NORESTART /RELAUNCH=1
; O parâmetro é `/RELAUNCH=1` (com valor) porque o Inno só expõe parâmetros
; no formato `/NOME=valor` via constante `param`. Uma flag pura `/RELAUNCH`
; não é detectável no Pascal Script do Inno.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "DeepSeek UI"
#define AppExe "DeepSeekUI.exe"

[Setup]
AppId={{8F3C2A1E-6B7D-4E59-9A0C-5D2E7B41C3F8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\instalador
OutputBaseFilename=DeepSeekUI-Setup-{#AppVersion}
SetupIconFile=..\build\deepseek_ui.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na área de trabalho"; Flags: unchecked
Name: "chrome"; Description: "Instalar o Google Chrome pelo winget (não encontrei o Chrome neste computador)"; Check: ChromeFaltaComWinget
Name: "tailscale"; Description: "Instalar o Tailscale pelo winget, para usar o app pelo celular (pede administrador)"; Flags: unchecked; Check: TemWinget

[Files]
Source: "..\dist\DeepSeekUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Atualização: tira do pacote anterior o que não existe mais no novo.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: atalho

[Run]
Filename: "{code:CaminhoWinget}"; Parameters: "install -e --id Google.Chrome --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando o Google Chrome..."; Tasks: chrome; Flags: waituntilterminated
Filename: "{code:CaminhoWinget}"; Parameters: "install -e --id tailscale.tailscale --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando o Tailscale..."; Tasks: tailscale; Flags: waituntilterminated
Filename: "https://www.google.com/chrome/"; Description: "Baixar o Google Chrome (o app precisa dele)"; Flags: shellexec postinstall skipifsilent unchecked; Check: ChromeFaltaSemWinget

; Modo interativo: checkbox "Abrir o app" (comportamento antigo), pulado
; quando /RELAUNCH=1 já vai cuidar disso.
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent unchecked; Check: NaoFoiRelaunch
; Modo atualização (silencioso ou interativo com /RELAUNCH=1): abre o app
; novo sempre que o updater passou /RELAUNCH=1. Sem checkbox, sem depender
; do usuário.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: FoiRelaunch

[Code]
function CaminhoWinget(Param: String): String;
begin
  Result := ExpandConstant('{localappdata}\Microsoft\WindowsApps\winget.exe');
end;

function TemWinget: Boolean;
begin
  Result := FileExists(CaminhoWinget(''));
end;

function ChromeInstalado: Boolean;
begin
  Result :=
    RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') or
    RegKeyExists(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') or
    FileExists(ExpandConstant('{commonpf}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{commonpf32}\Google\Chrome\Application\chrome.exe')) or
    FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe'));
end;

function ChromeFaltaComWinget: Boolean;
begin
  Result := (not ChromeInstalado) and TemWinget;
end;

function ChromeFaltaSemWinget: Boolean;
begin
  Result := (not ChromeInstalado) and (not TemWinget);
end;

// Detecta `/RELAUNCH=1`. O Inno só expõe parâmetros no formato
// `/NOME=valor` via a constante de string `param`; uma flag pura
// `/RELAUNCH` não é detectável no Pascal Script do Inno.
function FoiRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function NaoFoiRelaunch: Boolean;
begin
  Result := not FoiRelaunch;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Pasta: String;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  Pasta := ExpandConstant('{localappdata}\{#AppName}');
  if UninstallSilent or not DirExists(Pasta) then
    exit;
  if MsgBox('Apagar também os seus dados do DeepSeek UI?' + #13#10#13#10 +
            'Login do DeepSeek, pareamento do celular, configurações e log em:' + #13#10 +
            Pasta + #13#10#13#10 +
            'Escolha Não para manter e reaproveitar numa próxima instalação.',
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    DelTree(Pasta, True, True, True);
end;
