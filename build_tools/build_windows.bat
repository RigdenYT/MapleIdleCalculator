@echo off
setlocal
cd /d "%~dp0\.."

python -m venv .build-venv
if errorlevel 1 exit /b 1
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r build_tools\build-requirements.txt
if errorlevel 1 exit /b 1
python build_tools\release_metadata.py --write-windows-version
if errorlevel 1 exit /b 1
python build_tools\release_metadata.py --check
if errorlevel 1 exit /b 1
python build_tools\stage_ocr_runtime.py
if errorlevel 1 exit /b 1
python -m pytest -q
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release
set MSIO_ONEFILE=0
pyinstaller --clean --noconfirm build_tools\MapleStoryIdleOptimizer.spec
if errorlevel 1 exit /b 1
set MSIO_ONEFILE=1
pyinstaller --clean --noconfirm build_tools\MapleStoryIdleOptimizer.spec
if errorlevel 1 exit /b 1
python build_tools\package_release_artifacts.py
if errorlevel 1 exit /b 1

echo.
echo Raw PyInstaller builds: %CD%\dist
echo Upload-ready files:      %CD%\release
echo Test the -onedir archive first, then the single-file EXE.
endlocal
