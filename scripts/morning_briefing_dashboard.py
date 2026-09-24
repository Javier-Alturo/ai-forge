"""Morning Briefing Dashboard — Servidor web local (localhost:8765) que renderiza el briefing diario de forma interactiva y visual."""

from __future__ import annotations

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import date, datetime
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from agents.obsidian_tools import get_vault_path
from scripts.morning_briefing import run_briefing_flow

app = FastAPI(title="AI-Forge Morning Briefing Dashboard")

# ══════════════════════════════════════════════════════════════════════════════
# DATA PARSERS & HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_briefing_content() -> str:
    """Lee el briefing de hoy en Obsidian."""
    today = date.today().isoformat()
    try:
        vault = get_vault_path()
        path = vault / "Daily Notes" / f"{today}-briefing.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""

def read_daily_tasks() -> List[Dict[str, Any]]:
    """Lee las tareas (pendientes y completadas) de la Daily Note de hoy en Obsidian."""
    today = date.today().isoformat()
    tasks = []
    try:
        vault = get_vault_path()
        path = vault / "Daily Notes" / f"{today}.md"
        if not path.exists():
            return []
        
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("- [ ]") or line_str.startswith("- [x]"):
                completed = line_str.startswith("- [x]")
                text = line_str[5:].strip()
                if text:
                    tasks.append({
                        "text": text,
                        "completed": completed,
                        "raw_line": line
                    })
    except Exception:
        pass
    return tasks

def write_daily_tasks(tasks: List[Dict[str, Any]]) -> bool:
    """Escribe de vuelta el bloque de tareas en la Daily Note de hoy."""
    today = date.today().isoformat()
    try:
        vault = get_vault_path()
        path = vault / "Daily Notes" / f"{today}.md"
        if not path.exists():
            return False
            
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        task_idx = 0
        
        for line in lines:
            if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]"):
                if task_idx < len(tasks):
                    t = tasks[task_idx]
                    prefix = "- [x]" if t["completed"] else "- [ ]"
                    # Preservar indentación original
                    indent = line[:line.find("-")]
                    new_lines.append(f"{indent}{prefix} {t['text']}")
                    task_idx += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

class TaskToggleIn(BaseModel):
    task_text: str
    completed: bool

@app.get("/api/briefing")
async def get_briefing():
    """Retorna el contenido crudo del briefing de hoy en markdown y las tareas estructuradas."""
    briefing = get_briefing_content()
    tasks = read_daily_tasks()
    return {
        "date": date.today().isoformat(),
        "has_briefing": bool(briefing),
        "markdown": briefing,
        "tasks": tasks
    }

@app.post("/api/generate")
async def generate_briefing():
    """Genera (o regenera) el briefing diario en segundo plano."""
    try:
        # Ejecuta el script de orquestación principal
        briefing = await asyncio.to_thread(run_briefing_flow)
        tasks = read_daily_tasks()
        return {"status": "ok", "markdown": briefing, "tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/toggle")
async def toggle_task(body: TaskToggleIn):
    """Marca o desmarca una tarea en el archivo .md de Obsidian de hoy."""
    tasks = read_daily_tasks()
    found = False
    for t in tasks:
        if t["text"].strip() == body.task_text.strip():
            t["completed"] = body.completed
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
    success = write_daily_tasks(tasks)
    if not success:
        raise HTTPException(status_code=500, detail="Error al actualizar el archivo Markdown")
        
    return {"status": "ok", "tasks": tasks}

