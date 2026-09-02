"""Command-line interface for deterministic Evaluate/Review contracts."""

import argparse
import hashlib
import json
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .finalize import finalize
from .materialize import materialize_source_packet, verify_materialized_packet
from .orchestrate import run_dual_stages
from .result_validation import validate_provider_result
from .run_provider import run_provider_stage
from .snapshot import compute_source_snapshot, validate_packet_bindings


def _load(path: str) -> Dict[str, Any]:
    with Path(path).open() as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _emit(value: Dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def command_snapshot(args: argparse.Namespace) -> int:
    snapshot = compute_source_snapshot(Path(args.repository))
    _emit({"source_snapshot_id": snapshot["source_snapshot_id"]})
    return 0


def command_validate(args: argparse.Namespace) -> int:
    packet = _load(args.packet)
    result = _load(args.result)
    errors = validate_provider_result(result, args.stage, args.engine, packet)
    status = "PASS" if not errors else "BLOCKED"
    _emit({"status": status, "errors": errors})
    return 0 if status == "PASS" else 2


def command_finalize(args: argparse.Namespace) -> int:
    packet = _load(args.packet)
    results: List[Dict[str, Any]] = []
    for path in args.results:
        item = _load(path)
        results.append(item)
    final = finalize(results, packet)
    _emit(final)
    return 0 if final["status"] == "PASS" else 2


def command_run(args: argparse.Namespace) -> int:
    """Run blind Dual Evaluate followed by Dual Review and persist parent-owned artifacts."""
    packet = _load(args.packet)
    packet_source = Path(args.packet_source).resolve()
    output_root = Path(args.output_root).resolve()
    if output_root == packet_source or packet_source in output_root.parents:
        raise ValueError("output_root must be outside packet_source")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output_root must be absent or empty")
    binding_errors = validate_packet_bindings(packet, packet_source)
    if binding_errors:
        _emit({"status": "BLOCKED", "errors": binding_errors})
        return 2
    prompts = {
        "evaluate": Path(args.evaluate_prompt).read_text(),
        "review": Path(args.review_prompt).read_text(),
    }
    prompt_sha256 = {
        stage: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for stage, value in prompts.items()
    }
    expected_prompt_sha256 = packet.get("request", {}).get("prompt_sha256")
    if expected_prompt_sha256 != prompt_sha256:
        _emit({"status": "BLOCKED", "errors": ["PROMPT_DIGEST_MISMATCH"]})
        return 2
    model_ids = {"claude": args.claude_model, "codex": args.codex_model}
    if packet.get("request", {}).get("model_ids") != model_ids:
        _emit({"status": "BLOCKED", "errors": ["MODEL_ID_MISMATCH"]})
        return 2
    parent_facts = json.dumps({
        "packet_id": packet["packet_id"],
        "source_snapshot_id": packet["source_snapshot_id"],
        "evidence_bundle_id": packet["evidence_bundle_id"],
    }, ensure_ascii=False, sort_keys=True)
    effective_prompts = {
        stage: value + "\n\n# Parent-owned packet facts\n" + parent_facts
        for stage, value in prompts.items()
    }
    effective_prompt_sha256 = {
        stage: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for stage, value in effective_prompts.items()
    }
    output_root.mkdir(parents=True, exist_ok=True)
    materialized_root = output_root / "materialized-packet"
    materialized_manifest = materialize_source_packet(packet_source, materialized_root)
    if not verify_materialized_packet(materialized_root, materialized_manifest):
        _emit({"status": "BLOCKED", "errors": ["MATERIALIZED_PACKET_MISMATCH"]})
        return 2
    provider_source = materialized_root / "source"
    (output_root / "execution-manifest.json").write_text(json.dumps({
        "schema_version": "1.0",
        "packet_id": packet["packet_id"],
        "source_snapshot_id": packet["source_snapshot_id"],
        "evidence_bundle_id": packet["evidence_bundle_id"],
        "prompt_sha256": prompt_sha256,
        "effective_prompt_sha256": effective_prompt_sha256,
        "model_ids": model_ids,
        "isolation_policy": "macos-deny-default-v1",
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    lock = threading.Lock()
    review_cleanup_done = False

    def runner(stage: str, engine: str) -> Dict[str, Any]:
        nonlocal review_cleanup_done
        if stage == "review":
            with lock:
                if not review_cleanup_done:
                    # Review receives only the sealed packet, never either evaluator's output.
                    for candidate in (
                        output_root / "evaluate-claude", output_root / "evaluate-codex"
                    ):
                        if candidate.exists():
                            shutil.rmtree(str(candidate))
                    review_cleanup_done = True
        peer = "codex" if engine == "claude" else "claude"
        return run_provider_stage(
            engine=engine,
            stage=stage,
            packet=packet,
            packet_source=provider_source,
            output_root=output_root / f"{stage}-{engine}",
            prompt=effective_prompts[stage],
            timeout_seconds=args.timeout,
            peer_output_root=output_root / f"{stage}-{peer}",
            model=model_ids[engine],
        )

    result = run_dual_stages(runner, packet)
    result_path = output_root / "final-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    sealed_root = output_root / "sealed-results"
    sealed_root.mkdir(parents=True, exist_ok=True)
    for record in result.get("results", []):
        semantic = record.get("semantic", {}) if isinstance(record, dict) else {}
        envelope = record.get("envelope", {}) if isinstance(record, dict) else {}
        stage = semantic.get("stage") or envelope.get("stage", "unknown")
        engine = envelope.get("engine", "unknown")
        path = sealed_root / f"{stage}-{engine}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _emit({
        "status": result.get("status", "BLOCKED"),
        "stage": result.get("stage", "unknown"),
        "result_path": str(result_path),
        "final": result.get("final"),
        "errors": result.get("errors"),
    })
    return 0 if result.get("status") == "PASS" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hb-eval-review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("repository")
    snapshot.set_defaults(func=command_snapshot)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--stage", choices=("evaluate", "review"), required=True)
    validate.add_argument("--engine", choices=("claude", "codex"), required=True)
    validate.add_argument("packet")
    validate.add_argument("result")
    validate.set_defaults(func=command_validate)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("packet")
    finalize.add_argument("results", nargs="*")
    finalize.set_defaults(func=command_finalize)

    run = subparsers.add_parser("run")
    run.add_argument("--packet", required=True)
    run.add_argument("--packet-source", required=True)
    run.add_argument("--evaluate-prompt", required=True)
    run.add_argument("--review-prompt", required=True)
    run.add_argument("--output-root", required=True)
    run.add_argument("--timeout", type=float, default=240)
    run.add_argument("--claude-model", required=True)
    run.add_argument("--codex-model", required=True)
    run.set_defaults(func=command_run)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _emit({"status": "BLOCKED", "errors": [type(error).__name__]})
        return 2


if __name__ == "__main__":
    sys.exit(main())
