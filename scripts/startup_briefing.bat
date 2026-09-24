@echo off
:: Despacha el Morning Briefing y levanta el Dashboard
cd /d "%~dp0.."

echo [AI-Forge] Iniciando Dashboard en http://localhost:8765...
start /b py scripts/morning_briefing_dashboard.py

echo [AI-Forge] Iniciando pipeline de Morning Briefing...
py scripts/morning_briefing.py

exit
