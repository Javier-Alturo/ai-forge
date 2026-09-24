"""Módulo de Scraping B2B dinámico usando Playwright y Beautifulsoup."""
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

DATA_DIR = Path("data")
LEADS_DB = DATA_DIR / "marketing_leads_db.json"
SESSION_DIR = DATA_DIR / "browser_sessions"

def _load_db() -> set[str]:
    if not LEADS_DB.exists():
        return set()
    try:
        with open(LEADS_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(d.get("url") for d in data if "url" in d)
    except:
        return set()

def _save_to_db(lead: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = []
    if LEADS_DB.exists():
        try:
            with open(LEADS_DB, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass
    data.append(lead)
    with open(LEADS_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _is_valid_lead(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    # Exclude freelancers offering services
    bad_keywords = [
        "for hire", "my portfolio", "i am a developer", "my service", 
        "looking for work", "hire me", "agency", "seo services"
    ]
    if any(kw in text for kw in bad_keywords):
        return False
    return True

def _anti_bot_delay():
    time.sleep(random.uniform(2.5, 6.5))

def get_browser_context(p, headless: bool = True):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(SESSION_DIR),
        headless=headless,
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        args=["--disable-blink-features=AutomationControlled"]
    )

def scrape_upwork(query: str, headless: bool = True) -> list[dict]:
    """
    Busca trabajos en Upwork usando DuckDuckGo como intermediario para evitar el bloqueo de Cloudflare.
    Estrategia: 'site:upwork.com/jobs <query>' en DuckDuckGo extrae URLs y snippets reales.
    """
    import httpx
    from urllib.parse import quote_plus

    leads = []
    seen = _load_db()

    # Construir queries de busqueda orientadas a Upwork via DuckDuckGo
    search_variants = [
        f'site:upwork.com/jobs "{query}"',
        f'site:upwork.com/jobs n8n automation langraph',
        f'site:upwork.com/jobs "ai agent" OR "automation" python',
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for search_q in search_variants[:2]:
        try:
            encoded = quote_plus(search_q)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            r = httpx.get(url, headers=headers, timeout=20.0)
            r.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")

            # Extraer resultados de busqueda de DDG
            for result in soup.select(".result")[:8]:
                title_elem = result.select_one(".result__title a")
                snippet_elem = result.select_one(".result__snippet")

                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                # Solo incluir links reales de upwork.com/jobs
                if "upwork.com/jobs/" not in href and "upwork.com/nx/jobs" not in href:
                    continue

                if href in seen:
                    continue

                if _is_valid_lead(title, snippet):
                    lead = {
                        "platform": "Upwork",
                        "title": title,
                        "description": snippet,
                        "url": href,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    leads.append(lead)
                    seen.add(href)
                    _save_to_db(lead)

        except Exception as e:
            print(f"[Lead Scraper] Upwork via DuckDuckGo error: {e}")

    return leads

def scrape_linkedin(query: str, headless: bool = True) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    leads = []
    seen = _load_db()
    
    with sync_playwright() as p:
        context = get_browser_context(p, headless=headless)
        page = context.new_page()
        page.set_default_timeout(30_000)  # max 30s por operacion de pagina

        encoded_query = query.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}&f_TPR=r86400&sortBy=DD"

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            
            if not headless:
                # Da tiempo al usuario (hasta 2 minutos) para resolver captchas y que carguen los resultados
                try:
                    page.wait_for_selector('div.job-search-card, li.jobs-search-results__list-item', timeout=120000)
                except Exception:
                    pass
                    
            _anti_bot_delay()
            page.mouse.wheel(0, 2000)
            _anti_bot_delay()
            
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            job_cards = soup.select('div.job-search-card, li.jobs-search-results__list-item')
            for card in job_cards[:8]:
                title_elem = card.select_one('h3.base-search-card__title, a.job-card-list__title')
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                
                link_elem = card.select_one('a.base-card__full-link, a.job-card-list__title')
                if not link_elem:
                    continue
                href = link_elem.get('href', '').split('?')[0] # Clean URL
                
                if href in seen:
                    continue
                
                desc = "Descripción rápida no disponible. Entrar al link para leer más."
                if _is_valid_lead(title, desc):
                    lead = {
                        "platform": "LinkedIn",
                        "title": title,
                        "description": desc,
                        "url": href,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    leads.append(lead)
                    seen.add(href)
                    _save_to_db(lead)
        except Exception as e:
            print(f"[Lead Scraper] LinkedIn error: {e}")
        finally:
            context.close()
            
    return leads

# Subreddits donde la gente publica trabajos de automatizacion e IA
_REDDIT_SUBREDDITS = [
    "forhire",
    "slavelabour",
    "jobbit",
    "entrepreneur",
    "smallbusiness",
]

# Palabras clave para filtrar posts relevantes en esos subreddits
_REDDIT_KEYWORDS = [
    "n8n", "langgraph", "langchain", "automation", "automate",
    "ai agent", "workflow", "zapier alternative", "make.com",
    "python automation", "api integration", "chatbot", "whatsapp bot"
]

def _reddit_post_is_relevant(title: str, desc: str) -> bool:
    """Filtra posts de Reddit que mencionen automatizacion o IA."""
    text = f"{title} {desc}".lower()
    return any(kw in text for kw in _REDDIT_KEYWORDS)

def scrape_reddit(query: str) -> list[dict]:
    """Busca en multiples subreddits usando la API JSON de Reddit + filtrado por keyword."""
    leads = []
    seen = _load_db()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AI-Forge-Lead-Finder/2.0)"}
    
    # 1. Buscar en subreddits por keyword usando la API de busqueda de Reddit
    search_queries = [query] + ["n8n automation", "LangGraph agent", "ai automation freelance"]
    
    for q in search_queries[:2]:  # Limitamos a 2 queries para no sobrecargar
        try:
            encoded = q.replace(" ", "+")
            search_url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit=15&t=week"
            r = httpx.get(search_url, headers=headers, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            
            for child in data.get("data", {}).get("children", []):
                post = child["data"]
                title = post.get("title", "")
                desc = post.get("selftext", "")
                subreddit = post.get("subreddit", "")
                href = f"https://www.reddit.com{post.get('permalink', '')}"
                
                if href in seen:
                    continue
                
                # Aceptar posts de contratacion o discusiones relevantes
                is_hiring = "[hiring]" in title.lower() or "[h]" in title.lower()
                is_relevant = _reddit_post_is_relevant(title, desc)
                
                if (is_hiring or is_relevant) and _is_valid_lead(title, desc):
                    lead = {
                        "platform": f"Reddit r/{subreddit}",
                        "title": title,
                        "description": desc[:600] if desc else f"Post sobre: {title}",
                        "url": href,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    leads.append(lead)
                    seen.add(href)
                    _save_to_db(lead)
        except Exception as e:
            print(f"[Lead Scraper] Reddit search error for '{q}': {e}")
    
    # 2. Tambien revisar r/forhire con [Hiring] recientes
    try:
        url = "https://www.reddit.com/r/forhire/new.json?limit=25"
        r = httpx.get(url, headers=headers, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        
        for child in data.get("data", {}).get("children", []):
            post = child["data"]
            title = post.get("title", "")
            desc = post.get("selftext", "")
            href = f"https://www.reddit.com{post.get('permalink', '')}"
            
            if href in seen:
                continue
                
            if "[hiring]" in title.lower() and _is_valid_lead(title, desc):
                lead = {
                    "platform": "Reddit r/forhire",
                    "title": title,
                    "description": desc[:600],
                    "url": href,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                leads.append(lead)
                seen.add(href)
                _save_to_db(lead)
    except Exception as e:
        print(f"[Lead Scraper] Reddit r/forhire error: {e}")
        
    return leads

def scrape_all(query: str, platforms: list[str], headless: bool = True) -> list[dict]:
    all_leads = []
    plats = [p.lower() for p in platforms]
    
    if "upwork" in plats:
        all_leads.extend(scrape_upwork(query, headless))
    if "linkedin" in plats:
        all_leads.extend(scrape_linkedin(query, headless))
    if "reddit" in plats:
        all_leads.extend(scrape_reddit(query))
    
    # Dedup por URL por si alguna ronda duplicó
    seen_urls = set()
    unique = []
    for lead in all_leads:
        if lead["url"] not in seen_urls:
            seen_urls.add(lead["url"])
            unique.append(lead)
        
    return unique
