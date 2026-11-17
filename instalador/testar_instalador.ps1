# Testa o instalador na tela real: instala a versao anterior, atualiza para a
# atual, roda o autoteste do app instalado, abre pelo atalho, confere a
# primeira e a segunda execucao e desinstala. Usa pastas temporarias e sai
# com o numero de falhas (0 = tudo certo).
#
#   powershell -ExecutionPolicy Bypass -File instalador\testar_instalador.ps1 -Anterior 1.0.3 -Atual 1.0.4
#
# Precisa dos dois DeepSeekUI-Setup-<versao>.exe em dist\instalador. Recusa
# rodar se o DeepSeek UI estiver instalado de verdade: o instalador usa o mesmo
# AppId, e a desinstalacao do teste tiraria o atalho e o registro da instalacao
# real.
param(
    [Parameter(Mandatory = $true)][string]$Anterior,
    [Parameter(Mandatory = $true)][string]$Atual
)

$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $env:TEMP "dsui_instalado"
$dados = Join-Path $env:TEMP "dsui_inst_dados"
$atalho = Join-Path ([Environment]::GetFolderPath('Programs')) "DeepSeek UI.lnk"
$falhas = 0

function Checa($nome, $cond, $detalhe) {
    if ($cond) { "  ok      $nome" } else { "  FALHOU  $nome -> $detalhe"; $script:falhas++ }
}
function Registro {
    Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall |
        Get-ItemProperty | Where-Object DisplayName -eq "DeepSeek UI"
}
function Instalar($versao, $comDir) {
    $argumentos = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=`"`"")
    if ($comDir) { $argumentos += "/DIR=`"$dir`"" }
    $p = Start-Process "$raiz\dist\instalador\DeepSeekUI-Setup-$versao.exe" -ArgumentList $argumentos -PassThru
    if (-not $p.WaitForExit(180000)) { Stop-Process -Id $p.Id -Force; return -999 }
    return $p.ExitCode
}

if (Registro) {
    "Recusado: o DeepSeek UI esta instalado nesta maquina. Desinstale antes de"
    "testar, ou a desinstalacao do teste removeria o atalho e o registro dele."
    exit 99
}
foreach ($d in $dir, $dados) { if (Test-Path $d) { Remove-Item -Recurse -Force $d -Confirm:$false } }
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue

"-- 1. instalar $Anterior e atualizar por cima para $Atual --"
Checa "instala $Anterior" ((Instalar $Anterior $true) -eq 0) ""
Checa "registro apos instalar" ((Registro).DisplayVersion -eq $Anterior) (Registro).DisplayVersion
Checa "atualiza para $Atual (mesma pasta, sem /DIR)" ((Instalar $Atual $false) -eq 0) ""
Checa "registro apos atualizar" ((Registro).DisplayVersion -eq $Atual) (Registro).DisplayVersion
Checa "continua na mesma pasta" (Test-Path "$dir\DeepSeekUI.exe") $dir
Checa "atalho no menu Iniciar" (Test-Path $atalho) $atalho

"-- 2. autoteste do app instalado, janela real, de outra pasta --"
$env:DEEPSEEK_UI_DADOS = $dados
$a = Start-Process "$dir\DeepSeekUI.exe" -ArgumentList "--verificar" -PassThru -WorkingDirectory $env:USERPROFILE
if (-not $a.WaitForExit(120000)) { Stop-Process -Id $a.Id -Force; $codigo = -999 } else { $codigo = $a.ExitCode }
Get-Content "$dados\logs\deepseek_ui.log" -Encoding utf8 | Where-Object { $_ -match "verificar:" } | ForEach-Object { "      $_" }
Checa "autoteste do instalado: 0 falhas" ($codigo -eq 0) "saida $codigo"

"-- 3. abrir pelo atalho, uso normal --"
Set-Content "$dados\primeira_execucao.ok" "teste" -Encoding ascii
$antes = @((Get-Process DeepSeekUI -ErrorAction SilentlyContinue).Id)
Start-Process $atalho
Start-Sleep -Seconds 10
$proc = Get-Process DeepSeekUI -ErrorAction SilentlyContinue | Where-Object { $antes -notcontains $_.Id }
Checa "app aberto pelo atalho continua rodando" ($null -ne $proc) "processo sumiu"
Checa "janela principal 'DeepSeek UI'" ($proc.MainWindowTitle -eq "DeepSeek UI") $proc.MainWindowTitle
$log = Get-Content "$dados\logs\deepseek_ui.log" -Raw -Encoding utf8
Checa "sem erro no log" ($log -notmatch "Traceback|Error|Erro") ($log.Substring([Math]::Max(0, $log.Length - 400)))
if ($proc) { $proc | Stop-Process -Force }
Start-Sleep -Seconds 1

"-- 4. primeira execucao real: dialogo de importacao --"
Remove-Item -Recurse -Force $dados -Confirm:$false
$b = Start-Process "$dir\DeepSeekUI.exe" -PassThru
Start-Sleep -Seconds 8
$b.Refresh()
Checa "dialogo de primeira execucao aparece" ($b.MainWindowTitle -like "DeepSeek UI*primeira*") $b.MainWindowTitle
Checa "marca de primeira execucao gravada" (Test-Path "$dados\primeira_execucao.ok") ""
Stop-Process -Id $b.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

"-- 5. segunda execucao abre direto a janela principal --"
$c = Start-Process "$dir\DeepSeekUI.exe" -PassThru
Start-Sleep -Seconds 8
$c.Refresh()
Checa "segunda execucao: janela 'DeepSeek UI'" ($c.MainWindowTitle -eq "DeepSeek UI") $c.MainWindowTitle
$log = Get-Content "$dados\logs\deepseek_ui.log" -Raw -Encoding utf8
Checa "sem erro no log" ($log -notmatch "Traceback|Error") $log
Stop-Process -Id $c.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item Env:DEEPSEEK_UI_DADOS

"-- 6. desinstalar --"
$u = Start-Process "$dir\unins000.exe" -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru
$u.WaitForExit(120000) | Out-Null
Start-Sleep -Seconds 3
Checa "pasta removida" (-not (Test-Path "$dir\DeepSeekUI.exe")) ""
Checa "atalho removido" (-not (Test-Path $atalho)) ""
Checa "registro removido" ($null -eq (Registro)) ""
foreach ($d in $dir, $dados) { if (Test-Path $d) { Remove-Item -Recurse -Force $d -Confirm:$false } }
"==> falhas: $falhas"
exit $falhas
