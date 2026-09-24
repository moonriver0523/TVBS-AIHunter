#!/usr/bin/env python3
"""Shared patch schema v1 and atomic file helpers for S2 rewrite-entry.

The patch document deliberately contains no target path.  The caller chooses the
target on its command line; ``target_sha256`` binds the patch to the exact bytes
that the agent inspected before preparing its changes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


SCHEMA_VERSION = 1
PATCH_FIELDS = frozenset(("entry", "category", "tc", "skip"))
_TOP_LEVEL_FIELDS = frozenset(("schema_version", "site", "target_sha256", "changes"))
_CHANGE_FIELDS = frozenset(("id", "set"))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PatchFileError(ValueError):
    """The patch cannot be safely interpreted or applied."""


@dataclass(frozen=True)
class PatchChange:
    supplied_id: str
    canonical_id: str
    values: Mapping[str, Any]

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(self.values)


@dataclass(frozen=True)
class PatchDocument:
    site: str
    target_sha256: str
    changes: tuple[PatchChange, ...]


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_target_sha(path: os.PathLike[str] | str, expected_sha256: str) -> str:
    try:
        actual = sha256_file(path)
    except OSError as exc:
        raise PatchFileError(f"target 無法讀取 SHA-256：{exc}") from exc
    if actual != expected_sha256:
        raise PatchFileError(
            "target_sha256 stale：patch 建立後 target 已被其他步驟修改；"
            f"expected={expected_sha256} actual={actual}"
        )
    return actual


def _unknown_fields(payload: Mapping[str, Any], allowed: Iterable[str]) -> list[str]:
    return sorted(set(payload) - set(allowed))


def load_patch(
    path: os.PathLike[str] | str,
    *,
    expected_site: str,
    canonicalize: Callable[[str], str],
    allowed_fields: Iterable[str] = PATCH_FIELDS,
) -> PatchDocument:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        raise PatchFileError(f"patch file 無法讀取：{exc}") from exc
    if not isinstance(payload, dict):
        raise PatchFileError("patch file 頂層必須是 object。")
    unknown = _unknown_fields(payload, _TOP_LEVEL_FIELDS)
    if unknown:
        raise PatchFileError(f"patch file 頂層含未知欄位：{', '.join(unknown)}")
    missing = sorted(_TOP_LEVEL_FIELDS - set(payload))
    if missing:
        raise PatchFileError(f"patch file 缺必要欄位：{', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PatchFileError(
            f"只支援 schema_version={SCHEMA_VERSION}，實得 {payload.get('schema_version')!r}。"
        )
    site = str(payload.get("site") or "").strip().lower()
    if site != str(expected_site).strip().lower():
        raise PatchFileError(f"patch 站別是 {site or '?'}，不是 {expected_site}。")
    target_sha256 = str(payload.get("target_sha256") or "").strip().lower()
    if not _SHA256_RE.fullmatch(target_sha256):
        raise PatchFileError("target_sha256 必須是 64 位小寫 hex SHA-256。")
    raw_changes = payload.get("changes")
    if not isinstance(raw_changes, list):
        raise PatchFileError("changes 必須是陣列。")

    allowed = frozenset(allowed_fields)
    changes: list[PatchChange] = []
    seen: dict[str, str] = {}
    for index, raw in enumerate(raw_changes, 1):
        if not isinstance(raw, dict):
            raise PatchFileError(f"changes[{index}] 必須是 object。")
        unknown = _unknown_fields(raw, _CHANGE_FIELDS)
        if unknown:
            raise PatchFileError(f"changes[{index}] 含未知欄位：{', '.join(unknown)}")
        missing = sorted(_CHANGE_FIELDS - set(raw))
        if missing:
            raise PatchFileError(f"changes[{index}] 缺必要欄位：{', '.join(missing)}")
        supplied_id = str(raw.get("id") or "").strip()
        canonical_id = str(canonicalize(supplied_id) or "").strip()
        if not supplied_id or not canonical_id:
            raise PatchFileError(f"changes[{index}].id 不是有效 ID。")
        if canonical_id in seen:
            raise PatchFileError(
                "changes 重複指定同一 canonical ID："
                f"{seen[canonical_id]}／{supplied_id}"
            )
        values = raw.get("set")
        if not isinstance(values, dict) or not values:
            raise PatchFileError(f"changes[{index}].set 必須是非空 object。")
        unknown = _unknown_fields(values, allowed)
        if unknown:
            raise PatchFileError(
                f"{supplied_id} 含不可修改欄位：{', '.join(unknown)}；"
                f"只允許 {', '.join(sorted(allowed))}。"
            )
        seen[canonical_id] = supplied_id
        changes.append(PatchChange(supplied_id, canonical_id, dict(values)))
    return PatchDocument(site, target_sha256, tuple(changes))


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(json_bytes(payload)).hexdigest()


def write_scaffold(
    out: os.PathLike[str] | str,
    *,
    site: str,
    target: os.PathLike[str] | str,
) -> None:
    try:
        target_sha256 = sha256_file(target)
    except OSError as exc:
        raise PatchFileError(f"target 無法讀取 SHA-256：{exc}") from exc
    scaffold = {
        "schema_version": SCHEMA_VERSION,
        "site": str(site).lower(),
        "target_sha256": target_sha256,
        "changes": [],
    }
    out_path = os.path.abspath(os.fspath(out))
    os.makedirs(os.path.dirname(out_path) or os.getcwd(), exist_ok=True)
    try:
        with open(out_path, "x", encoding="utf-8", newline="") as handle:
            json.dump(scaffold, handle, ensure_ascii=False, indent=2)
    except FileExistsError as exc:
        raise PatchFileError(f"patch scaffold 已存在，不覆寫：{out_path}") from exc
    except OSError as exc:
        raise PatchFileError(f"patch scaffold 無法寫入：{exc}") from exc


def atomic_write_json(path: os.PathLike[str] | str, payload: Any) -> None:
    """Write one JSON target with same-directory temporary + atomic replace."""
    target = os.path.abspath(os.fspath(path))
    directory = os.path.dirname(target) or os.getcwd()
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".s2patch_", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
