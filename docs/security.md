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
| 10 | Hugging Face Hub | Model downloads (no user data) | Set `HF_HUB_OFFLINE=1` once models are cached. |
| 11 | GitHub Actions (`ai-pr-reviewer`, `pr-to-obsidian`) | PR diffs and descriptions sent to OpenAI / Groq | Runs on GitHub, not locally. Review before enabling on a repo that holds personal data. |

The dashboard binds to `127.0.0.1` only.

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
