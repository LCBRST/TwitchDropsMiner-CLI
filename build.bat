@echo off
setlocal EnableDelayedExpansion


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
exit /b 2

:help
echo Usage:
echo   build_cli.bat
echo   build_cli.bat --one-dir
echo   build_cli.bat --upx
echo   build_cli.bat --clean
echo   build_cli.bat --name MyCLI
echo   build_cli.bat --venv path\to\venv
exit /b 0

:done_args


set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"
set "VENV_PYI=%VENV%\Scripts\pyinstaller.exe"

if not exist "%VENV_PY%" (
    echo venv not found at %VENV%
    echo Create one with:
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r requirements.txt
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


"%VENV_PYI%" --noconfirm --clean build_cli.spec


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
) else (
    echo WARN: expected binary not found at !BIN_PATH!
    exit /b 1
)

endlocal