"""S2 split-session shadow rounds: durable, fail-closed completion manifest.

This module is deliberately independent from the production S2 pipeline.  The
experimental launcher is its only caller; importing it changes no production
behaviour.  All mutations are atomic (temporary file + os.replace), while the
outer ``.s2-scan.lock`` remains the single process-level writer lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
CHECKPOINT_RE = re.compile(r"^\d{4}-\d{4}$")
SESSION_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class ManifestError(RuntimeError):
    """Base class for a malformed or invalid manifest transition."""


class ManifestIncompleteError(ManifestError):
    """Raised when finalization is attempted before every required session."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _validate_run_id(value: str) -> None:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ManifestError(f"run_id must be a UUID: {value!r}") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ManifestError(f"run_id must be a lowercase UUID v4: {value!r}")


def new_manifest(
    checkpoint: str,
    run_id: str,
    sessions: Iterable[dict[str, Any]],
    *,
    state_file: str | None = None,
    output_file: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Return a new in-memory manifest; no files are written."""
    if not CHECKPOINT_RE.fullmatch(checkpoint):
        raise ManifestError(f"invalid checkpoint: {checkpoint!r}")
    _validate_run_id(run_id)

    normalized = []
    seen: set[str] = set()
    for order, raw in enumerate(sessions):
        session_id = str(raw.get("id", ""))
        if not SESSION_ID_RE.fullmatch(session_id) or session_id in seen:
            raise ManifestError(f"invalid or duplicate session id: {session_id!r}")
        seen.add(session_id)
        sites = [str(site).upper() for site in raw.get("sites", [])]
        if not sites or any(not site for site in sites):
            raise ManifestError(f"session {session_id!r} must own at least one site")
        normalized.append(
            {
                "id": session_id,
                "order": order,
                "sites": sites,
                "required": bool(raw.get("required", True)),
                "status": "pending",
                "attempts": [],
                "completed_at": None,
            }
        )
    if not normalized:
        raise ManifestError("at least one session is required")

    timestamp = created_at or _now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint": checkpoint,
        "run_id": run_id,
        "mode": "split-session-shadow",
        "status": "pending",
        "revision": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
        "state_file": state_file,
        "output_file": output_file,
        "sessions": normalized,
        "finalization": {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "exit_code": None,
            "artifacts": [],
            "error": None,
        },
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    """Validate schema and cross-field invariants, raising ``ManifestError``."""
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("unsupported schema_version")
    if not CHECKPOINT_RE.fullmatch(str(manifest.get("checkpoint", ""))):
        raise ManifestError("manifest checkpoint is invalid")
    _validate_run_id(str(manifest.get("run_id", "")))
    if manifest.get("status") not in {
        "pending",
        "running",
        "ready_to_finalize",
        "finalizing",
        "finalized",
        "failed",
    }:
        raise ManifestError("manifest status is invalid")
    sessions = manifest.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ManifestError("manifest sessions must be a non-empty list")
    ids: set[str] = set()
    running = 0
    for expected_order, session in enumerate(sessions):
        sid = session.get("id")
        if not isinstance(sid, str) or not SESSION_ID_RE.fullmatch(sid) or sid in ids:
            raise ManifestError(f"invalid or duplicate session id: {sid!r}")
        ids.add(sid)
        if session.get("order") != expected_order:
            raise ManifestError("session order must be contiguous")
        if session.get("status") not in {"pending", "running", "completed", "failed"}:
            raise ManifestError(f"invalid status for session {sid}")
        if session.get("status") == "running":
            running += 1
        attempts = session.get("attempts")
        if not isinstance(attempts, list):
            raise ManifestError(f"attempts for session {sid} must be a list")
    if running > 1:
        raise ManifestError("split sessions must be sequential; multiple sessions are running")
    finalization = manifest.get("finalization")
    if not isinstance(finalization, dict) or finalization.get("status") not in {
        "pending",
        "running",
        "completed",
        "failed",
    }:
        raise ManifestError("finalization is invalid")
    if manifest.get("status") == "finalized" and finalization.get("status") != "completed":
        raise ManifestError("a finalized round must have completed finalization")


def write_manifest(path: str | os.PathLike[str], manifest: dict[str, Any]) -> None:
    """Atomically write a validated manifest to ``path``."""
    validate_manifest(manifest)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as temp:
            temp_name = temp.name
            temp.write(payload)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def load_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    validate_manifest(manifest)
    return manifest


def _session(manifest: dict[str, Any], session_id: str) -> dict[str, Any]:
    for session in manifest["sessions"]:
        if session["id"] == session_id:
            return session
    raise ManifestError(f"unknown session: {session_id}")


def _mutate(path: str | os.PathLike[str], fn: Any) -> dict[str, Any]:
    manifest = load_manifest(path)
    updated = deepcopy(manifest)
    fn(updated)
    updated["revision"] = manifest["revision"] + 1
    updated["updated_at"] = _now()
    write_manifest(path, updated)
    return updated


def start_session(
    path: str | os.PathLike[str], session_id: str, *, pid: int | None = None,
    attempt_id: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Start the next session in order and return ``(manifest, attempt_id)``."""
    chosen = attempt_id or str(uuid.uuid4())

    def change(manifest: dict[str, Any]) -> None:
        target = _session(manifest, session_id)
        if target["status"] not in {"pending", "failed"}:
            raise ManifestError(f"session {session_id} cannot start from {target['status']}")
        for earlier in manifest["sessions"][: target["order"]]:
            if earlier["required"] and earlier["status"] != "completed":
                raise ManifestIncompleteError(
                    f"session {session_id} cannot start before {earlier['id']} completes"
                )
        if any(s["status"] == "running" for s in manifest["sessions"]):
            raise ManifestError("another session is already running")
        target["status"] = "running"
        target["attempts"].append(
            {
                "attempt_id": chosen,
                "status": "running",
                "pid": pid,
                "started_at": _now(),
                "ended_at": None,
                "exit_code": None,
                "log_path": None,
                "log_size": None,
                "log_sha256": None,
                "error": None,
            }
        )
        manifest["status"] = "running"

    return _mutate(path, change), chosen


def finish_session(
    path: str | os.PathLike[str], session_id: str, attempt_id: str, *,
    exit_code: int, log_path: str | os.PathLike[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Finish an attempt. Success requires exit 0 and a non-empty log file."""

    def change(manifest: dict[str, Any]) -> None:
        target = _session(manifest, session_id)
        if target["status"] != "running" or not target["attempts"]:
            raise ManifestError(f"session {session_id} has no running attempt")
        attempt = target["attempts"][-1]
        if attempt["attempt_id"] != attempt_id or attempt["status"] != "running":
            raise ManifestError("attempt id does not match the running attempt")

        log = Path(log_path) if log_path else None
        log_ok = bool(log and log.is_file() and log.stat().st_size > 0)
        succeeded = exit_code == 0 and log_ok and not error
        attempt["ended_at"] = _now()
        attempt["exit_code"] = exit_code
        attempt["log_path"] = str(log) if log else None
        attempt["error"] = error
        if log_ok and log:
            content = log.read_bytes()
            attempt["log_size"] = len(content)
            attempt["log_sha256"] = hashlib.sha256(content).hexdigest()
        attempt["status"] = "completed" if succeeded else "failed"
        target["status"] = attempt["status"]
        target["completed_at"] = attempt["ended_at"] if succeeded else None

        if succeeded and all(
            (not item["required"]) or item["status"] == "completed"
            for item in manifest["sessions"]
        ):
            manifest["status"] = "ready_to_finalize"
        elif succeeded:
            manifest["status"] = "running"
        else:
            manifest["status"] = "failed"

    return _mutate(path, change)


def assert_complete(manifest: dict[str, Any]) -> None:
    """Fail closed unless every required child session completed successfully."""
    validate_manifest(manifest)
    missing = [
        item["id"] for item in manifest["sessions"]
        if item["required"] and item["status"] != "completed"
    ]
    if missing:
        raise ManifestIncompleteError("required sessions incomplete: " + ", ".join(missing))
    if manifest["status"] not in {"ready_to_finalize", "finalizing", "finalized"}:
        raise ManifestIncompleteError(f"round status is {manifest['status']}")


def start_finalization(path: str | os.PathLike[str]) -> dict[str, Any]:
    def change(manifest: dict[str, Any]) -> None:
        assert_complete(manifest)
        finalization = manifest["finalization"]
        if finalization["status"] not in {"pending", "failed"}:
            raise ManifestError(f"cannot finalize from {finalization['status']}")
        finalization.update(
            status="running", started_at=_now(), completed_at=None,
            exit_code=None, artifacts=[], error=None,
        )
        manifest["status"] = "finalizing"

    return _mutate(path, change)


def finish_finalization(
    path: str | os.PathLike[str], *, exit_code: int,
    artifacts: Iterable[str | os.PathLike[str]] = (), error: str | None = None,
) -> dict[str, Any]:
    """Finish render/finalization; success requires all artifacts to be non-empty."""

    def change(manifest: dict[str, Any]) -> None:
        finalization = manifest["finalization"]
        if finalization["status"] != "running":
            raise ManifestError("finalization is not running")
        artifact_rows = []
        all_ok = True
        for raw in artifacts:
            artifact = Path(raw)
            exists = artifact.is_file() and artifact.stat().st_size > 0
            all_ok = all_ok and exists
            artifact_rows.append(
                {"path": str(artifact), "exists": exists,
                 "size": artifact.stat().st_size if exists else None}
            )
        succeeded = exit_code == 0 and bool(artifact_rows) and all_ok and not error
        finalization.update(
            status="completed" if succeeded else "failed",
            completed_at=_now(), exit_code=exit_code,
            artifacts=artifact_rows, error=error,
        )
        manifest["status"] = "finalized" if succeeded else "failed"

    return _mutate(path, change)


def _parse_session(value: str) -> dict[str, Any]:
    try:
        session_id, sites_text = value.split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("session must be ID:SITE,SITE") from exc
    sites = [item.strip() for item in sites_text.split(",") if item.strip()]
    return {"id": session_id.strip(), "sites": sites, "required": True}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--manifest", required=True)
    init.add_argument("--checkpoint", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--session", action="append", type=_parse_session, required=True)
    init.add_argument("--state-file")
    init.add_argument("--output-file")

    start = sub.add_parser("start-session")
    start.add_argument("--manifest", required=True)
    start.add_argument("--session-id", required=True)
    start.add_argument("--pid", type=int)
    start.add_argument("--attempt-id")

    finish = sub.add_parser("finish-session")
    finish.add_argument("--manifest", required=True)
    finish.add_argument("--session-id", required=True)
    finish.add_argument("--attempt-id", required=True)
    finish.add_argument("--exit-code", type=int, required=True)
    finish.add_argument("--log")
    finish.add_argument("--error")

    complete = sub.add_parser("assert-complete")
    complete.add_argument("--manifest", required=True)

    start_fin = sub.add_parser("start-finalize")
    start_fin.add_argument("--manifest", required=True)

    finish_fin = sub.add_parser("finish-finalize")
    finish_fin.add_argument("--manifest", required=True)
    finish_fin.add_argument("--exit-code", type=int, required=True)
    finish_fin.add_argument("--artifact", action="append", default=[])
    finish_fin.add_argument("--error")

    status = sub.add_parser("status")
    status.add_argument("--manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init":
            manifest = new_manifest(
                args.checkpoint, args.run_id, args.session,
                state_file=args.state_file, output_file=args.output_file,
            )
            write_manifest(args.manifest, manifest)
        elif args.command == "start-session":
            manifest, attempt_id = start_session(
                args.manifest, args.session_id, pid=args.pid,
                attempt_id=args.attempt_id,
            )
            print(attempt_id)
            return 0
        elif args.command == "finish-session":
            manifest = finish_session(
                args.manifest, args.session_id, args.attempt_id,
                exit_code=args.exit_code, log_path=args.log, error=args.error,
            )
        elif args.command == "assert-complete":
            manifest = load_manifest(args.manifest)
            assert_complete(manifest)
        elif args.command == "start-finalize":
            manifest = start_finalization(args.manifest)
        elif args.command == "finish-finalize":
            manifest = finish_finalization(
                args.manifest, exit_code=args.exit_code,
                artifacts=args.artifact, error=args.error,
            )
        else:
            manifest = load_manifest(args.manifest)
        print(json.dumps(
            {"checkpoint": manifest["checkpoint"], "run_id": manifest["run_id"],
             "status": manifest["status"], "revision": manifest["revision"]},
            ensure_ascii=False,
        ))
        return 0
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
