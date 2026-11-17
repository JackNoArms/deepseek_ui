@echo off
setlocal
cd /d "%~dp0"

rem DeepSeek UI - prepara o ambiente Python sozinho e abre o app.
rem   executar_main.bat             prepara se precisar e abre
rem   executar_main.bat --preparar  so prepara e sai
rem
rem Usa .venv na pasta do app. Cria se faltar ou estiver quebrado e roda
rem pip install sempre que o requirements.txt mudar: a copia instalada fica
rem em .venv\requirements.instalado.

set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"
set "MARCA=%VENV%\requirements.instalado"
set "CHECA=import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"

"%PY%" -c "%CHECA%" >nul 2>&1
if errorlevel 1 call :criar_venv || goto :falhou

fc /b "requirements.txt" "%MARCA%" >nul 2>&1
if errorlevel 1 call :instalar || goto :falhou

if /i "%~1"=="--preparar" (
    echo Ambiente pronto.
    exit /b 0
)

"%PY%" main.py
set "SAIDA=%errorlevel%"
if not "%SAIDA%"=="0" pause
exit /b %SAIDA%


:criar_venv
call :achar_python || exit /b 1
echo Criando o ambiente Python em .venv ...
if exist "%VENV%" rmdir /s /q "%VENV%"
%BASE% -m venv "%VENV%" || exit /b 1
exit /b 0


:instalar
echo Instalando dependencias do requirements.txt ...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt || exit /b 1
copy /y "requirements.txt" "%MARCA%" >nul
exit /b 0


:achar_python
set "BASE="
py -3 -c "%CHECA%" >nul 2>&1 && set "BASE=py -3"
if not defined BASE python -c "%CHECA%" >nul 2>&1 && set "BASE=python"
if defined BASE exit /b 0

echo Python 3.10 ou mais novo nao foi encontrado.
where winget >nul 2>&1
if errorlevel 1 (
    echo Instale pelo site python.org/downloads e rode este arquivo de novo.
    exit /b 1
)
choice /c SN /m "Instalar o Python 3.12 agora pelo winget"
if errorlevel 2 exit /b 1
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
set "NOVO=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%NOVO%" (
    set BASE="%NOVO%"
    exit /b 0
)
echo Python instalado. Feche esta janela e abra o executar_main.bat de novo.
exit /b 1


:falhou
echo.
echo Nao consegui preparar o ambiente. Veja a mensagem acima.
pause
exit /b 1
