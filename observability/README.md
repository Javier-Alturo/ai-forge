# Observability — self-hosted LangFuse

Every orchestrator turn becomes one trace in a LangFuse instance running **on this machine**:
the orchestrator's LLM calls, the tool it picked, and — nested inside — the sub-agent's own LLM
calls and tools, each with latency, token usage and errors.

```
orchestrator_turn                      7.0s   session=<thread id>
├─ agent → ChatOllama                  4.6s   3062 in / 17 out tokens
└─ tools → orchestrator_consult_code_agent
   └─ subagent:code                    1.6s
      ├─ agent → ChatOllama            0.6s
      └─ tools → code_generate_and_execute
```

## Run it

```bash
python observability/setup_env.py --write-app-env   # once: random secrets + LANGFUSE_* in .env
docker compose -f observability/docker-compose.yml up -d
# UI: http://localhost:3000  (user admin@langfuse.local, password in observability/.env)
docker compose -f observability/docker-compose.yml down        # stop (data is kept)
docker compose -f observability/docker-compose.yml down -v     # stop and delete all traces
```

Tracing is off unless `LANGFUSE_ENABLED=1`. `observability/tracing.py` refuses to send traces
to a non-local `LANGFUSE_HOST` unless `LANGFUSE_ALLOW_REMOTE=1`.

## What the compose file runs

| Service | Role | Published |
|---|---|---|
| `langfuse-web` | UI + ingestion API | `127.0.0.1:3000` |
| `langfuse-worker` | processes ingested events in the background | no |
| `postgres` | users, projects, API keys | no |
| `clickhouse` | traces/observations (analytics database) | no |
| `redis` | queue between web and worker | no |
| `minio` | S3-compatible storage for raw events and media | `127.0.0.1:9090` |

Differences from the upstream compose: every published port is bound to `127.0.0.1`, the
databases are not published at all, there are no default passwords (compose fails if a
secret is missing), product telemetry and sign-up are disabled, and the org/project/API
keys/user are created headlessly on first boot.

## How sub-agent traces stay nested

Sub-agents run in a worker thread (for the hard timeout). LangChain keeps the current run's
child config in a context variable, which does not cross threads, so each `consult` tool calls
`ensure_config()` and passes that config explicitly to the sub-agent
(`agents/subagent_runner.child_config`). Without this, every sub-agent call would appear as a
separate, disconnected trace.

## Reading traces from code

LangFuse v4 runs in events-only mode: use `GET /api/public/v2/observations`
(basic auth: public key / secret key) instead of the v3 `/api/public/traces` endpoint.
