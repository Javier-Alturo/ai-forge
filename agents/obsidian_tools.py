import os
from pathlib import Path
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

# El usuario debe configurar OBSIDIAN_VAULT_PATH en su archivo .env
VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "")

def get_vault_path() -> Path:
    if not VAULT_PATH:
        raise ValueError("OBSIDIAN_VAULT_PATH no está configurado en el archivo .env. Por favor añádelo.")
    p = Path(VAULT_PATH)
    if not p.exists() or not p.is_dir():
        raise ValueError(f"La ruta del vault de Obsidian no es válida o no existe: {VAULT_PATH}")
    return p

def _resolve_note_path(title: str) -> Path:
    if not title.endswith(".md"):
        title += ".md"
    return get_vault_path() / title

@tool
def obsidian_read_note(title: str) -> str:
    """Lee el contenido de una nota de Obsidian por su título (ej: 'Ideas' o 'Ideas.md')."""
    try:
        path = _resolve_note_path(title)
        if not path.exists():
            return f"Error: La nota '{title}' no existe en {path.parent}."
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error al leer la nota: {str(e)}"

@tool
def obsidian_write_note(title: str, content: str) -> str:
    """Crea una nueva nota en Obsidian o sobrescribe una existente con el nuevo contenido."""
    try:
        path = _resolve_note_path(title)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Nota '{title}' guardada exitosamente en el vault."
    except Exception as e:
        return f"Error al escribir la nota: {str(e)}"

@tool
def obsidian_append_note(title: str, content: str) -> str:
    """Añade texto al final de una nota existente en Obsidian sin sobrescribir lo anterior."""
    try:
        path = _resolve_note_path(title)
        if not path.exists():
            return f"Error: La nota '{title}' no existe. Usa obsidian_write_note primero para crearla."
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{content}")
        return f"Contenido añadido a '{title}' exitosamente."
    except Exception as e:
        return f"Error al modificar la nota: {str(e)}"

@tool
def obsidian_search_notes(query: str) -> str:
    """Busca un texto dentro de todas las notas (.md) del vault de Obsidian y devuelve fragmentos."""
    try:
        vault = get_vault_path()
        results = []
        for filepath in vault.rglob("*.md"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if query.lower() in content.lower():
                        idx = content.lower().find(query.lower())
                        start = max(0, idx - 40)
                        end = min(len(content), idx + len(query) + 40)
                        snippet = content[start:end].replace("\n", " ")
                        results.append(f"- {filepath.name}: ...{snippet}...")
            except Exception:
                pass 
                
        if not results:
            return f"No se encontró '{query}' en ninguna nota del vault."
        
        # Limitar a 20 resultados para no exceder el contexto
        return f"Coincidencias encontradas ({len(results)} en total):\n" + "\n".join(results[:20])
    except Exception as e:
        return f"Error en la búsqueda: {str(e)}"

@tool
def obsidian_get_recent_notes(days: int = 7) -> str:
    """Busca y lee las notas de Obsidian que han sido modificadas en los últimos N días."""
    try:
        import time
        vault = get_vault_path()
        current_time = time.time()
        max_age_seconds = days * 24 * 3600
        
        recent_notes = []
        for filepath in vault.rglob("*.md"):
            try:
                mtime = os.path.getmtime(filepath)
                if current_time - mtime <= max_age_seconds:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Si es muy larga la truncamos a 500 caracteres
                        if len(content) > 500:
                            content = content[:500] + "... (truncado)"
                        recent_notes.append(f"--- Nota: {filepath.name} ---\n{content}\n")
            except Exception:
                pass
                
        if not recent_notes:
            return f"No se encontraron notas modificadas en los últimos {days} días."
            
        # Limitar para no explotar el contexto
        if len(recent_notes) > 15:
            recent_notes = recent_notes[:15]
            recent_notes.append("\n... (limitado a las 15 más recientes)")
            
        return f"Notas recientes (últimos {days} días):\n\n" + "\n".join(recent_notes)
    except Exception as e:
        return f"Error al buscar notas recientes: {str(e)}"

def get_obsidian_tools():
    return [
        obsidian_read_note,
        obsidian_write_note,
        obsidian_append_note,
        obsidian_search_notes,
        obsidian_get_recent_notes
    ]
