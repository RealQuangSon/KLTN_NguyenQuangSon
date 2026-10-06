"""Hash shareable repository sources, excluding local state and generated results."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    names = subprocess.check_output([
        "rg", "--files", "--hidden", "-g", "!.git/**", "-g", "!.local/**",
        "-g", "!.venv/**", "-g", "!**/node_modules/**", "-g", "!**/dist/**",
        "-g", "!**/__pycache__/**", "-g", "!.pytest_cache/**", "-g", "!**/.cache/**",
        "-g", "!*.env", "-g", "!*.env.local", "-g", "!*.sqlite*",
        "-g", "!eval/runs/**", "-g", "!eval/labels/**", "-g", "!docs/release-manifest.json",
    ], cwd=ROOT, text=True).splitlines()
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in sorted(names)}
    source_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    packages = {}
    for name in ("fastapi", "pydantic", "langgraph", "langgraph-checkpoint-postgres", "openai", "psycopg", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "source_hash": source_hash,
            "files": hashes, "runtime": {"python": platform.python_version(),
                                          "platform": platform.platform(), "packages": packages},
            "deployment": "local-only", "api_workers": 1,
            "live_provider_verified": False, "research_relevance_labels": "pending_human_annotation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/release-manifest.json")
    args = parser.parse_args()
    result = manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(args.output), "source_hash": result["source_hash"],
                      "file_count": len(result["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
