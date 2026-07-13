@echo off
REM Startet edelrep im LAN-Modus. Logs landen in edelrep.log.
cd /d "D:\edelrep-master"

REM uv verlinkt Pakete standardmaessig per Hardlink aus seinem Cache in die .venv.
REM Liegt der Cache auf einem anderen Laufwerk als dieses Projekt (z.B. Cache auf
REM C:, Projekt auf D:), scheitert das unter Windows ("linking across drives").
REM copy umgeht das (etwas mehr Speicher, aber robust).
set UV_LINK_MODE=copy

if not exist bilder mkdir bilder
echo [%date% %time%] starting edelrep >> edelrep.log

REM Start ueber den Interpreter statt ueber den edelrep.exe-Shim: manche Windows-
REM Anwendungssteuerungsrichtlinien (Smart App Control / WDAC) blockieren den
REM unsignierten Shim-Launcher (os error 4551). "python -m" umgeht ihn.
uv run python -m edelrep.cli.main serve --storage-root .\bilder --index-path index.db --host 0.0.0.0 --port 8080 1>>edelrep.log 2>&1
