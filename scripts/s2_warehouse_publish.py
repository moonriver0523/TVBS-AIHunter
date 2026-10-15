# -*- coding: utf-8 -*-
"""Archive 唯讀母本 → 可增量發布的靜態分片；僅使用標準函式庫。"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import s2_warehouse as W
import s2_warehouse_editorial as E

FORMAT_VERSION = 1
MAX_SHARD_BYTES = 2_000_000
# Metadata is exactly the query projection. Only these explicit display/search
# additions are allowed; never serialize platform, fields, compiled or payload.
TEXT_FIELDS = ("id", "raw_entry")


def packed(value):
    return (W.encoded(value) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_changed(path, data):
    """Do not touch mtime for identical bytes; replace on the same filesystem."""
    path = Path(path)
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".publish-", delete=False) as f:
            name = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and Path(name).exists():
            Path(name).unlink()
    return True


def allowed_path(path):
    path = Path(path).resolve()
    if path.drive.upper() == "G:":
        raise ValueError("發布輸出不可位於 G:")
    return path


def split_rows(rows, max_bytes):
    """Account for UTF-8, JSON punctuation and envelope, not character count."""
    chunks, chunk, size = [], [], len(packed({"items": []}))
    for row in rows:
        row_size = len(W.encoded(row).encode("utf-8"))
        added = row_size + bool(chunk)
        if chunk and size + added > max_bytes:
            chunks.append(chunk)
            chunk, size = [], len(packed({"items": []}))
        size += row_size + bool(chunk)
        chunk.append(row)
    if chunk or not chunks:
        chunks.append(chunk)
    return chunks


def public_text(payload):
    return {key: str(payload.get(key) or "") for key in TEXT_FIELDS}


def export_archive(warehouse_root=W.DEFAULT_ROOT, max_bytes=MAX_SHARD_BYTES, rundown_dir=None):
    if max_bytes < 128:
        raise ValueError("分片上限至少 128 bytes")
    root = allowed_path(warehouse_root)
    archive = W.output_path(root, "archive")
    output = allowed_path(archive / "publish")
    if not output.is_relative_to(archive.resolve()):
        raise ValueError("publish 不可經由連結越出 archive")
    conn = W.connect_db(archive / "warehouse.sqlite")
    changed = 0
    files = []

    def emit(group, key, rows):
        nonlocal changed
        parts = []
        for i, chunk in enumerate(split_rows(rows, max_bytes)):
            suffix = "" if i == 0 else f".part{i+1:03}"
            relative = f"{group}/{key}{suffix}.json"
            target = allowed_path(output / relative)
            if not target.is_relative_to(output):
                raise ValueError("分片路徑越界")
            data = packed({"items": chunk})
            info = {"path": relative, "count": len(chunk), "bytes": len(data),
                    "sha256": digest(data), "oversized": len(data) > max_bytes}
            # One exceptionally large row remains intact and explicitly flagged.
            changed += write_changed(target, data)
            parts.append(info)
            files.append(info)
        return {"date": key, "count": len(rows), "parts": parts}

    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")  # one consistent SQLite read snapshot
        count = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        metadata = W.query(conn, include_notes=True, limit=count)["素材"]
        materials = {r["material_id"]: r for r in metadata}
        tags = defaultdict(lambda: {"T": [], "C": []})
        for r in conn.execute("SELECT material_id,axis,value FROM material_tags ORDER BY material_id,axis,value"):
            tags[r["material_id"]][r["axis"]].append(r["value"])
        days = defaultdict(list)
        payloads = {}
        for r in conn.execute("SELECT m.material_id,m.search_text,r.payload_json FROM materials m "
                              "JOIN material_revisions r ON r.revision_id=m.current_revision_id ORDER BY m.material_id"):
            mid = r["material_id"]
            payloads[mid] = json.loads(r["payload_json"])
            row = dict(materials[mid], **public_text(payloads[mid]),
                       tc=tags[mid], search_text=r["search_text"])
            days[row["material_date"] or "unknown"].append(row)
        day_entries = [emit("days", day, rows) for day, rows in sorted(days.items())]
        shifts = defaultdict(list)
        snapshots = defaultdict(set)
        observations = []
        for r in conn.execute("SELECT s.shift_date,o.* FROM material_observations o JOIN shifts s USING(shift_id) "
                              "ORDER BY s.shift_date,o.shift_id,o.ordinal,o.local_item_id"):
            payload = json.loads(r["payload_json"])
            observations.append((r["shift_date"], r["material_id"], payload))
            row = dict(materials[r["material_id"]], **public_text(payload))
            family, kind = W.source_class(payload)
            # Reconstruct the observed version's dates, tags and link, not current.
            dates = W.extract_dates(payload, r["shift_date"])
            for key in row.keys() & dates.keys():
                row[key] = dates[key]
            for raw_key, local_key in (("first_seen_at_utc", "first_seen_taipei"),
                                       ("material_at_utc", "material_at_taipei")):
                value = row[raw_key]
                row[local_key] = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(W.TAIPEI).isoformat() if value else None
            row.update(source_family=family, kind=kind, script_status=payload.get("script_status"),
                       shift_date=r["shift_date"], source_link=W.source_link(payload, family),
                       tc={axis: sorted(set((payload.get("tc") or {}).get(axis, []))) for axis in ("T", "C")},
                       observation={"shift_id": r["shift_id"], "ordinal": r["ordinal"], "revision_id": r["revision_id"]})
            shifts[r["shift_date"]].append(row)
            snapshots[r["shift_date"]].add(r["shift_id"])
        shift_entries = [dict(emit("shifts", day, rows), snapshot_count=len(snapshots[day]))
                         for day, rows in sorted(shifts.items())]
        bundles, editorial, references, resolver = E.derive(payloads, materials, observations)
        bundle_entries = [emit("bundles", day, bundles[day]) for day in sorted(shifts)]
        editorial_entries = [emit("editorial", day, rows) for day, rows in sorted(editorial.items())]
        reference_entries = [emit("references", key, rows) for key, rows in sorted(references.items())]
        inputs = allowed_path(rundown_dir) if rundown_dir else archive / "rundowns"
        rundown_entries = []
        for day in sorted(shifts):
            candidates, report = E.optional_rundown(inputs / (day + ".json"), resolver, payloads)
            rundown_entries.append(dict(emit("rundowns", day, candidates), mapping=report))
        supplement = json.loads((Path(__file__).parent / "s2_warehouse_inputs" / "supplement.json").read_text(encoding="utf-8"))
        config_entries = [emit("config", "supplement", [supplement])]
        content = {"format_version": FORMAT_VERSION, "dataset": "archive", "display_timezone": "Asia/Taipei",
                   "max_shard_bytes": max_bytes, "shifts": shift_entries, "days": day_entries,
                   "bundles": bundle_entries, "editorial": editorial_entries, "references": reference_entries,
                   "rundowns": rundown_entries, "config": config_entries,
                   "material_count": count, "observation_count": sum(e["count"] for e in shift_entries),
                   "default_end_date": max(shifts, default=None),
                   "vocabulary": {"sources": sorted({r["source_family"] for r in metadata}),
                                  **{axis: sorted({v for tc in tags.values() for v in tc[axis]}) for axis in ("T", "C")}},
                   "search_scope": "CLI query：ID、完整中文摘要、已存來源原文、category、needs_review；SQLite ASCII lower 子字串",
                   "notes": "跨日預設排除 note；unknown 分片只在勾選未知日期時載入。班次含全部 observation；多快照不合併。日期異常保留原值。"}
        generation = digest(packed(content))
        manifest_path = output / "manifest.json"
        old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        generated_at = old.get("generated_at") if old.get("generation") == generation else None
        manifest = dict(content, generation=generation,
                        generated_at=generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"))
        changed += write_changed(manifest_path, packed(manifest))  # publish pointer last
        return {"generation": generation, "changed_files": changed, "shard_count": len(files),
                "shard_bytes": sum(f["bytes"] for f in files), "manifest_bytes": manifest_path.stat().st_size,
                "oversized_shards": sum(f["oversized"] for f in files), "output": str(output)}
    finally:
        conn.close()


def build_demo(publish_dir, demo_dir):
    """Copy only the manifest's reachable shards; copy manifest last."""
    publish_dir, demo_dir = Path(publish_dir).resolve(), allowed_path(demo_dir)
    if demo_dir == publish_dir or demo_dir.is_relative_to(publish_dir) or publish_dir.is_relative_to(demo_dir):
        raise ValueError("demo 與 publish 不可相互包含")
    manifest = json.loads((publish_dir / "manifest.json").read_text(encoding="utf-8"))
    for group in ("shifts", "days", "bundles", "editorial", "references", "rundowns", "config"):
        for entry in manifest.get(group, []):
            for part in entry["parts"]:
                data = (publish_dir / part["path"]).read_bytes()
                if digest(data) != part["sha256"]:
                    raise ValueError("分片 hash 不符；請重新匯出")
                target = allowed_path(demo_dir / "data" / part["path"])
                if not target.is_relative_to(demo_dir):
                    raise ValueError("demo 分片路徑越界")
                write_changed(target, data)
    for source in (Path(__file__).parent / "s2_warehouse_web").iterdir():
        if source.is_file():
            write_changed(demo_dir / source.name, source.read_bytes())
    write_changed(demo_dir / "data" / "manifest.json", packed(manifest))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse-root", type=Path, default=Path(os.environ.get("S2_WAREHOUSE_ROOT", W.DEFAULT_ROOT)))
    parser.add_argument("--max-shard-bytes", type=int, default=MAX_SHARD_BYTES)
    parser.add_argument("--demo-dir", type=Path, help="同時建立本機 demo，例如 D:\\Downloads\\外電資料庫_線上demo")
    parser.add_argument("--rundown-dir", type=Path, help="可選人工候選稿單目錄，檔名 YYYY-MM-DD.json；預設 archive/rundowns")
    args = parser.parse_args()
    try:
        result = export_archive(args.warehouse_root, args.max_shard_bytes, args.rundown_dir)
        if args.demo_dir:
            build_demo(result["output"], args.demo_dir)
            result["demo"] = str(args.demo_dir)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, W.sqlite3.Error) as exc:
        parser.exit(1, f"發布失敗：{exc}\n")


if __name__ == "__main__":
    main()
