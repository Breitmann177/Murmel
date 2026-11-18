@echo off
setlocal
cd /d "%~dp0"
title Murmel installieren
echo.
echo  Murmel wird installiert ...
echo.

rem --- Python 3.10 bis 3.13 finden -------------------------------------------
set "PY="
py -3.12 -c "" >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 -c "import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,13))" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,13))" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

rem --- Virtuelle Umgebung und Pakete --------------------------------------------
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
set "REQ=requirements.txt"
where nvidia-smi >nul 2>nul && set "REQ=requirements-gpu.txt"
if "%REQ%"=="requirements-gpu.txt" echo  NVIDIA-Grafikkarte gefunden: GPU-Pakete werden mitinstalliert.
".venv\Scripts\python.exe" -m pip install -r "%REQ%"
if errorlevel 1 goto fail

rem --- Verknuepfung im Startmenue ----------------------------------------------
set "MURMEL_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=$env:MURMEL_DIR; $s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs')+'\Murmel.lnk'); $s.TargetPath=$d+'.venv\Scripts\pythonw.exe'; $s.Arguments='\"'+$d+'main.pyw\"'; $s.WorkingDirectory=$d; $s.IconLocation=$d+'assets\murmel.ico'; $s.Save()"

echo.
echo  Fertig! Murmel steht jetzt im Startmenue und startet gleich.
echo  Beim ersten Start wird das Sprachmodell geladen (einmalig, bis ~1,6 GB).
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.pyw"
pause
exit /b 0

:nopython
echo  Python 3.10 bis 3.13 (64-bit) fehlt.
echo  Bitte von https://www.python.org/downloads/ installieren
echo  und dabei den Haken bei "Add python.exe to PATH" setzen. Dann install.bat erneut starten.
pause
exit /b 1

:fail
echo.
echo  Installation fehlgeschlagen. Die Meldung oben zeigt, woran es lag.
pause
exit /b 1
