"""Command-line interface for deterministic Evaluate/Review contracts."""

import argparse
import hashlib
import json
import os
import time
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .finalize import finalize
from .materialize import (
    materialize_source_packet,
    remove_materialized_packet,
    verify_materialized_packet,
)
from .gate import generate_gate, validate_gate_file
from .pack import (ContractError, build_packet, default_output_root, materialize_evidence,
                   packet_context, repository_slug, validate_gate_binding, validate_packet_schema)
from .orchestrate import run_dual_stages
from .result_validation import validate_provider_result
from .run_provider import run_provider_stage
from .snapshot import (
    PacketPolicyError,
    compute_source_snapshot,
    compute_tree_sha256,
    validate_packet_bindings,
)


_STAGES = ("evaluate", "review")
_ENGINES = ("claude", "codex")


def _load(path: str) -> Dict[str, Any]:
    with Path(path).open() as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _emit(value: Dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _discard_materialized_packet(root: Path) -> List[str]:
    """Remove a copy the run can no longer use; report a failure to do so, never mask it.

    The copy is locked 0o444/0o555, so removal can fail on its own. That failure is a second
    fact next to the cause that made the copy unusable, not a replacement for it: the caller
    appends the returned code to its own verdict, and only the code is published.
    """
    try:
        remove_materialized_packet(root)
    except Exception:
        return ["MATERIALIZED_PACKET_REMOVE_FAILED"]
    return []


def _attach_cleanup_errors(error: BaseException, codes: List[str]) -> None:
    """Carry cleanup codes on an exception the caller re-raises, for ``main`` to append.

    The cause owns the verdict, so a failed removal travels with it instead of replacing it or
    being dropped. An exception type that refuses the attribute simply carries nothing; the
    cause is still reported.
    """
    if not codes:
        return
    try:
        error.cleanup_errors = [*getattr(error, "cleanup_errors", ()), *codes]
    except AttributeError:
        pass


def _cleanup_errors(error: BaseException) -> List[str]:
    """Cleanup codes attached on the way up, reported after the cause."""
    return list(getattr(error, "cleanup_errors", ()))


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


def command_gate(args: argparse.Namespace) -> int:
    result = generate_gate(Path(args.repo), args.cmd, Path(args.out), issue_type=args.issue_type)
    _emit(result)
    return 0 if result["status"] == "PASS" else 2


def command_pack(args: argparse.Namespace) -> int:
    models = {"claude": args.claude_model or os.environ.get("CLAUDE_MODEL_ID"),
              "codex": args.codex_model or os.environ.get("CODEX_MODEL_ID")}
    if not all(models.values()):
        raise ContractError(["MODEL_ID_REQUIRED"])
    packet = build_packet(Path(args.repo), Path(args.artifacts), args.request_source,
                          args.base, models, issue_type=args.issue_type)
    _emit({"status": "PASS", "packet_id": packet["packet_id"],
           "packet_path": str(Path(args.artifacts).resolve() / "eval-review/packet/packet.json")})
    return 0


def _run_arguments(args: argparse.Namespace) -> None:
    if args.from_packet:
        if any((args.packet, args.packet_source, args.evaluate_prompt, args.review_prompt)):
            raise ContractError(["RUN_ARGUMENT_CONFLICT"])
        folder = Path(args.from_packet).resolve()
        args.packet = str(folder / "packet.json")
        packet = _load(args.packet)
        schema_errors = validate_packet_schema(packet)
        if schema_errors:
            raise ContractError(schema_errors)
        args.packet_source = packet.get("request", {}).get("repository")
        if not args.packet_source:
            raise ContractError(["PACKET_REPOSITORY_MISMATCH"])
        repo = Path(args.packet_source).resolve()
        _, identifier, artifacts = packet_context(packet, repo)
        if folder != artifacts / "eval-review" / "packet":
            raise ContractError(["ARTIFACT_PATH_INVALID"])
        args.evaluate_prompt = str(folder / "evaluate-prompt.md")
        args.review_prompt = str(folder / "review-prompt.md")
        args.output_root = args.output_root or str(default_output_root(repo, identifier))
        args.claude_model = args.claude_model or os.environ.get("CLAUDE_MODEL_ID")
        args.codex_model = args.codex_model or os.environ.get("CODEX_MODEL_ID")
    required = ("packet", "packet_source", "evaluate_prompt", "review_prompt",
                "output_root", "claude_model", "codex_model")
    if any(not getattr(args, field) for field in required):
        raise ContractError(["RUN_ARGUMENTS_MISSING"])


def _copy_run_reports(output: Path, artifacts: Path) -> Path:
    index = 1
    destination = artifacts / "eval-review" / ("run-" + str(index))
    while destination.exists():
        index += 1
        destination = artifacts / "eval-review" / ("run-" + str(index))
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("final-result.json", "execution-manifest.json"):
        (destination / name).write_bytes((output / name).read_bytes())
    return destination


def command_run(args: argparse.Namespace) -> int:
    """Run blind Dual Evaluate followed by Dual Review and persist parent-owned artifacts."""
    _run_arguments(args)
    packet = _load(args.packet)
    packet_source = Path(args.packet_source).resolve()
    output_root = Path(args.output_root).resolve()
    if output_root == packet_source or packet_source in output_root.parents:
        raise ValueError("output_root must be outside packet_source")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output_root must be absent or empty")
    binding_errors = validate_packet_bindings(packet, packet_source)
    schema_errors = validate_packet_schema(packet)
    if ("SOURCE_SNAPSHOT_MISMATCH" in binding_errors and isinstance(packet.get("request"), dict)
            and isinstance(packet["request"].get("gate"), dict)):
        gate_path = packet_source / packet["request"]["gate"].get("path", "")
        early_gate_errors = validate_gate_file(gate_path, packet_source,
                                              track=packet["request"].get("track"),
                                              issue_type=packet["request"].get("issue_type"))
        if "GATE_STALE" in early_gate_errors:
            binding_errors.append("GATE_STALE")
    binding_errors = list(dict.fromkeys(schema_errors + binding_errors))
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
    gate_binding_errors = validate_gate_binding(packet)
    if gate_binding_errors:
        _emit({"status": "BLOCKED", "errors": gate_binding_errors})
        return 2
    track, identifier, artifacts = packet_context(packet, packet_source)
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
    copy_started = time.monotonic()
    materialized_manifest = materialize_source_packet(packet_source, materialized_root)
    copy_duration_ms = int((time.monotonic() - copy_started) * 1000)
    if not verify_materialized_packet(materialized_root, materialized_manifest):
        _emit({"status": "BLOCKED", "errors": ["MATERIALIZED_PACKET_MISMATCH"]})
        return 2
    # The packet was bound to the live tree before the copy, and the tree may have changed
    # in between. Snapshot it again now and compare both ways: the packet identity against
    # the tree as it is, and the tree as it is against the bytes that were actually copied.
    # The first alone misses a change reverted after the copy; the second alone never ties
    # the copy to the packet.
    try:
        recomputed = compute_source_snapshot(packet_source)
    except (OSError, subprocess.CalledProcessError):
        # The same git or filesystem fault validate_packet_bindings reports under this code;
        # the recheck says the same, and the copy still goes.
        _emit({"status": "BLOCKED", "errors": [
            "SOURCE_SNAPSHOT_UNAVAILABLE", *_discard_materialized_packet(materialized_root),
        ]})
        return 2
    except Exception as error:
        # The tree became something the enumerator refuses (PacketPolicyError keeps its code
        # and paths through main). A locked copy of a tree no longer bound to anything must
        # not stay, and a removal that fails is a second fact next to that cause: the cause
        # keeps the verdict and main appends the cleanup code after it.
        _attach_cleanup_errors(error, _discard_materialized_packet(materialized_root))
        raise
    if (
        recomputed["source_snapshot_id"] != packet["source_snapshot_id"]
        or compute_tree_sha256(recomputed["manifest"]["files"])
        != materialized_manifest.get("source_tree_sha256")
    ):
        _emit({"status": "BLOCKED", "errors": [
            "SOURCE_CHANGED_BEFORE_MATERIALIZE", *_discard_materialized_packet(materialized_root),
        ]})
        return 2
    try:
        evidence_root = materialize_evidence(packet_source, materialized_root, packet["evidence_entries"])
        gate_errors = validate_gate_file(
            evidence_root / "gate-result.json", packet_source, evidence_root=evidence_root,
            source_snapshot_id=recomputed["source_snapshot_id"], track=track,
            issue_type=packet["request"].get("issue_type"),
        )
        if gate_errors:
            raise ContractError(gate_errors)
    except Exception as error:
        _attach_cleanup_errors(error, _discard_materialized_packet(materialized_root))
        raise
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
        "repository_slug": repository_slug(packet_source), "identifier": identifier,
        "repository": str(packet_source), "output_root": str(output_root),
        "materialize_duration_ms": copy_duration_ms,
        "materialized_bytes": sum(p.stat().st_size for p in materialized_root.rglob("*")
                                  if p.is_file() and not p.is_symlink()),
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
            readable_roots=[materialized_root],
        )

    result = run_dual_stages(runner, packet)
    result_path = output_root / "final-result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    sealed_root = output_root / "sealed-results"
    sealed_root.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(result.get("results", [])):
        envelope = record.get("envelope", {}) if isinstance(record, dict) else {}
        stage = envelope.get("stage")
        engine = envelope.get("engine")
        # The file name comes from the parent-owned envelope and only from the two
        # enums; a model-owned string must never decide where the parent writes.
        if stage in _STAGES and engine in _ENGINES:
            name = f"{stage}-{engine}.json"
        else:
            name = f"unknown-{index}.json"
        (sealed_root / name).write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    report_copy = _copy_run_reports(output_root, artifacts)
    _emit({
        "report_copy": str(report_copy),
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

    gate = subparsers.add_parser("gate")
    gate.add_argument("--repo", required=True)
    gate.add_argument("--cmd", action="append", required=True)
    gate.add_argument("--out", required=True)
    gate.add_argument("--issue-type", choices=("bug", "feature", "refactor", "hotfix", "performance"))
    gate.set_defaults(func=command_gate)

    pack = subparsers.add_parser("pack")
    pack.add_argument("--repo", required=True)
    pack.add_argument("--artifacts", required=True)
    pack.add_argument("--request-source", required=True)
    pack.add_argument("--base", required=True)
    pack.add_argument("--claude-model")
    pack.add_argument("--codex-model")
    pack.add_argument("--issue-type", choices=("bug", "feature", "refactor", "hotfix", "performance"))
    pack.set_defaults(func=command_pack)

    run = subparsers.add_parser("run")
    run.add_argument("--from", dest="from_packet")
    run.add_argument("--packet")
    run.add_argument("--packet-source")
    run.add_argument("--evaluate-prompt")
    run.add_argument("--review-prompt")
    run.add_argument("--output-root")
    run.add_argument("--timeout", type=float, default=240)
    run.add_argument("--claude-model")
    run.add_argument("--codex-model")
    run.set_defaults(func=command_run)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except ContractError as error:
        payload = {"status": "BLOCKED", "errors": [*error.errors, *_cleanup_errors(error)]}
        if error.paths:
            payload["paths"] = error.paths
        _emit(payload)
        return 2
    except PacketPolicyError as error:
        # Paths only. The refused bytes never reach stdout. A cleanup that failed on the way
        # here is reported after the cause, never instead of it.
        _emit({
            "status": "BLOCKED", "errors": [error.code, *_cleanup_errors(error)],
            "paths": error.paths,
        })
        return 2
    except Exception as error:
        # Untrusted provider output and a resource fault must both leave a JSON verdict
        # rather than a traceback, so every ordinary exception is mapped to BLOCKED and
        # only its type is published. KeyboardInterrupt and SystemExit derive from
        # BaseException and are deliberately left to propagate.
        _emit({"status": "BLOCKED", "errors": [type(error).__name__, *_cleanup_errors(error)]})
        return 2


if __name__ == "__main__":
    sys.exit(main())
