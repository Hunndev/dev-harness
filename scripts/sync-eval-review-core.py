#!/usr/bin/env python3
"""Vendor the minimal Evaluate/Review core into standalone stack plugins."""

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ("BE", "CM", "FE", "CHAT", "AOS", "IOS")


def mappings(plugin: str) -> List[Tuple[Path, Path]]:
    destination = ROOT / plugin
    pairs: List[Tuple[Path, Path]] = []
    for source in sorted((ROOT / "SHARED" / "contracts").glob("*.json")):
        pairs.append((source, destination / "contracts" / source.name))
    for source in sorted((ROOT / "SHARED" / "runtime" / "hb_eval_review").rglob("*.py")):
        relative = source.relative_to(ROOT / "SHARED")
        pairs.append((source, destination / relative))
    pairs.append((ROOT / "SHARED" / "bin" / "hb-eval-review", destination / "bin" / "hb-eval-review"))
    pairs.extend(
        [
            (ROOT / "SHARED" / "commands" / "evaluate.md", destination / "commands" / "shared" / "evaluate.md"),
            (ROOT / "SHARED" / "commands" / "review.md", destination / "commands" / "shared" / "review.md"),
        ]
    )
    return pairs


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(str(source), str(temporary))
    shutil.copymode(str(source), str(temporary))
    os.replace(str(temporary), str(destination))


def run(check: bool) -> int:
    drift: List[str] = []
    for plugin in PLUGINS:
        manifest = {}
        for source, destination in mappings(plugin):
            relative = destination.relative_to(ROOT / plugin).as_posix()
            manifest[relative] = digest(source)
            if check:
                if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                    drift.append(f"{plugin}/{relative}")
            else:
                sync_file(source, destination)
        manifest_path = ROOT / plugin / "eval-review-core.manifest.json"
        content = json.dumps({"schema_version": "1.0", "files": manifest}, indent=2, sort_keys=True) + "\n"
        if check:
            if not manifest_path.is_file() or manifest_path.read_text() != content:
                drift.append(f"{plugin}/{manifest_path.name}")
        else:
            manifest_path.write_text(content)
    if drift:
        print("EVAL_REVIEW_CORE_DRIFT")
        for item in drift:
            print(item)
        return 1
    print("EVAL_REVIEW_CORE_SYNC=PASS" if check else "EVAL_REVIEW_CORE_SYNC=UPDATED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
