@echo off
setlocal
cd /d "%~dp0\.."

py -3 -m venv .build-venv
if errorlevel 1 exit /b 1
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r build_tools\build-requirements.txt
python build_tools\stage_ocr_runtime.py
if errorlevel 1 exit /b 1
python -m pytest -q
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
set MSIO_ONEFILE=0
pyinstaller --clean --noconfirm build_tools\MapleStoryIdleOptimizer.spec
if errorlevel 1 exit /b 1
set MSIO_ONEFILE=1
pyinstaller --clean --noconfirm build_tools\MapleStoryIdleOptimizer.spec
if errorlevel 1 exit /b 1

echo.
echo Builds are in: %CD%\dist
echo Test the -onedir build first, then the single-file EXE.
endlocal
