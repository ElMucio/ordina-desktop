@echo off
rem Crea "Ordina Desktop.lnk" in questa cartella, con l'icona dell'app.
rem Il collegamento contiene i percorsi di questo PC, per questo non e' nel repository.
setlocal
cd /d "%~dp0"

set "PYW="
for /f "delims=" %%P in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%P"
if not defined PYW (
  echo pythonw.exe non trovato. Installa Python 3 da https://www.python.org/downloads/
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%~dp0Ordina Desktop.lnk');" ^
  "$s.TargetPath = '%PYW%';" ^
  "$s.Arguments = '\"%~dp0ordina_desktop.pyw\"';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%~dp0assets\app.ico';" ^
  "$s.Description = 'Salva e ripristina la posizione delle icone del desktop';" ^
  "$s.Save()"
if errorlevel 1 (
  echo Creazione del collegamento non riuscita.
  pause
  exit /b 1
)
echo Fatto: "Ordina Desktop.lnk" creato in questa cartella.
pause
