# Evals

Offline evaluation of AI-Forge's three decision points, run against the **local** Ollama model
(the runner forces `LLM_PROVIDER=local`, so eval data never reaches a cloud API).

```bash
python -m evals.run                         # all suites, generic data
python -m evals.run --suite routing --limit 10
python -m evals.run --model qwen2.5:7b      # compare models
python -m evals.run --private               # generic + your own data in evals/private/
```

Results are printed and saved as JSON in `evals/results/` (git-ignored). Runs that include
private data are saved only under `evals/private/results/`.

## Suites

| Suite | Dataset | What is measured |
|---|---|---|
| `routing` | `datasets/routing.jsonl` (42 requests) | First tool the orchestrator LLM calls, given the real prompt and tool schemas. Accuracy, per-class precision/recall, confusion matrix. No sub-agent is executed. |
| `grounding` | `datasets/grounding.jsonl` (16 requests) | Full tool loop with the real prompt and tool schemas; every agent returns canned text and only the right one has the data. **Grounding rate** (right agent called and its facts are in the answer) and **ignore rate** (right agent called but its result was dropped). Also counts wrong-agent and no-tool answers. |
| `memory_gate` | `datasets/memory_gate.jsonl` (50 turns, 10 per class) | `MemoryGate._classify` type accuracy, **EPHEMERAL leak rate** (would store something it should not; target 0) and store recall. |
| `rag` | `datasets/rag.jsonl` + `datasets/rag_docs/` (4 fictional docs, 20 + 5 questions) | Answer accuracy (expected facts present), abstention on unanswerable questions (hallucination rate), false "no sé" rate. Uses a temporary ChromaDB. |

All generic data is invented. Labels for ambiguous routing requests list several accepted tools.

## Private data

Put your own files in `evals/private/` (git-ignored) using the same names and formats:
`routing.jsonl`, `grounding.jsonl`, `memory_gate.jsonl`, `rag.jsonl` and `rag_docs/`. Use `--private` to add them
to the generic set or `--private-only` to run them alone.

## Formats

```jsonc
// routing.jsonl
{"text": "¿Qué eventos tengo mañana?", "expected": ["calendar"]}
// grounding.jsonl  ("tool": agents that may answer; "expected": facts the answer must contain)
{"text": "¿Qué eventos tengo mañana?", "tool": ["calendar"], "result": "Mañana: 09:15 reunión con Lucía", "expected": ["09:15"]}
// memory_gate.jsonl  (fact | preference | decision | event | ephemeral)
{"text": "Usuario: Prefiero respuestas cortas.\nAsistente: De acuerdo.", "expected": "preference"}
// rag.jsonl
{"question": "¿Qué base de datos usa Atlas?", "expected": ["postgresql"]}
{"question": "¿Quién es el CEO?", "answerable": false}
```

## Limits of keyword scoring

RAG answers are scored by checking that the expected strings appear (case/accent-insensitive)
and abstentions by regex. That is cheap and deterministic but can miss paraphrases ("dos mil
quince") or count "no se permite" as an abstention. An LLM-as-judge pass is the next step for
open-ended answers; see the main README.
