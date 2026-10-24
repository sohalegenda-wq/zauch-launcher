@echo off
setlocal
cd /d "%~dp0"
set "ZAUCH_PY=py -3.12"
%ZAUCH_PY% -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8" >nul 2>nul
if not errorlevel 1 goto python_found
set "ZAUCH_PY=python"
%ZAUCH_PY% -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8" >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 x64 is required. Install it from python.org.
  exit /b 1
)
:python_found
if not exist .venv\Scripts\python.exe %ZAUCH_PY% -m venv .venv
if errorlevel 1 exit /b 1
set "ZAUCH_BUILD_PY=.venv\Scripts\python.exe"
%ZAUCH_BUILD_PY% -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
if errorlevel 1 (
  echo Existing .venv must use Python 3.12 x64. Recreate it and retry.
  exit /b 1
)
%ZAUCH_BUILD_PY% -m pip install --disable-pip-version-check -r requirements-dev.txt
if errorlevel 1 exit /b 1
%ZAUCH_BUILD_PY% tools\check_resources.py
if errorlevel 1 exit /b 1
set "QT_QPA_PLATFORM=offscreen"
%ZAUCH_BUILD_PY% -m pytest -q
if errorlevel 1 exit /b 1
%ZAUCH_BUILD_PY% -m PyInstaller --clean --noconfirm launcher.spec
if errorlevel 1 exit /b 1
%ZAUCH_BUILD_PY% tools\frozen_smoke.py "dist\Zauch Launcher.exe"
if errorlevel 1 exit /b 1
set "QT_QPA_PLATFORM="
echo Build complete: dist\Zauch Launcher.exe
exit /b 0