# ══════════════════════════════════════════════════════════════════════════════
# HTML INTERACTION PANEL (SINGLE FILE ARCHITECTURE)
# ══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-Forge — Morning Briefing</title>
    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Marked.js para renderizar Markdown -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                        outfit: ['Outfit', 'sans-serif'],
                    }
                }
            }
        }
    </script>
    <style>
        body {
            background-color: #080c14;
            background-image: 
                radial-gradient(at 10% 20%, rgba(99, 102, 241, 0.05) 0px, transparent 50%),
                radial-gradient(at 90% 80%, rgba(20, 184, 166, 0.05) 0px, transparent 50%);
            font-family: 'Inter', sans-serif;
        }
        .glass-panel {
            background: rgba(13, 20, 35, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.03);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }
        .glass-card {
            background: rgba(255, 255, 255, 0.01);
            border: 1px solid rgba(255, 255, 255, 0.04);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-card:hover {
            border-color: rgba(99, 102, 241, 0.3);
            background: rgba(255, 255, 255, 0.02);
            box-shadow: 0 0 20px rgba(99, 102, 241, 0.1);
            transform: translateY(-2px);
        }
        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.01);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        /* Markdown override styling */
        .prose h1, .prose h2, .prose h3 {
            font-family: 'Outfit', sans-serif;
            color: #f3f4f6;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
            font-weight: 600;
        }
        .prose h1 { font-size: 1.75rem; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 0.5rem; }
        .prose h2 { font-size: 1.4rem; color: #e5e7eb; }
        .prose h3 { font-size: 1.15rem; color: #a5b4fc; }
        .prose p { color: #9ca3af; margin-bottom: 1rem; line-height: 1.625; }
        .prose ul { list-style-type: none; padding-left: 0; }
        .prose li { margin-bottom: 0.5rem; color: #d1d5db; position: relative; padding-left: 1.25rem; }
        .prose li::before {
            content: "•";
            color: #6366f1;
            position: absolute;
            left: 0;
            font-weight: bold;
        }
        .prose blockquote {
            border-left: 4px solid #6366f1;
            padding-left: 1rem;
            margin: 1.5rem 0;
            color: #d1d5db;
            font-style: italic;
            background: rgba(99, 102, 241, 0.03);
            padding: 0.75rem 1rem;
            border-radius: 0 8px 8px 0;
        }
        .prose strong { color: #f3f4f6; }
    </style>
</head>
<body class="text-slate-100 min-h-screen flex flex-col antialiased">

    <!-- Header -->
    <header class="w-full glass-panel border-b border-indigo-950/40 px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div class="flex items-center gap-3">
            <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-teal-400 flex items-center justify-center font-outfit font-bold text-xl shadow-lg shadow-indigo-500/20">
                ⚡
            </div>
            <div>
                <h1 class="font-outfit font-bold text-lg tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-slate-50 to-indigo-200">
                    AI-Forge Morning Briefing
                </h1>
                <p class="text-xs text-slate-400 font-medium">SISTEMA ORQUESTADO DE INTELIGENCIA LOCAL</p>
            </div>
        </div>
        
        <div class="flex items-center gap-6">
            <div id="date-display" class="text-sm font-outfit text-indigo-300 font-semibold tracking-wide">
                Cargando fecha...
            </div>
            <button onclick="generateBriefing()" id="btn-refresh" class="flex items-center gap-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-slate-50 font-outfit font-semibold px-4 py-2 rounded-lg text-sm shadow-lg shadow-indigo-600/20 transition-all active:scale-95 disabled:opacity-50">
                <svg id="refresh-icon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3 3L22 4"></path>
                </svg>
                <span id="btn-text">Regenerar Briefing</span>
            </button>
        </div>
    </header>

    <!-- Main Content Grid -->
    <main class="flex-grow max-w-[1600px] w-full mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        <!-- Left Side: Interactive Checklist & Daily Stats -->
        <section class="lg:col-span-4 flex flex-col gap-6">
            
            <!-- Tasks Checklist Card -->
            <div class="glass-panel p-6 rounded-2xl flex-grow flex flex-col min-h-[400px]">
                <h2 class="font-outfit font-bold text-lg text-slate-50 mb-4 flex items-center gap-2">
                    <span class="text-indigo-400">📝</span> Tareas del Día (Interactive)
                </h2>
                <div id="tasks-container" class="space-y-3 overflow-y-auto flex-grow max-h-[550px] pr-2">
                    <!-- Tasks will be rendered here dynamically -->
                </div>
            </div>

            <!-- Bogota Weather Widget -->
            <div id="weather-widget" class="glass-panel p-6 rounded-2xl glass-card">
                <h2 class="font-outfit font-bold text-lg text-slate-50 mb-3 flex items-center gap-2">
                    <span class="text-teal-400">🌦️</span> Clima en Bogotá
                </h2>
                <div id="weather-content" class="text-slate-300 text-sm space-y-2">
                    Cargando información del clima...
                </div>
            </div>
            
        </section>

        <!-- Right Side: AI Synthesis & Deep Briefing Markdown -->
        <section class="lg:col-span-8 flex flex-col">
            <div class="glass-panel p-8 rounded-2xl flex-grow flex flex-col overflow-hidden">
                <div class="flex items-center justify-between border-b border-slate-800 pb-4 mb-6">
                    <h2 class="font-outfit font-bold text-xl text-indigo-200 tracking-wide flex items-center gap-2">
                        <span>🌅</span> Resumen Ejecutivo del Agente
                    </h2>
                    <span class="text-xs bg-slate-800/80 text-indigo-300 px-3 py-1 rounded-full border border-indigo-500/20 font-mono">
                        briefing_agent_v1.0
                    </span>
                </div>
                
                <!-- Loading State / Markdown Container -->
                <div id="briefing-container" class="prose max-w-none flex-grow overflow-y-auto pr-4 max-h-[700px]">
                    <!-- Briefing markdown will be parsed and injected here -->
                    <div class="flex flex-col items-center justify-center h-64 text-slate-400">
                        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500 mb-4"></div>
                        <p class="font-outfit text-sm">Cargando el briefing del día...</p>
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="w-full text-center py-4 text-xs text-slate-600 border-t border-slate-900 glass-panel">
        AI-Forge Hub-and-Spoke System · Ryzen 7 9800X3D · RTX 5070 Ti · Bogotá, Colombia
    </footer>

    <script>
        let currentTasks = [];

        async function fetchBriefing() {
            try {
                const r = await fetch('/api/briefing');
                const data = await r.json();
                
                // Set Date
                document.getElementById('date-display').innerText = `📅 ${data.date}`;
                
                // Render Tasks
                currentTasks = data.tasks;
                renderTasks();
                
                // Render Markdown Briefing
                const container = document.getElementById('briefing-container');
                if (data.has_briefing) {
                    container.innerHTML = marked.parse(data.markdown);
                    
                    // Parse weather and extract to widget as well
                    extractWeatherToWidget(data.markdown);
                } else {
                    container.innerHTML = `
                        <div class="flex flex-col items-center justify-center h-64 text-slate-400 text-center">
                            <span class="text-4xl mb-4">🔮</span>
                            <h3 class="text-lg font-outfit text-slate-100 font-semibold mb-2">No se encontró Briefing hoy</h3>
                            <p class="text-sm max-w-md mx-auto mb-6">El Morning Briefing aún no ha sido generado para el día de hoy. Haz clic en el botón superior para compilarlo.</p>
                            <button onclick="generateBriefing()" class="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded-lg text-sm font-outfit font-semibold transition-all">
                                Compilar Briefing Ahora
                            </button>
                        </div>
                    `;
                }
            } catch (err) {
                console.error("Error fetching briefing:", err);
                document.getElementById('briefing-container').innerHTML = `<p class="text-red-400">Error al cargar datos: ${err.message}</p>`;
            }
        }

        function renderTasks() {
            const container = document.getElementById('tasks-container');
            if (currentTasks.length === 0) {
                container.innerHTML = '<p class="text-xs text-slate-500 italic">No hay tareas registradas en la nota diaria de hoy.</p>';
                return;
            }

            container.innerHTML = currentTasks.map((t, idx) => `
                <div class="glass-card flex items-start gap-3 p-3.5 rounded-xl transition-all ${t.completed ? 'opacity-50' : ''}">
                    <input type="checkbox" ${t.completed ? 'checked' : ''} 
                        onclick="toggleTask('${t.text.replace(/'/g, "\\'")}', this.checked)"
                        class="w-5 h-5 mt-0.5 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-900 cursor-pointer">
                    <span class="text-sm ${t.completed ? 'line-through text-slate-400' : 'text-slate-200'} font-medium">
                        ${t.text}
                    </span>
                </div>
            `).join('');
        }

        async function toggleTask(taskText, completed) {
            try {
                const r = await fetch('/api/tasks/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_text: taskText, completed: completed })
                });
                const data = await r.json();
                currentTasks = data.tasks;
                renderTasks();
            } catch (err) {
                alert("Error al actualizar la tarea: " + err.message);
            }
        }

        async function generateBriefing() {
            const btn = document.getElementById('btn-refresh');
            const icon = document.getElementById('refresh-icon');
            const text = document.getElementById('btn-text');
            
            btn.disabled = true;
            icon.classList.add('animate-spin');
            text.innerText = "Compilando con AI...";
            
            document.getElementById('briefing-container').innerHTML = `
                <div class="flex flex-col items-center justify-center h-64 text-indigo-400 text-center">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500 mb-4"></div>
                    <h3 class="text-lg font-outfit font-semibold mb-1 text-slate-200">AI-Forge compilando tu mañana</h3>
                    <p class="text-xs text-slate-500 max-w-sm">El agente de Morning Briefing está ejecutando herramientas del sistema, consultando Google APIs, leyendo Obsidian Vault y priorizando tus tareas.</p>
                </div>
            `;
            
            try {
                const r = await fetch('/api/generate', { method: 'POST' });
                const data = await r.json();
                
                const container = document.getElementById('briefing-container');
                container.innerHTML = marked.parse(data.markdown);
                currentTasks = data.tasks;
                renderTasks();
                extractWeatherToWidget(data.markdown);
            } catch (err) {
                document.getElementById('briefing-container').innerHTML = `<p class="text-red-400 p-4 rounded bg-red-950/20 border border-red-800">Error durante la generación: ${err.message}</p>`;
            } finally {
                btn.disabled = false;
                icon.classList.remove('animate-spin');
                text.innerText = "Regenerar Briefing";
            }
        }

        function extractWeatherToWidget(markdown) {
            // Intenta extraer el texto de clima de la sección del clima en el markdown
            const weatherHeaderIdx = markdown.indexOf('### 🌦️ Clima y Consejos');
            const weatherContent = document.getElementById('weather-content');
            
            if (weatherHeaderIdx !== -1) {
                let nextHeaderIdx = markdown.indexOf('###', weatherHeaderIdx + 10);
                if (nextHeaderIdx === -1) nextHeaderIdx = markdown.length;
                
                const rawWeatherText = markdown.substring(weatherHeaderIdx + 23, nextHeaderIdx).trim();
                weatherContent.innerHTML = marked.parse(rawWeatherText);
            } else {
                weatherContent.innerHTML = '<p class="text-xs text-slate-400">Ver detalles en el reporte general del Briefing.</p>';
            }
        }

        // Init page loading
        fetchBriefing();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return HTML_TEMPLATE

def main():
    print("🚀 Levantando Dashboard del Morning Briefing en http://localhost:8765...")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

if __name__ == "__main__":
    main()
