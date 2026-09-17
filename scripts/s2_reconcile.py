#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 五站統一清單對帳核心模組 (s2-reconcile/v1)。

定義五站對帳 schema、狀態常量、標準化 record 建構與狀態檔讀寫。
"""

from __future__ import annotations

import datetime
from typing import Any

SITE_ORDER = ("RT", "AP", "NS", "ENEX", "ABC")
RECONCILE_SCHEMA = "s2-reconcile/v1"

STATUS_OK = "ok"
STATUS_NEEDS_REVIEW = "needs-review"
STATUS_NOT_SCHEDULED = "not-scheduled"
STATUS_MISSING_EVIDENCE = "missing-evidence"

ALLOWED_STATUSES = frozenset({
    STATUS_OK,
    STATUS_NEEDS_REVIEW,
    STATUS_NOT_SCHEDULED,
    STATUS_MISSING_EVIDENCE,
})


def make_record(
    source: str,
    status: str,
    *,
    evidence_path: str | None = None,
    list_count: int | None = None,
    got_count: int | None = None,
    missing: int | None = None,
    missing_ids: list[str] | None = None,
    reason_code: str | None = None,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """建立符合 s2-reconcile/v1 規格的單站對帳紀錄。"""
    src = (source or "").strip().upper()
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"不合法的對帳狀態：{status}，必須在 {sorted(ALLOWED_STATUSES)} 之中")

    rec: dict[str, Any] = {
        "status": status,
        "source": src,
        "evidence_path": str(evidence_path) if evidence_path else None,
        "list": list_count,
        "got": got_count,
        "missing": missing,
        "missing_ids": list(missing_ids or []),
        "ts": ts or datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
    if reason_code:
        rec["reason_code"] = reason_code
    if reason:
        rec["reason"] = reason
    if extra:
        rec.update(extra)
    return rec


def is_v1_reconcile_log(log_entry: Any) -> bool:
    """判斷該輪之 reconcile_log 是否為 v1 五站統一格式。"""
    return isinstance(log_entry, dict) and log_entry.get("_schema") == RECONCILE_SCHEMA
