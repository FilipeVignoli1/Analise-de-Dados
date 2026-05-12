@echo off
setlocal EnableExtensions

cd /d "%~dp0"
title GEREL Produtividade ^| Importador de Dados
color 0B

cls
call :banner
echo.
echo  Sistema iniciado em: %date% %time:~0,8%
echo  Diretorio base....: %~dp0
echo.

call :step "1/4" "Verificando Python"
python --version >nul 2>&1
if errorlevel 1 (
    call :erro "Python nao encontrado. Verifique a instalacao antes de continuar."
    goto :fim_erro
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  OK  %%v
echo.

call :step "2/4" "Verificando arquivos do sistema"
if not exist "importador.py" (
    call :erro "Arquivo importador.py nao encontrado neste diretorio."
    goto :fim_erro
)
if not exist "gerel_produtividade.db" (
    call :erro "Banco gerel_produtividade.db nao encontrado neste diretorio."
    goto :fim_erro
)
if not exist "dados" (
    call :erro "Pasta dados nao encontrada neste diretorio."
    goto :fim_erro
)
echo  OK  Arquivos principais localizados.
echo.

call :step "3/4" "Verificando bibliotecas"
python -m pip install pandas sqlalchemy openpyxl customtkinter --quiet
if errorlevel 1 (
    call :erro "Falha ao verificar ou instalar bibliotecas Python."
    goto :fim_erro
)
echo  OK  Bibliotecas prontas.
echo.

call :step "4/4" "Abrindo interface grafica"
echo  Use a janela do sistema para selecionar a tabela e importar os arquivos.
echo  Os arquivos de entrada ficam na pasta: dados
echo.
echo ------------------------------------------------------------
python app_importador.py
set "CODIGO_SAIDA=%errorlevel%"
echo ------------------------------------------------------------
echo.

if not "%CODIGO_SAIDA%"=="0" (
    call :erro "O importador foi encerrado com erro. Codigo: %CODIGO_SAIDA%"
    goto :fim_erro
)

color 0A
echo ============================================================
echo  PROCESSO FINALIZADO COM SUCESSO
echo ============================================================
echo.
pause
exit /b 0

:fim_erro
color 0C
echo.
echo ============================================================
echo  PROCESSO INTERROMPIDO
echo ============================================================
echo.
pause
exit /b 1

:banner
echo ============================================================
echo  GEREL PRODUTIVIDADE
echo  IMPORTADOR DE DADOS
echo ============================================================
exit /b 0

:step
echo [ETAPA %~1] %~2
echo ------------------------------------------------------------
exit /b 0

:erro
echo.
echo  ERRO: %~1
exit /b 0
