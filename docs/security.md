# Security model

AI-Forge is local-first: the LLM (Ollama), the vector store (ChromaDB) and the dashboard run on
the user's machine. This page lists every path by which data can leave the machine, and how each
one is controlled.

## Egress map

| # | Egress point | What leaves | Control |
|---|---|---|---|
| 1 | Cloud LLM (Anthropic) via `LLM_PROVIDER=cloud` or ModelRouter fallback | Full prompts, including retrieved memory/RAG context | Off by default. Requires `AIFORGE_ALLOW_CLOUD=1` in the environment (`core/cloud_policy.py`); the ModelRouter also needs `allow_cloud_fallback: true`. Checked again when the client is built. |
| 2 | GitHub (MCP repo tools, PyGithub agent) | Commits, PR titles/bodies, merges | Push and merge need human approval via `scripts/approve_git_action.py` (`core/git_guard.py`). Pushes to the public mirror are refused. Explicit file lists only. Token sent as an HTTP header, never in URLs or logs. |
| 3 | Telegram Bot API | Briefings and agent replies; incoming messages reach the orchestrator | Only allow-listed chat ids (`TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_CHAT_IDS`) are processed (`core/telegram_auth.py`). The bot refuses to start without one. |
| 4 | WhatsApp Web (Playwright) | Messages to configured contacts | Runs a local browser session stored under `data/whatsapp_session*/` (git-ignored). Recipients come from local config, not from LLM output. |
| 5 | Gmail / Google Calendar API | Email search queries, calendar events | Gmail is read-only (`gmail.readonly`); no send tool exists. Old tokens with send/modify scopes are refused and trigger re-consent. Token in `token.json` (git-ignored). |
| 6 | Web search (DuckDuckGo) and lead scraper (DuckDuckGo, Reddit, LinkedIn) | Search queries written by the LLM | Queries may contain user text; avoid personal data in search prompts. No credentials sent. |
| 7 | Weather and RSS feeds | City name; plain GET requests | No personal data. |
| 8 | SkillForge-generated tools | Whatever the generated code requests | AST validation + import allowlist + sandboxed process (`core/sandbox/`). `requests`/`httpx` are allowed, so generated tools can reach the network. |
| 9 | ChromaDB telemetry | Anonymous usage events | Disabled (`agents/chroma_client.py`). |
| 9b | LangFuse traces | Prompts, answers, tool calls | Self-hosted on 127.0.0.1 (`observability/`); the tracer refuses non-local hosts; LangFuse product telemetry disabled. |
| 10 | Hugging Face Hub | Model downloads (no user data) | Set `HF_HUB_OFFLINE=1` once models are cached. |
| 11 | GitHub Actions | Nothing: CI runs Ruff, tests and evals with fake or local models only | The PR workflows that sent diffs to OpenAI / Groq were removed. |

The dashboard binds to `127.0.0.1` only.

## Local actions (what an agent can do on this machine)

| Capability | Default | Control |
|---|---|---|
| Generated Python (code / neural-network agents) | Sandboxed | AST deny-list + import allowlist + isolated process + **runtime audit hook** (`core/sandbox/runtime_guard.py`): writes only in the sandbox workspace, reads only workspace + Python install, no process creation, network to localhost only. |
| File agent | `data/agent_workspace` only | `core/fs_policy.py`: paths must be under `AIFORGE_FILE_ROOTS`; `.env`, tokens, keys, `.git`, `.ssh` and session folders are always denied. |
| Obsidian agent | Vault only | Note paths cannot escape the vault (`..` refused). |
| Computer use | Look-only | Click / type / open apps need `AIFORGE_ALLOW_COMPUTER_USE=1`; apps limited to `AIFORGE_ALLOWED_APPS` names. |
| Gmail | Read-only | No send tool, no send/modify scopes. |
| Git push / PR merge | Human approval | `core/git_guard.py`; public mirror blocked. |

Residual risk: with computer use enabled, an agent can still type into any window. Enable it only
while supervising.

## Prompt injection (what the agent reads)

Emails, web pages, notes, files, issues and calendar entries reach the model as tool results, and
the model cannot tell their text from the user's instructions. Two layers run in code, outside the
model, so they do not depend on the model obeying a prompt:

| Layer | What it does | Setting |
|---|---|---|
| Taint policy (`core/tool_policy.py`) | Once a turn has read external content, calls to tools that change something or send data (memory, notes, files, calendar, git, tasks, code, web search...) are replaced by a no-op that tells the model to finish the user's task and report what was blocked. Calls decided before the read are not affected. | `AIFORGE_TAINT_POLICY`: `turn` (default), `thread`, `off` |
| Quarantined reader (`core/external_content.py`) | Before the orchestrator model reads an external result, a separate model call with no tools extracts only the data that answers the request. The stored conversation keeps the original. | `AIFORGE_EXTERNAL_CONTENT`: `reader` (default), `wrap`, `off` |

Measured with `evals/suites/injection.py` (`qwen2.5:14b`, 18 fictional scenarios x 5 templates, one run each):

| Attack goal | No defenses | Both layers |
|---|---|---|
| Make the agent call a tool (40 attacks) | 9 | 0 |
| Put the attacker's text in the answer (50 attacks) | 45 | 9 |
| **Total (90)** | **54 (60%)** | **9 (10%)** |

Residual risk, stated plainly:

- This is not solved. The templates are public ones; published defenses with near-zero rates have
  been broken by attackers who adapt to them, and no benchmark covers a 14B local model or Spanish.
- The reader lets through instructions that look like data ("the warranty was cancelled", a promo
  code inside a note). Treat anything the agent reports from an email or web page as unverified.
- `turn` mode forgets at the user's next message; the poisoned text stays in the conversation.
  `thread` mode keeps the block until the user confirms with a plain yes.
- A call decided before any external content is read is trusted, including its arguments.
- The direct tools (`find_real_leads`, `rag_index_obsidian_vault`) are not gated, and sub-agents
  read their own tool results without these layers: the policy protects the orchestrator's calls.
- Cost: one extra model call per external result, and 14 instead of 16 of 24 two-part requests
  complete, because the reader sometimes drops a fact that was needed.

## Secrets

All credentials live in `.env`, `credentials.json`, `token*.json` or session folders, and are
git-ignored. `tests/test_gitignore_secrets.py` fails if any of those patterns stops being ignored.

## Recommended GitHub token

Use a **fine-grained personal access token**, not a classic `ghp_` token:

- **Repository access:** *Only select repositories* → the private working repo only. Never the public mirror.
- **Permissions:**
  - Contents: **Read and write** (push branches)
  - Pull requests: **Read and write** (open PRs; merge goes through human approval anyway)
  - Metadata: Read (mandatory)
  - Everything else: **No access** (no Administration, Actions, Secrets, Workflows, Webhooks)
- **Expiration:** 30–90 days, then rotate.
- Protect `main` with a branch protection rule (require a PR, no force push) so even a leaked
  token cannot rewrite history.
