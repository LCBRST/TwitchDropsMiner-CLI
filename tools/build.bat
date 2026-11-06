@echo off
setlocal EnableDelayedExpansion
title TwitchDropsMiner build

rem Run from the project root; this file lives in tools\.
cd /d "%~dp0.."
if errorlevel 1 (
    echo Could not change to the project root: "%~dp0.."
    pause
    exit /b 3
)


set "VENV=venv"
set DO_CLEAN=0
set ONE_FILE=1
set USE_UPX=0
set EXCLUDE_GUI=1
set APP_NAME=TwitchDropsMiner-CLI
set OPTIMIZE=1


:parse_args
if "%~1"=="" goto :done_args

if "%~1"=="--one-dir" (
    set ONE_FILE=0
    shift
    goto :parse_args
)
if "%~1"=="--one-file" (
    set ONE_FILE=1
    shift
    goto :parse_args
)
if "%~1"=="--upx" (
    set USE_UPX=1
    shift
    goto :parse_args
)
if "%~1"=="--clean" (
    set DO_CLEAN=1
    shift
    goto :parse_args
)
if "%~1"=="--name" (
    set "APP_NAME=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--venv" (
    set "VENV=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="-h" goto :help
if "%~1"=="--help" goto :help

echo Unknown flag: %1
if "%~1"=="" pause
exit /b 2

:help
echo Usage:
echo   tools\build.bat
echo   tools\build.bat --one-dir
echo   tools\build.bat --upx
echo   tools\build.bat --clean
echo   tools\build.bat --name MyCLI
echo   tools\build.bat --venv path\to\venv
exit /b 0

:done_args


set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "VENV_PYI=%VENV%\Scripts\pyinstaller.exe"

if not exist "%VENV_PY%" (
    echo venv not found: %VENV%\Scripts\python.exe
    echo Current directory: %CD%
    echo Create one from the project root with:
    echo   python -m venv venv
    echo   venv\Scripts\python -m pip install -r requirements.txt
    echo.
    echo Or point at an existing environment:
    echo   tools\build.bat --venv path\to\venv
    if "%~1"=="" pause
    exit /b 3
)


echo Installing dependencies...
"%VENV_PIP%" install --quiet --upgrade pip wheel >nul
"%VENV_PIP%" install --quiet -r requirements.txt

if not exist "%VENV_PYI%" (
    echo Installing PyInstaller...
    "%VENV_PIP%" install --quiet pyinstaller
)


if "%DO_CLEAN%"=="1" (
    echo Cleaning dist/ build/
    if exist dist rmdir /s /q dist
    if exist build rmdir /s /q build
)


set ONE_FILE=%ONE_FILE%
set USE_UPX=%USE_UPX%
set EXCLUDE_GUI=%EXCLUDE_GUI%
set APP_NAME=%APP_NAME%
set OPTIMIZE=%OPTIMIZE%

echo Building:
echo   one_file=%ONE_FILE%
echo   upx=%USE_UPX%
echo   exclude_gui=%EXCLUDE_GUI%
echo   name=%APP_NAME%


"%VENV_PYI%" --noconfirm --clean "%~dp0build_cli.spec"
if errorlevel 1 (
    echo.
    echo Build failed. See the output above.
    if "%~1"=="" pause
    exit /b 1
)


if "%ONE_FILE%"=="1" (
    set "BIN_PATH=dist\%APP_NAME%.exe"
) else (
    set "BIN_PATH=dist\%APP_NAME%\%APP_NAME%.exe"
)

if exist "!BIN_PATH!" (
    for %%F in ("!BIN_PATH!") do (
        echo Build succeeded: !BIN_PATH!
        echo Size: %%~zF bytes
    )
    if "%~1"=="" pause
    exit /b 0
)

echo WARN: expected binary not found at !BIN_PATH!
if "%~1"=="" pause
exit /b 1
