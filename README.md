# AI-Forge: Local Multi-Agent System 🤖🧠

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Tests](https://img.shields.io/badge/tests-92%20passed-brightgreen)
![Agents](https://img.shields.io/badge/agents-17-purple)

**AI-Forge** is a local AI orchestration system built with **LangGraph**. An orchestrator reads each request and hands it to one of 17 specialist agents, so the whole system works as one: it keeps long-term memory, acts on the user's machine and can even write new tools for itself.

It is designed to run on local models through Ollama, with an optional cloud fallback.

---

## ✨ Key Features

- **Agent orchestration:** a main orchestrator evaluates the user's request and routes it to the right specialist (Memory, RAG, File, GitHub, MCP, Marketing and more). Each agent gets only the context it needs, which keeps the LLM focused.
- **Self-programming (SkillForge Agent):** if you ask for something AI-Forge can't do yet, the SkillForge Agent writes the Python tool, validates it with the AST validator, backs up the current tools and saves the new one, with automatic rollback if anything fails.
- **Second brain (Obsidian Agent):** reads your Obsidian vault, analyzes recent notes and generates weekly reports.
- **Model Context Protocol (MCP Agent):** full integration with FastMCP servers running in persistent threads. It creates commits and pull requests straight from the chat and works around Windows Credential Manager lockups.
- **Semantic memory with MemoryGate:** ChromaDB and LlamaIndex give the system long-term memory. MemoryGate classifies every conversation turn before saving it, so the database doesn't fill up with noise.
- **4-layer security sandbox:** all LLM-generated code goes through AST validator → import allowlist → isolated process → resource limits before it runs. 67 of the 92 tests cover the sandbox alone.
- **Local first (100% private):** built to run on local models such as `qwen2.5:14b` through Ollama. A ModelRouter with a circuit breaker can fall back to the cloud if you enable it.
- **WhatsApp daily sync:** reads your latest WhatsApp Web message with Playwright (for example, *"worked out and read 20 pages"*), uses the local model to work out which daily habits you completed, updates the RPG-style habit tracker, writes a daily log to Obsidian and sends a report with the XP earned back to the chat.

---

## 🧭 How Does the Orchestrator Decide?

The orchestrator doesn't use fixed rules. It uses the LLM to understand the user's intent and picks which agent, or chain of agents, to run.

### Flow of a full request

```
User writes a prompt
        ↓
   Orchestrator (LangGraph ReAct — qwen2.5:14b via Ollama)
        ↓ evaluates intent with the full session history
        ├── Code / execution task?        → Code Agent → SandboxManager (4 layers)
        ├── Memory / past context?        → Memory Agent → ChromaDB
        ├── Search in documents / notes?  → RAG Agent → LlamaIndex + Obsidian
        ├── Write to Obsidian?            → Obsidian Agent → local vault
        ├── GitHub / CI/CD operation?     → MCP Agent → FastMCP server (stdio)
        ├── New skill requested?          → SkillForge Agent → dynamic_tools.py
        ├── UI / screen automation?       → Computer Use Agent → llava + PyAutoGUI
        ├── Real-time web search?         → Web Search Agent → DuckDuckGo
        ├── Leads / clients / Upwork?     → Marketing Agent → Playwright scraper
        ├── Google email / calendar?      → Email / Calendar Agent → OAuth2
        ├── PyTorch neural networks?      → Neural Network Agent
        ├── Fitness / training?           → Fitness Agent → persistent JSON
        └── Compound task?                → chain of agents in sequence
        ↓
   MemoryGate evaluates the turn in the background (daemon thread)
        ↓ classifies it with the LLM: FACT / PREFERENCE / DECISION / EVENT / EPHEMERAL
        ↓ if it's worth keeping → saves it to ChromaDB (semantic deduplication)
        ↓
   Consolidated result → WebSocket → dashboard UI
```

### Routing principles

- **Clean context per agent:** no sub-agent sees the whole conversation. Each one gets a specific sub-prompt with its exact task.
- **Structured fallback:** if an agent fails, the orchestrator receives a structured error and can retry, rephrase or report back to the user without hanging.
- **No cycles:** the LangGraph graph is acyclic. Agents never call each other directly; everything goes through the orchestrator.
- **ModelRouter with circuit breaker:** if Ollama fails 3 times in a row, the router can escalate to the cloud automatically (off by default, for privacy).

---

## 🦾 The Agent Ecosystem

The orchestrator has a team of specialists, all inheriting from `AgentBase`:

1. **Memory Agent** — writes and reads semantic memories in ChromaDB, with deduplication.
2. **File Agent** — browses the disk and reads and writes local files.
3. **GitHub Agent** — creates repos and reads remote code, issues and PRs through PyGitHub.
4. **Obsidian Agent** — reads, writes and searches notes in your Markdown vault.
5. **Marketing Agent** — scrapes leads from Upwork and Reddit with Playwright and scores them.
6. **Fitness Agent** — keeps a persistent JSON log of gym PRs, injury history and weekly volume.
7. **Computer Use Agent** — sees the screen with `llava` and automates clicks and typing with PyAutoGUI.
8. **Code Agent** — generates Python and runs it inside the 4-layer sandbox.
9. **RAG Agent** — vector search over local PDFs and files plus the whole Obsidian vault.
10. **Neural Network Agent** — designs, codes and trains PyTorch models with persistent metrics.
11. **MCP Agent** — autonomous CI/CD: commits, pushes and PRs through FastMCP, with Windows workarounds.
12. **SkillForge Agent** — writes and saves new tools with automatic backup and rollback.
13. **Image Agent** — generates images with Stable Diffusion v1.5 (local diffusers).
14. **Voice Agent** — real-time speech transcription with local Whisper.
15. **Calendar / Email Agents** — Gmail and Google Calendar with full OAuth2.
16. **Brain Agent** — analyzes recent Obsidian notes and generates weekly insights.
17. **Web Search Agent** — real-time DuckDuckGo search, with the option to save findings to memory.

---

## ⚙️ Environment Setup

Copy the example file and fill it in for your machine:

```bash
cp .env.example .env   # Linux/macOS
copy .env.example .env # Windows
```

### Main variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `OLLAMA_MODEL` | ✅ Yes | Main inference model | `qwen2.5:14b` |
| `OLLAMA_BASE_URL` | ✅ Yes | URL of the local Ollama server | `http://localhost:11434` |
| `LLM_PROVIDER` | ✅ Yes | LLM engine: `local` or `cloud` | `local` |
| `OBSIDIAN_VAULT_PATH` | ✅ For Obsidian / Brain | Absolute path to your vault | `C:/Users/user/MyVault` |
| `GITHUB_TOKEN` | ✅ For MCP / GitHub | Personal access token | `ghp_xxxxxxxxxxxx` |

### Cloud fallback variables (optional)

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | No | Fall back to Claude when Ollama is not available | `None` |
| `ANTHROPIC_MODEL` | No | Anthropic model used for the fallback | `claude-sonnet-4-20250514` |

### Per-agent variables

| Variable | Agent | Required | Description |
|----------|-------|----------|-------------|
| `GOOGLE_OAUTH_CREDENTIALS` | Calendar / Email | OAuth only | Path to the JSON from Google Cloud Console |
| `GOOGLE_OAUTH_TOKEN` | Calendar / Email | Auto-generated | OAuth session (created on first use) |
| `MEMORY_EMBED_MODEL` | Memory / RAG | No | Embedding model |
| `RAG_TOP_K` | RAG | No | Maximum RAG results |
| `OLLAMA_VISION_MODEL` | Computer Use | No | Vision model (`llava`) |
| `SD_MODEL_ID` | Image | No | Stable Diffusion model |
| `IMAGE_OUTPUT_DIR` | Image | No | Output folder for images |
| `WHISPER_MODEL` | Voice | No | Whisper model size (`base`) |
| `MCP_SERVERS_CONFIG` | MCP | No | Path to the MCP servers JSON (see `mcp_servers.example.json`) |

---

## 🔧 Tools by Agent

Each agent exposes tools to the orchestrator with LangChain's `@tool` decorator. This table lists what each agent can do and its exact parameters, checked against the source code.

### 🧠 Memory Agent (`memory_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `memory_list_all` | Lists every memory indexed in ChromaDB | — |
| `memory_add_reminder` | Creates a persistent reminder | `text: str` |
| `memory_add_progress` | Adds a progress note or log entry | `text: str` |
| `memory_delete_reminder` | Deletes a reminder by short ID | `item_id: str` |
| `memory_delete_progress` | Deletes a progress entry by ID | `item_id: str` |
| `memory_semantic_search` | Semantic search over embeddings | `query: str, n_results: int = 8` |
| `memory_add_embedding` | Saves text with an embedding and a free-form label | `text: str, kind: str = "note"` |
| `memory_get_context` | Retrieves the N most relevant memories (internal RAG) | `query: str, n: int = 6` |

### 📁 File Agent (`file_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `file_read_file` | Reads a text file with a size limit | `path: str, max_bytes: int = 500000` |
| `file_write_file` | Writes or appends content to a file | `path: str, content: str, append: bool = False` |
| `file_list_directory` | Lists the entries of a directory (not recursive) | `path: str, max_entries: int = 200` |
| `file_move_or_copy` | Moves or copies files and directories | `source_path: str, destination_path: str, operation: str` |
| `file_search` | Recursive search by name or content | `root_path: str, name_glob: str, content_substring: str` |

### 💻 Code Agent (`code_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `code_generate_and_execute` | Generates Python code and runs it in the 4-layer sandbox | `description: str` |
| `code_handoff_to_memory_agent` | Hands off to the Memory Agent to save results | `instruction: str` |

### 🛠️ SkillForge Agent (`skillforge_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `skillforge_save_tool` | Validates, backs up and saves a new tool in `dynamic_tools.py` | `python_code: str` |
| `skillforge_list_history` | Lists the version history of `dynamic_tools.py` | — |
| `skillforge_rollback` | Reverts to the last backup after explicit confirmation | `confirm: str` |

### 🤖 MCP Agent (dynamic tools through FastMCP)
| Tool | Description | Parameters |
|------|-------------|------------|
| `aiforge_commit_push` | Commits and pushes to the remote repo (with Windows workarounds) | `message: str, branch: str` |
| `aiforge_create_pr` | Creates a GitHub pull request through the API | `title: str, body: str, head: str, base: str` |
| `aiforge_get_status` | Current status of the Git repo | — |
| `aiforge_get_diff` | Diff of the current changes | — |
| `aiforge_list_branches` | Lists the repo's branches | — |
| `aiforge_merge_pr` | Merges an existing PR | `pr_number: int` |

### 📚 RAG Agent (`rag_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `rag_index_documents` | Indexes PDF, TXT and MD files in `data/documents/` | — |
| `rag_query` | Runs a RAG query over the indexed documents | `question: str` |
| `rag_add_document` | Creates and indexes a new file | `filename: str, content: str` |
| `rag_list_indexed` | Lists the chunks indexed in Chroma | `max_rows: int = 50` |
| `rag_index_obsidian_vault` | Indexes the whole Obsidian vault in Chroma | — |
| `rag_query_obsidian` | Queries the Obsidian knowledge base | `question: str` |

### 📓 Obsidian Agent (`obsidian_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `obsidian_read_note` | Reads a note by title (`.md` optional) | `title: str` |
| `obsidian_write_note` | Creates or overwrites a note | `title: str, content: str` |
| `obsidian_append_note` | Appends text to the end of an existing note | `title: str, content: str` |
| `obsidian_search_notes` | Searches text across every note in the vault | `query: str` |
| `obsidian_get_recent_notes` | Notes modified in the last N days | `days: int = 7` |

### 🌐 Web Search Agent (`web_search_tools.py`)
| Tool | Description | Parameters |
|------|-------------|------------|
| `web_search_duckduckgo` | Real-time internet search | `query: str` |
| `web_search_save_findings_to_memory` | Hands findings off to the Memory Agent | `instruction: str` |

---

## 🌅 Morning Briefing & Telegram Bot

AI-Forge includes an autonomous "second brain" that writes a morning report every time you log in, plus a 24/7 conversational assistant on Telegram.

### 🔄 Morning briefing (runs at startup)

```
Waits until Ollama + ChromaDB are free (60 s max)
      │
      ▼
[Step 0] goal_tracker.py
      │  ← reads Telegram messages from the last 24 h
      │  ← analyzes progress on your goals with local Qwen
      │  ← updates progress_log and status in data/taskforge/tasks.json
      │  ← sends the updated goals to Telegram (if anything changed)
      │
      ▼
MorningBriefingAgent (LangGraph ReAct)
      │
      ├── 📝 Reads your Obsidian daily note
      ├── 🎯 Reads your active goals from TaskForge
      ├── ⏳ Scans pending tasks from the last 3 days
      ├── 🌦️ Checks the weather (OpenWeatherMap)
      ├── 📰 Pulls headlines from Hugging Face, TechCrunch and Papers with Code
      ├── 📅 Reviews Google Calendar events (if configured)
      ├── 📧 Filters critical Gmail messages (if configured)
      └── 🛡️ Checks that Ollama, ChromaDB and MCP are running
      │
      ▼
Writes the briefing in Markdown
      │
      ├──→ 💾 Saves it to Obsidian: Daily Notes/YYYY-MM-DD-briefing.md
      ├──→ 🌐 Serves it at http://localhost:8765
      └──→ 📱 Sends a short summary to Telegram
```

### Does the Telegram bot read all my messages?

> Yes and no. `scripts/telegram_bot_listener.py` runs on your PC and connects to the Telegram API. It receives every message you send directly to the bot, and it does two things with them:
>
> 1. **Explicit commands:** if you type exactly `/daily` or `/briefing`, it generates the briefing right away.
> 2. **Conversation:** anything else goes to the local LangGraph orchestrator, so Qwen answers you and can use its tools on your PC.
>
> Before the morning briefing runs, `goal_tracker.py` also reviews the last 24 hours of chat. It uses local Qwen to spot progress on the previous day's goals (for example, *"studied English for 2 hours"* or *"sent 3 proposals on Upwork"*) and updates your tasks and XP in `tasks.json`.

---

## 📱 WhatsApp Daily Sync

Log your daily habits and tasks by sending a plain WhatsApp message (for example, *"worked out and read 20 pages"*). The local AI maps it to your structured TaskForge habits.

### 🔄 How it runs

1. **Read (Playwright):** opens a persistent browser session (reusing your logged-in Chrome), opens the WhatsApp chat and extracts the latest message.
2. **Understand (local Ollama):** your local model (for example `qwen2.5:14b`) interprets the message and maps it to the system's habits.
3. **Update (TaskForge RPG):** records the completed habits, adds XP and levels up your character when it applies.
4. **Log (Obsidian vault):** saves a structured note with the day's summary.
5. **Report (WhatsApp):** sends a report with the completed habits and your character's current status back to the chat.

### 💻 Commands

- **Dry run (CLI):** test the interpretation and the database update without opening WhatsApp:
  ```bash
  python agents/wsp_daily_sync.py --messages "Worked out and read 20 pages"
  ```

- **Schedule it (Windows Task Scheduler):** installs a scheduled task that syncs automatically every night:
  ```bash
  python scripts/setup_wsp_cron.py --install
  ```

---

## 🛠️ Tech Stack

| Category | Technology |
|----------|-----------|
| ReAct core | Python 3.10+, LangGraph, LangChain |
| Local LLM engine | Ollama (`qwen2.5:14b`, `llava`) |
| Cloud LLM engine | Anthropic Claude (optional fallback) |
| Vector database | ChromaDB (persistent, singleton) |
| RAG engine | LlamaIndex + Hugging Face embeddings |
| Extended protocol | FastMCP (Model Context Protocol) |
| Dashboard UI | FastAPI + WebSockets |
| UI automation | PyAutoGUI + Playwright |
| Code security | SandboxManager (AST + allowlist + ProcessRunner + ResourceGovernor) |
| CI/CD | GitHub Actions + GitHub API |
| Extra persistence | JSON (fitness, leads), ChromaDB (memory, RAG) |

---

## 🚀 Installation

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) installed and running

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/Javier-Alturo/ai-forge.git
cd ai-forge

# 2. Virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Download the local models
ollama pull qwen2.5:14b
ollama pull llava

# 5. Configure the environment
cp .env.example .env
# Edit .env with your paths and tokens
```

---

## 💻 Usage

Start the interactive dashboard:

```bash
python dashboard/app.py
```

Then open `http://localhost:8000` in your browser.

Or use the command line:

```bash
python main.py
python main.py "search for news about Python 3.13"
```

*Example prompts:*
- *"Orchestrator, use the Marketing agent to analyze Upwork profiles and write a proposal."*
- *"SkillForge, write yourself a tool that tells me the weather and save it."*
- *"Orchestrator, use the MCP Agent to commit today's changes and open a pull request to main."*
- *"Write a weekly summary of my training and my Obsidian notes."*
- *"Search my Obsidian vault for everything I wrote about agent architecture."*

---

## 📂 Project Structure

```text
ai-forge/
├── main.py                       # Command-line entry point
├── agents/                       # LangGraph nodes
│   ├── agent_base.py             # Main abstract class (AgentBase)
│   ├── orchestrator.py           # Router + MemoryGate + ModelRouter
│   ├── mcp_agent.py              # Model Context Protocol sub-agent
│   ├── skillforge_agent.py       # Self-programming module
│   ├── dynamic_tools.py          # Tools generated by SkillForge (active)
│   ├── wsp_daily_sync.py         # WhatsApp habit sync engine
│   ├── morning_briefing_agent.py # Daily summary (Obsidian, Calendar, weather, RSS)
│   ├── morning_briefing_tools.py # Data-gathering tools for the briefing
│   └── memory/
│       ├── memory_gate.py        # LLM classifier for memory relevance
│       └── memory_schemas.py     # Types: FACT/PREFERENCE/DECISION/EVENT/EPHEMERAL
├── core/
│   ├── model_router.py           # Local → cloud circuit breaker
│   └── sandbox/
│       ├── sandbox_manager.py    # Single entry point for LLM code
│       ├── ast_validator.py      # LAYER 1: AST analysis
│       ├── import_allowlist.py   # LAYER 2: module allowlist
│       ├── process_runner.py     # LAYER 3: isolated process (locked CWD + clean env)
│       └── resource_governor.py  # LAYER 4: CPU / RAM / time limits
├── dashboard/
│   └── app.py                    # FastAPI + WebSocket dashboard (port 8000)
├── docs/
│   ├── architecture.md           # Map of ports and services
│   └── failure_modes/
│       ├── code_agent.md         # Code Agent failure matrix
│       └── skillforge_agent.md   # Backup / rollback system
├── tests/
│   ├── sandbox/
│   │   └── test_ast_validator.py # 46 security tests (4 groups)
│   └── test_sandbox.py           # 21 integration tests
├── data/
│   ├── documents/                # PDFs / TXT for RAG
│   ├── chromadb/                 # Persistent vector database
│   └── sandbox_workspace/        # Isolated execution workspace (not in git)
├── scripts/
│   ├── goal_tracker.py           # Reads bot messages, tracks goal progress with Qwen, updates tasks.json
│   ├── morning_briefing.py       # Main briefing runner
│   ├── mcp_aiforge_server.py     # Isolated FastMCP server (stdio)
│   ├── morning_briefing_dashboard.py # Briefing web page on port 8765
│   ├── setup_morning_briefing.py # Setup and Task Scheduler registration
│   ├── telegram_bot_listener.py  # Telegram bot (commands and conversation)
│   ├── register_tasks_admin.ps1  # Registers the Windows tasks (needs admin)
│   └── startup_briefing.bat      # Windows startup wrapper
├── knowledge/prs/                # PR summaries written by a GitHub Action
├── agents_config.json            # Central config (timeouts, sandbox, model_router)
├── mcp_servers.example.json      # MCP servers template
└── .env.example                  # Environment variables template
```

---

## 🤝 How to Add a New Agent

The agent architecture makes adding one predictable. Follow these 4 steps:

### Step 1: Create the agent's tools

```python
# agents/my_agent_tools.py
from langchain_core.tools import tool

@tool
def my_main_tool(parameter: str) -> str:
    """
    Clear description of what this tool does.
    The orchestrator's LLM reads this docstring to decide when to call it.
    """
    return f"Result for: {parameter}"

def get_my_agent_tools():
    return [my_main_tool]
```

### Step 2: Create the agent

```python
# agents/my_agent_agent.py
from agents.my_agent_tools import get_my_agent_tools

def get_my_agent():
    from langgraph.prebuilt import create_react_agent
    from agents.llm import get_llm
    return create_react_agent(get_llm(), tools=get_my_agent_tools())
```

### Step 3: Register it in the orchestrator

```python
# agents/orchestrator.py — add inside build_orchestrator_tools()
@tool
def orchestrator_consult_my_agent(task: str) -> str:
    """Delegates to my new specialist agent."""
    from agents.my_agent_agent import get_my_agent
    return _invoke_subagent("my_agent", get_my_agent, task)
```

And add it to `agents_config.json`:
```json
"my_agent": { "enabled": true, "timeout_soft_s": 30, "timeout_hard_s": 90 }
```

### Step 4: Tests and PR

```bash
python -m pytest tests/ -v
git checkout -b feat/my-agent
git add agents/my_agent_tools.py agents/my_agent_agent.py agents/orchestrator.py
git commit -m "feat: add my new agent"
git push origin feat/my-agent
```

### AgentBase rules

| Method | Status | Description |
|--------|--------|-------------|
| `invoke()` | 🔒 Don't touch | Standard entry point with timing and trace_id |
| `_run()` | ✅ Implement | The agent's main logic |
| `name` | ✅ Implement | Abstract property — the agent's identifier |

---

## 🗺️ Roadmap

### ✅ Done
- Main orchestrator with LangGraph ReAct and 17 specialist agents
- Self-programming system (SkillForge) with automatic backup/rollback and AST validation
- Persistent semantic memory with ChromaDB and MemoryGate (LLM classification)
- MCP integration with GitHub CI/CD (Windows workarounds)
- Real-time WebSocket dashboard with agent logs
- SandboxManager with 4 security layers (67 tests: 46 + 21)
- ModelRouter with a circuit breaker for local → cloud fallback
- Technical documentation (`docs/architecture.md`, `docs/failure_modes/`)
- RAG over the whole Obsidian vault
- Daily habit sync and RPG gamification through WhatsApp, with Playwright and local Ollama (Qwen 2.5 14B)
- Morning Briefing Agent with Obsidian, Google Calendar, OpenWeather, Gmail and RSS feeds (plus Telegram)

### 🔄 In progress
- ModelRouter in every AgentBase (today it's only in the orchestrator)
- MemoryGate metrics panel in the dashboard
- End-to-end integration tests for the full orchestrator

### 📋 Planned
- Public REST API for external systems
- Agent admin panel (enable or disable agents without restarting)
- Support for several Obsidian vaults
- Swarm mode: Marketing Agent sub-agents (copywriter, scraper, SEO)
- Move to WSL to fix subprocess lockups on Windows for good
- SkillForge UI: a viewer for dynamically generated tools

---

## 📄 License

Open source under the MIT License.
