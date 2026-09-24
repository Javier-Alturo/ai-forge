import os
import re
import json
import requests
from datetime import datetime
from pathlib import Path

def get_pr_diff(pr_number: str, token: str) -> str:
    url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.text
    return ""

def call_llm(prompt: str, api_key: str) -> str:
    # Soporta Groq o OpenAI (por defecto usa Groq por ser gratis y rápido si se configura)
    # Se espera que el secreto LLM_API_KEY contenga la key
    if not api_key:
        return "No se ha configurado LLM_API_KEY en GitHub Secrets. No se pudo generar el resumen inteligente."
        
    base_url = "https://api.groq.com/openai/v1/chat/completions"
    model = "llama-3.3-70b-versatile"
    
    if api_key.startswith("sk-") and len(api_key) > 40:
        base_url = "https://api.openai.com/v1/chat/completions"
        model = "gpt-4o-mini"
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Eres un Tech Lead experto. Resume el PR para un archivo de Obsidian. Usa formato Markdown. Secciones obligatorias: 1. Resumen Técnico (qué hace y por qué). 2. Decisiones Arquitectónicas. 3. Deuda Técnica o TODOs detectados. 4. Agentes Afectados."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    resp = requests.post(base_url, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    else:
        return f"Error llamando al LLM: {resp.status_code} - {resp.text}"

def sanitize_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip()

def main():
    token = os.environ.get("GITHUB_TOKEN")
    pr_number = os.environ.get("PR_NUMBER", "0")
    pr_title = os.environ.get("PR_TITLE", "Untitled PR")
    pr_body = os.environ.get("PR_BODY", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    
    print(f"Generando documento para PR #{pr_number}: {pr_title}")
    
    diff = get_pr_diff(pr_number, token)
    
    # Acortar diff si es muy largo
    if len(diff) > 20000:
        diff = diff[:20000] + "\n... (diff truncado)"
        
    prompt = f"Título del PR: {pr_title}\n\nDescripción:\n{pr_body}\n\nDiff de cambios:\n{diff}"
    
    llm_summary = call_llm(prompt, api_key)
    
    # Crear estructura de carpetas
    now = datetime.now()
    folder_name = now.strftime("%Y-%m")
    base_dir = Path("knowledge/prs") / folder_name
    base_dir.mkdir(parents=True, exist_ok=True)
    
    clean_title = sanitize_filename(pr_title)
    file_name = f"PR-{pr_number}-{clean_title}.md"
    file_path = base_dir / file_name
    
    # Tags y metadata para Obsidian (YAML Frontmatter)
    frontmatter = f"""---
type: pull_request
id: {pr_number}
date: {now.strftime("%Y-%m-%d")}
title: "{clean_title}"
---

# PR #{pr_number}: {pr_title}

"""
    
    content = frontmatter + llm_summary
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Archivo guardado en {file_path}")

if __name__ == "__main__":
    main()
