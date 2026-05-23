@echo off
REM Startet edelrep im LAN-Modus. Logs landen in edelrep.log.
cd /d "D:\edelrep - master"
if not exist bilder mkdir bilder
echo [%date% %time%] starting edelrep >> edelrep.log
uv run edelrep serve --storage-root .\bilder --index-path index.db --host 0.0.0.0 --port 8080 1>>edelrep.log 2>&1
