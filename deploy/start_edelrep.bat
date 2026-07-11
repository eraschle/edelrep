@echo off
REM Startet edelrep im LAN-Modus mit Auto-Update bei jedem (Neu-)Start.
REM Bei einem regulären Exit (z.B. via "Jetzt aktualisieren"-Button)
REM loöscht der Loop unten den letzten Stand, holt sich Updates und
REM startet die App wieder.

cd /d "D:\edelrep-master"
if not exist bilder mkdir bilder

:loop
echo [%date% %time%] starting edelrep >> edelrep.log
git pull --ff-only 1>>edelrep.log 2>&1
uv sync --quiet 1>>edelrep.log 2>&1
uv run edelrep serve --storage-root .\bilder --index-path index.db --host 0.0.0.0 --port 8080 1>>edelrep.log 2>&1
echo [%date% %time%] edelrep exited with code %ERRORLEVEL%, restarting in 3s >> edelrep.log
timeout /t 3 /nobreak >nul
goto loop
