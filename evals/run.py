"""Run AI-Forge evals against the local Ollama model and save the metrics as JSON.

    python -m evals.run                        # all suites, generic data
    python -m evals.run --suite routing --limit 10
    python -m evals.run --private              # generic + evals/private/ (results stay in evals/private/results)
    python -m evals.run --private-only --model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SUITES = ("routing", "grounding", "memory_gate", "rag")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-Forge evals (local Ollama)")
    parser.add_argument("--suite", choices=(*SUITES, "all"), default="all")
    parser.add_argument("--private", action="store_true", help="also use evals/private/ datasets")
    parser.add_argument("--private-only", action="store_true", help="only evals/private/ datasets")
    parser.add_argument("--model", help="Ollama model (overrides OLLAMA_MODEL)")
    parser.add_argument("--limit", type=int, help="max items per suite (quick runs)")
    parser.add_argument("--out", type=Path, help="explicit output JSON path")
    return parser.parse_args(argv)


def _progress(name: str):
    def report(i: int, n: int) -> None:
        print(f"\r  {name}: {i}/{n}", end="" if i < n else "\n", flush=True)
    return report


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def check_ollama(base_url: str) -> None:
    import httpx

    try:
        httpx.get(f"{base_url}/api/tags", timeout=5.0).raise_for_status()
    except httpx.HTTPError as e:
        raise SystemExit(f"Ollama no responde en {base_url} ({type(e).__name__}). Arráncalo con `ollama serve`.") from e


def run_suite(name: str, items: list[dict], llm, include_private: bool, private_only: bool) -> dict:
    from evals import datasets
    from evals.suites import grounding, memory_gate, rag, routing

    progress = _progress(name)
    if name == "routing":
        return routing.run(llm, items, progress)
    if name == "grounding":
        return grounding.run(llm, items, progress)
    if name == "memory_gate":
        return memory_gate.run(llm, items, progress)
    doc_dirs = [] if private_only else [datasets.GENERIC_DIR / "rag_docs"]
    if include_private or private_only:
        doc_dirs.append(datasets.PRIVATE_DIR / "rag_docs")
    return rag.run(items, doc_dirs, progress)


def summarize(name: str, result: dict) -> str:
    from evals.suites import grounding, memory_gate, rag, routing

    return {"routing": routing, "grounding": grounding, "memory_gate": memory_gate, "rag": rag}[name].summary(result)


def main(argv: list[str] | None = None) -> dict:
    args = parse_args(argv)
    # Evals always run locally: data never goes to a cloud LLM.
    os.environ["LLM_PROVIDER"] = "local"
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model

    from agents.llm import OLLAMA_BASE, OLLAMA_MODEL, get_llm
    from evals import datasets

    uses_private = args.private or args.private_only
    check_ollama(OLLAMA_BASE)
    llm = get_llm(temperature=0.0)
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": OLLAMA_MODEL,
        "git_commit": _git_commit(),
        "uses_private_data": uses_private,
        "suites": {},
    }
    for name in SUITES if args.suite == "all" else (args.suite,):
        items = datasets.load(name, include_private=args.private, private_only=args.private_only)[: args.limit]
        if not items:
            print(f"[{name}] sin datos, se omite.")
            continue
        print(f"\n=== {name} ({len(items)} items, model {OLLAMA_MODEL}) ===")
        start = time.time()
        result = run_suite(name, items, llm, args.private, args.private_only)
        result["seconds"] = round(time.time() - start, 1)
        report["suites"][name] = result
        print(summarize(name, result))

    out = args.out or datasets.results_dir(uses_private) / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    if uses_private and not out.resolve().is_relative_to(datasets.PRIVATE_DIR.resolve()):
        raise SystemExit("Los resultados con datos privados solo pueden guardarse dentro de evals/private/.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResultados guardados en {out}")
    return report


if __name__ == "__main__":
    main()
