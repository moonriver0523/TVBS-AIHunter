# -*- coding: utf-8 -*-
"""Phase 0 唯讀副本匯入器；不接掃帶、render、Drive 或網路。

契約版本固定，未辨認格式留原文與問題，不以全文第一個日期猜主日。
用法與支援格式見 s2_warehouse.md。只依賴 Python 標準函式庫及純 schema。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from s2_material_schema import (
    canonicalize_id_for_lookup, classify_source_for_read,
    SCHEDULED_YOUTUBE_ID_RE, YOUTUBE_VIDEO_ID_RE,
)

SCHEMA_VERSION = 1
EXTRACTOR_VERSION = "s2-warehouse-1.0.0"
LINK_VERSION = 1
DEFAULT_ROOT = Path(r"D:\S2-外電資料庫")
INPUT_ROOT = Path(
    r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User"
    r"\d1d86ff2-4b80-4fa3-8af1-54cda62be154\scratchpad\s2data"
)
SNAPSHOT_PATH = INPUT_ROOT / "0930-s2-state.json"
TXT_PATH = INPUT_ROOT / "0930晚班交接.txt"
TAIPEI = ZoneInfo("Asia/Taipei")
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
TIME_COLUMNS = (
    "source_published_at_utc", "source_transmitted_at_utc", "source_updated_at_utc",
    "source_created_at_utc", "source_arrived_at_utc", "recorded_at_utc",
)
MONTHS = {name.lower(): n for n, name in enumerate((
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"), 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
MONTH_RE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
DATE_RE = re.compile(
    rf"\b(?:\d{{1,2}}\s+{MONTH_RE}\s+\d{{4}}|{MONTH_RE}\s+\d{{1,2}},?\s+\d{{4}})\b",
    re.I,
)
HISTORICAL_RE = re.compile(r"\b(?:ARCHIVE|FILE|B[ -]?ROLL|HISTORICAL)\b", re.I)

DDL = """
CREATE TABLE warehouse_meta (schema_version INTEGER NOT NULL, extractor_version TEXT NOT NULL);
CREATE TABLE shifts (shift_id TEXT PRIMARY KEY, shift_date TEXT NOT NULL,
    window_start TEXT, checkpoint TEXT, payload_json TEXT NOT NULL);
CREATE TABLE ingest_receipts (snapshot_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,
    extractor_version TEXT NOT NULL, status TEXT NOT NULL, receipt_json TEXT NOT NULL,
    snapshot_bytes BLOB NOT NULL);
CREATE TABLE materials (
    material_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, identity_status TEXT NOT NULL,
    provider TEXT, publisher TEXT, source_family TEXT NOT NULL, kind TEXT NOT NULL,
    source_keys TEXT NOT NULL, material_date TEXT, material_date_range TEXT NOT NULL,
    material_at_utc TEXT, material_date_basis TEXT NOT NULL, date_quality TEXT NOT NULL,
    date_confidence TEXT NOT NULL, date_issues TEXT NOT NULL, content_dates TEXT NOT NULL,
    first_seen_at_utc TEXT, first_seen_precision TEXT NOT NULL,
    source_published_at_utc TEXT, source_transmitted_at_utc TEXT, source_updated_at_utc TEXT,
    source_created_at_utc TEXT, source_arrived_at_utc TEXT, recorded_at_utc TEXT,
    time_evidence TEXT NOT NULL, source_link TEXT NOT NULL, link_missing_reason TEXT,
    current_revision_id TEXT NOT NULL, visibility_status TEXT NOT NULL,
    script_status TEXT, search_text TEXT NOT NULL
);
CREATE TABLE material_revisions (
    revision_id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES materials(material_id),
    previous_revision_id TEXT, source_version TEXT, source_content_sha256 TEXT NOT NULL,
    editorial_sha256 TEXT NOT NULL, metadata_sha256 TEXT NOT NULL, revision_kind TEXT NOT NULL,
    source_updated_at_utc TEXT, observed_at_utc TEXT, payload_json TEXT NOT NULL
);
CREATE TABLE material_observations (
    snapshot_id TEXT NOT NULL REFERENCES ingest_receipts(snapshot_id), local_item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL, material_id TEXT NOT NULL REFERENCES materials(material_id),
    revision_id TEXT NOT NULL REFERENCES material_revisions(revision_id),
    shift_id TEXT NOT NULL REFERENCES shifts(shift_id),
    first_seen_checkpoint TEXT, first_seen_run_id TEXT, last_checked_checkpoint TEXT,
    last_checked_run_id TEXT, candidate_checkpoint TEXT, entry_updated_ts TEXT,
    payload_json TEXT NOT NULL, PRIMARY KEY(snapshot_id, local_item_id, ordinal)
);
CREATE TABLE identity_aliases (
    namespace TEXT NOT NULL, alias_key TEXT NOT NULL, material_id TEXT NOT NULL REFERENCES materials,
    evidence_json TEXT NOT NULL, status TEXT NOT NULL, PRIMARY KEY(namespace, alias_key)
);
CREATE TABLE material_tags (
    material_id TEXT NOT NULL REFERENCES materials, axis TEXT NOT NULL CHECK(axis IN ('T','C')),
    value TEXT NOT NULL, vocabulary_revision TEXT, origin TEXT NOT NULL,
    PRIMARY KEY(material_id, axis, value)
);
CREATE TABLE candidate_dispositions (
    snapshot_id TEXT NOT NULL REFERENCES ingest_receipts, ordinal INTEGER NOT NULL,
    local_item_id TEXT NOT NULL, quality TEXT NOT NULL, disposition TEXT NOT NULL,
    reason_text TEXT, retained_material_id TEXT, retained_revision_id TEXT,
    policy_version TEXT NOT NULL, PRIMARY KEY(snapshot_id, ordinal)
);
CREATE INDEX material_date_idx ON materials(material_date, material_id);
CREATE INDEX source_date_idx ON materials(source_family, material_date);
CREATE INDEX tag_idx ON material_tags(axis, value, material_id);
CREATE INDEX shift_idx ON material_observations(shift_id, material_id);
"""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value).encode("utf-8")).hexdigest()


def utc_text(dt):
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(raw, tz_name=None):
    """已帶 offset 的值直接換算；無 offset 時須有來源時區契約。"""
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        return dt
    if not tz_name:
        raise ValueError("來源時區未知")
    zone = {"UTC": UTC, "Asia/Taipei": TAIPEI, "America/New_York": ET}[tz_name]
    first, second = dt.replace(tzinfo=zone, fold=0), dt.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError("夏令時間切換的模糊或不存在時刻，需明確 offset")
    return first


def url_encode(value):
    """以 UTF-8 位元組編碼 URL 參數；不把短碼當永久 GUID。"""
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(chr(b) if b in safe else f"%{b:02X}" for b in str(value).encode("utf-8"))


def source_class(item):
    result = classify_source_for_read(item["id"], item.get("source"))
    family = result.family
    if family == "SIDE":
        family = "SIDE_" + item["id"].split()[0]
    return family, "note" if item.get("script_status") == "note" else result.kind


def canonical_identity(item, shift_date):
    local_id = canonicalize_id_for_lookup(item["id"])
    match = SCHEDULED_YOUTUBE_ID_RE.fullmatch(local_id)
    if match:
        return local_id, "strong", [{"namespace": "youtube.video_id", "value": match["video_id"]}]
    if local_id.startswith("YT:") and YOUTUBE_VIDEO_ID_RE.fullmatch(local_id[3:]):
        return local_id, "strong", [{"namespace": "youtube.video_id", "value": local_id[3:]}]
    family, _ = source_class(item)
    # Phase 0 不升格 AP Edit No、ENEX newslinkId、ABC detailId 的永久身份。
    return f"legacy:{shift_date}:{family}:{url_encode(local_id)}", "provisional", [
        {"namespace": "shift.local_id", "value": local_id, "shift_date": shift_date}]


def source_link(item, family):
    platform = item.get("platform") or {}
    result = {"url": None, "kind": "unavailable", "basis": None,
              "generated_by": "s2_warehouse", "template_version": LINK_VERSION,
              "missing_reason": "尚無經驗證的來源頁面路由"}
    mid = canonicalize_id_for_lookup(item["id"])
    match = SCHEDULED_YOUTUBE_ID_RE.fullmatch(mid)
    video = match["video_id"] if match else mid[3:] if mid.startswith("YT:") else platform.get("video_id")
    if family in ("YNA", "CNA", "OTH", "YT") and video and YOUTUBE_VIDEO_ID_RE.fullmatch(video):
        url, kind, basis = f"https://www.youtube.com/watch?v={video}", "permalink", "youtube.video_id"
    elif family == "RT" and re.fullmatch(r"urn:newsml:reuters\.com:[A-Za-z0-9:._-]+", str(platform.get("guid", ""))):
        url = f"https://www.reutersconnect.com/all?id={url_encode(platform['guid'])}&media-types=vid"
        kind, basis = "permalink", "reuters.guid"
    elif family == "AP" and re.fullmatch(r"AP\d{7}", mid):
        url = f"https://newsroom.ap.org/home/search?query={mid[2:]}&mediaType=video"
        kind, basis = "search", "ap.EditNo"
    elif family == "NS" and re.fullmatch(
            r"https://(?:www\.)?newsource\.cnn\.com/[^\s?#]+", str(platform.get("url", ""))):
        url, kind, basis = platform["url"], "source_page", "platform.url"
    else:
        reasons = {"RT": "缺少可驗證的 Reuters GUID，短 Edit No 無法生成永久連結",
                   "AP": "AP 異型 ID 尚無 Edit No 映射契約",
                   "NS": "缺少經白名單驗證的 Newsource 原生頁面 URL",
                   "YNA": "缺少有效的 11 字元 video ID", "CNA": "缺少有效的 11 字元 video ID"}
        result["missing_reason"] = reasons.get(family, result["missing_reason"])
        return result
    result.update(url=url, kind=kind, basis=basis, missing_reason=None)
    return result


def checkpoint_time(value, shift_date):
    """年份由完整班次錨定；只接受相鄰三日內的正式 checkpoint。"""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{4}", value):
        return None
    anchor = date.fromisoformat(shift_date)
    possible = []
    for year in (anchor.year - 1, anchor.year, anchor.year + 1):
        try:
            dt = datetime.strptime(f"{year}{value}", "%Y%m%d-%H%M").replace(tzinfo=TAIPEI)
            if abs((dt.date() - anchor).days) <= 3:
                possible.append(dt)
        except ValueError:
            continue
    return possible[0] if len(possible) == 1 else None


def parse_content_date(value):
    parts = re.sub(r"[,.]", "", value).split()
    if parts[0].isdigit():
        day, month, year = parts
    else:
        month, day, year = parts
    return date(int(year), MONTHS[month.lower()], int(day)).isoformat()


def evidence(raw, start, end, text, kind="unknown", eligible=False, reason=None):
    return {"kind": kind, "raw_value": raw, "date_start": start, "date_end": end,
            "source_timezone": None, "precision": "date", "evidence": text,
            "field": "src_text", "extractor_version": EXTRACTOR_VERSION,
            "main_candidate": eligible, "exclusion_reason": reason}


def embedded_dates(item, family, shift_date):
    """AP 主 shotlist 標頭、RT 地點行、NS 明示 Shot Date；正文日期僅封存。"""
    text = item.get("src_text") or ""
    results = []
    if family == "NS":
        # HTML 標籤僅用於辨認欄名；原始位置與原文仍完整保存。
        for m in re.finditer(r"Shot Date:\s*(?:</?[^>]+>\s*)*(\d{1,2}/\d{1,2}/\d{4})", text, re.I):
            raw = m[1]
            try:
                d = datetime.strptime(raw, "%m/%d/%Y").date().isoformat()
            except ValueError:
                d = None
            e = evidence(raw, d, d, m[0], "filmed", bool(d), None if d else "日期格式不合法")
            e.update(span=[m.start(), m.end()])
            results.append(e)
        return results
    if family not in ("AP", "RT"):
        return results
    if family == "AP":
        section = re.search(r"\bSHOTLIST:\s*", text, re.I)
        if not section:
            return results
        start = section.end()
        ending = re.search(r"\bSTORYLINE:", text[start:], re.I)
        end = start + ending.start() if ending else len(text)
    else:
        section = re.search(r"\bSHOWS:\s*", text, re.I)
        if not section:
            return results
        start = section.end()
        ending = re.search(r"^\s*(?:STORY|SCRIPT):", text[start:], re.I | re.M)
        end = start + ending.start() if ending else len(text)
    body = text[start:end]
    for m in DATE_RE.finditer(body):
        try:
            d = parse_content_date(m[0])
        except (ValueError, KeyError):
            d = None
        before = body[max(0, m.start()-190):m.start()]
        after = body[m.end():m.end()+100]
        header = before + m[0] + after
        if family == "AP":
            # 只認日期緊接「地點 - 日期 [可選畫面標記] 編號.」；一般敘事不符合。
            shape = bool(re.search(r"[–—-]\s*$", before) and re.match(
                r"\s*(?:\+\+[^+]+\+\+\s*)*\d+\.\s", after))
            # 來源標頭內有 ARCHIVE；避免前一段一般敘述的字詞污染新標頭。
            lead = re.split(r"[.!?]\s|[\r\n]", before)[-1]
        else:
            line = before.rsplit("\n", 1)[-1]
            shape = bool(re.search(r"[A-Z][A-Z ,.'–/-]+\(\s*$", line) and re.match(r"\s*\)", after))
            lead = line
        reason = None
        if not shape:
            reason = "尚未辨認的內嵌日期格式，不能確認主素材"
        elif HISTORICAL_RE.search(lead) or HISTORICAL_RE.search(after.split("\n", 1)[0].split("1.", 1)[0]):
            reason = "ARCHIVE／FILE／歷史 B-roll，不作主日期"
        elif d and int(d[:4]) < int(shift_date[:4]):
            reason = "歷年 shotlist 畫面，主素材地位待確認"
        elif "[TRUNCATED]" in text or "...[TRUNCATED]" in text:
            reason = "原稿截斷，無法完整判讀主素材區段"
        elif not d:
            reason = "日期格式不合法"
        e = evidence(m[0], d, d, header, "filmed" if shape else "unknown", shape and reason is None, reason)
        e.update(span=[start + m.start(), start + m.end()])
        results.append(e)
    return results


def source_times(item, family):
    """只讀有契約的欄位；建立、到站、傳送、發布不混用。"""
    platform = item.get("platform") or {}
    values = {key: None for key in TIME_COLUMNS}
    ev, issues = [], []
    scheduled = SCHEDULED_YOUTUBE_ID_RE.fullmatch(item["id"])
    if scheduled and platform.get("video_id") != scheduled["video_id"]:
        issues.append("YouTube 時間證據的 video ID 不一致或缺失，未採用發布時間")
        ev.append({"field": "platform", "raw_value": platform, "semantic": "identity_conflict",
                   "extractor_version": EXTRACTOR_VERSION})
        return values, ev, issues
    contracts = {
        "YNA": [("published_at_utc", "source_published_at_utc", "UTC")],
        "CNA": [("published_at_utc", "source_published_at_utc", "UTC")],
        "OTH": [("published_at_utc", "source_published_at_utc", "UTC")],
        "AP": [("published_at_utc", "source_published_at_utc", "UTC"),
               ("transmitted_at_utc", "source_transmitted_at_utc", "UTC"),
               ("arrivaldatetime", "source_arrived_at_utc", None),
               ("firstcreated", "source_created_at_utc", None)],
        "RT": [("published_at_utc", "source_published_at_utc", "UTC"),
               ("transmitted_at_utc", "source_transmitted_at_utc", "UTC"),
               ("created_at_utc", "source_created_at_utc", "UTC")],
        "NS": [("createdDate", "source_created_at_utc", "UTC")],
        "ENEX": [("sortDate", "source_published_at_utc", "epoch_ms"),
                 ("publishedDate", "source_published_at_utc", "epoch_ms")],
        "ABC": [("DeliveryAvailableDateTime", "source_transmitted_at_utc", "Asia/Taipei"),
                ("DeliveryCompletedDateTime", "source_arrived_at_utc", "Asia/Taipei")],
    }
    for key, column, tz_name in contracts.get(family, []):
        raw = platform.get(key, item.get(key))
        if raw is None or raw == "":
            continue
        record = {"field": key, "raw_value": raw, "semantic": column, "source_timezone": tz_name,
                  "extractor_version": EXTRACTOR_VERSION, "at_utc": None}
        try:
            if tz_name == "epoch_ms":
                dt = datetime.fromtimestamp(float(raw)/1000, UTC)
            else:
                dt = parse_timestamp(raw, tz_name)
            record["at_utc"] = utc_text(dt)
            if values[column] and values[column] != record["at_utc"]:
                issues.append("來源時間衝突：" + column)
                record["conflict"] = True
            else:
                values[column] = record["at_utc"]
        except (ValueError, TypeError, OverflowError, OSError):
            issues.append("來源時間格式或時區未確認：" + key)
        ev.append(record)
    # 無 offset 的編輯時間只能作本機推定，不能當來源或首次入庫時間。
    if item.get("entry_updated_ts"):
        ev.append({"field": "entry_updated_ts", "raw_value": item["entry_updated_ts"],
                   "semantic": "local_editorial_update", "timezone_quality": "本機推定",
                   "extractor_version": EXTRACTOR_VERSION})
    return values, ev, issues


def extract_dates(item, shift_date):
    family, kind = source_class(item)
    first = checkpoint_time(item.get("first_seen_checkpoint"), shift_date)
    values, time_ev, issues = source_times(item, family)
    content = embedded_dates(item, family, shift_date)
    result = dict(values, material_date=None, material_date_range=None, material_at_utc=None,
                  material_date_basis="unknown", date_quality="unknown", date_confidence="unknown",
                  first_seen_at_utc=utc_text(first) if first else None,
                  first_seen_precision="checkpoint_anchor" if first else "unknown",
                  content_dates=content, time_evidence=time_ev, date_issues=issues)
    if kind == "note":
        result["date_issues"].append("歷史 note 非可用內容；無結構化候選處置證據")
        return result
    candidates = sorted({e["date_start"] for e in content if e["main_candidate"]})
    if candidates:
        result.update(material_date=candidates[0], material_date_basis="source_content_date",
                      date_quality="ambiguous" if len(candidates) > 1 else "embedded_verified",
                      date_confidence="medium" if len(candidates) > 1 else "high",
                      material_date_range=[candidates[0], candidates[-1]] if len(candidates) > 1 else None)
        if len(candidates) > 1:
            issues.append("多個同等主日期：依 D-候選1 暫列最早日，完整候選保留")
    elif family.startswith("SIDE_"):
        m = re.fullmatch(r"(?:CNN|NHK) (\d{2})-(\d{2}) (\d{2})(\d{2})(\d{2})", item["id"])
        if m:
            anchor = checkpoint_time(m[1]+m[2]+"-"+m[3]+m[4], shift_date)
            if anchor and int(m[5]) <= 59:
                anchor = anchor.replace(second=int(m[5]))
                result.update(material_date=anchor.date().isoformat(), material_at_utc=utc_text(anchor),
                              recorded_at_utc=utc_text(anchor), material_date_basis="recording_start",
                              date_quality="inferred_recording", date_confidence="medium")
                time_ev.append({"field": "id", "raw_value": item["id"], "at_utc": utc_text(anchor),
                                "semantic": "recording_start", "source_timezone": "Asia/Taipei",
                                "extractor_version": EXTRACTOR_VERSION})
                issues.append("側錄年份由班次推定，尚無母帶收據交叉驗證")
    if result["material_date"] is None:
        precedence = [("source_published_at_utc", "source_published", "structured_source"),
                      ("source_transmitted_at_utc", "source_transmitted", "structured_source"),
                      ("source_arrived_at_utc", "source_arrival_fallback", "inferred"),
                      ("source_created_at_utc", "source_created_fallback", "inferred")]
        for column, basis, quality in precedence:
            if values[column] and not any("衝突" in issue for issue in issues):
                dt = datetime.fromisoformat(values[column].replace("Z", "+00:00"))
                result.update(material_date=dt.astimezone(TAIPEI).date().isoformat(),
                              material_at_utc=values[column], material_date_basis=basis,
                              date_quality=quality, date_confidence="high" if quality == "structured_source" else "medium")
                time_ev.append({"semantic": "material_date", "from_field": column,
                                "extractor_version": EXTRACTOR_VERSION})
                break
    if result["material_date"] is None and first:
        result.update(material_date=first.date().isoformat(), material_date_basis="ingestion_fallback",
                      date_quality="ingestion_fallback", date_confidence="low")
        issues.append("依入庫日暫列；未取得已確認來源主日期／時間")
    if not first:
        issues.append("缺少可靠正式首次入庫 checkpoint；未採候選輪或編輯時間")
    if any(not e["main_candidate"] for e in content):
        issues.append("部分內嵌日期僅保留證據，未採為主日期")
    for entry in time_ev:
        if entry.get("at_utc"):
            day = datetime.fromisoformat(entry["at_utc"].replace("Z", "+00:00")).astimezone(TAIPEI).date().isoformat()
            content.append({"kind": "published" if entry["semantic"] == "source_published_at_utc" else "filmed" if entry["semantic"] == "recording_start" else "unknown",
                            "raw_value": entry["raw_value"], "date_start": day, "date_end": day,
                            "source_timezone": entry.get("source_timezone"), "precision": "second",
                            "field": entry["field"], "evidence": entry,
                            "extractor_version": EXTRACTOR_VERSION, "main_candidate": False,
                            "exclusion_reason": "來源時間另依優先序採用，非 shotlist 主日期"})
    return result


def connect_db(path, writable=False):
    if writable:
        conn = sqlite3.connect(path, timeout=30)
    else:
        conn = sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if writable and not conn.execute("SELECT name FROM sqlite_master WHERE name='warehouse_meta'").fetchone():
        # 只對空 DB 初始化，不能在別人的既有資料庫中混建 schema。
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
            conn.close()
            raise ValueError("輸出資料庫非空且不是外電庫 schema v1")
        conn.executescript(DDL)
        conn.execute("INSERT INTO warehouse_meta VALUES (?,?)", (SCHEMA_VERSION, EXTRACTOR_VERSION))
        conn.commit()
    meta = conn.execute("SELECT * FROM warehouse_meta").fetchone()
    if not meta or meta["schema_version"] != SCHEMA_VERSION or meta["extractor_version"] != EXTRACTOR_VERSION:
        conn.close()
        raise ValueError("schema／extractor 版本不符；需使用相同版本或另建輸出庫")
    return conn


def counts(conn):
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "materials", "material_revisions", "material_observations", "ingest_receipts", "material_tags", "candidate_dispositions")}


def txt_crosscheck(raw, state):
    if raw is None:
        return {"quality": "unknown", "reason": "缺少對應 txt，無法證實完成交接"}
    text = raw.decode("utf-8-sig")
    header = text.splitlines()[2] if len(text.splitlines()) > 2 else ""
    normal = sum(i.get("script_status") != "note" and not source_class(i)[0].startswith("SIDE_") for i in state["items"])
    m = re.search(r"收錄外電共(\d+)則.*?AP (\d+)則／RT (\d+)則／NS (\d+)則／其他 (\d+)則.*?側錄 (\d+)則", header)
    result = {"sha256": sha(raw), "last_render_sha_matches": sha(raw) == state.get("last_render_sha"),
              "state_general_content": normal, "header_raw": header, "quality": "provisional",
              "coverage": "只證明已觀測庫存；缺候選收據，不能推論來源全覆蓋"}
    if m:
        result["header_counts"] = dict(zip(("general", "AP", "RT", "NS", "other", "side_display_groups"), map(int, m.groups())))
        result["general_count_matches"] = int(m[1]) == normal
        result["issues"] = ["txt 的 NS=301／其他=200 含 R51 誤歸；來源辨識結果 NS=296／其他=205",
                            "側錄顯示群組不等同資料庫段數；未重建 renderer 完成證據"]
    return result


def import_bytes(snapshot_bytes, output_dir, txt_bytes=None, source_name="0930-s2-state.json"):
    """單一交易 writer；測試可用記憶體快照，CLI 僅接受固定唯讀副本。"""
    state = json.loads(snapshot_bytes.decode("utf-8-sig"))
    if not isinstance(state, dict) or not isinstance(state.get("items"), list):
        raise ValueError("快照須含 items 陣列；不接受字典轉換而吞掉同碼紀錄")
    if "schema_version" in state and state["schema_version"] != SCHEMA_VERSION:
        raise ValueError("輸入宣告的 schema 版本不支援，未寫入資料庫")
    shift_date = date.fromisoformat(str(state.get("window_start", ""))[:10]).isoformat()
    snapshot_id = sha(snapshot_bytes)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = connect_db(output_dir / "warehouse.sqlite", writable=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        before = counts(conn)
        old = conn.execute("SELECT receipt_json FROM ingest_receipts WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if old:
            receipt = json.loads(old[0])
            conn.rollback()
            write_json(output_dir / "receipts" / (snapshot_id+".json"), receipt)
            return {"snapshot_id": snapshot_id, "重複匯入": True, "新增": {k: 0 for k in before}, "總數": before}
        if before["ingest_receipts"]:
            raise ValueError("Phase 0 僅驗證單一快照；多班匯入留待 Phase 1，請另建輸出庫")
        started = utc_text(datetime.now(UTC))
        receipt = {"snapshot_id": snapshot_id, "source_relative_path": source_name,
                   "source_bytes": len(snapshot_bytes), "schema_version": SCHEMA_VERSION,
                   "extractor_version": EXTRACTOR_VERSION, "adapter_version": EXTRACTOR_VERSION,
                   "started_at_utc": started, "status": "complete", "issues": [],
                   "registry_snapshot_id": None, "history_completeness": "final_snapshot_only",
                   "source_schema": state.get("schema_version", "legacy_no_version"),
                   "producer_completion_status": "unknown", "txt_crosscheck": txt_crosscheck(txt_bytes, state)}
        conn.execute("INSERT INTO ingest_receipts VALUES (?,?,?,?,?,?)",
                     (snapshot_id, SCHEMA_VERSION, EXTRACTOR_VERSION, "complete", encoded(receipt), snapshot_bytes))
        shift_id = "s2:"+shift_date
        conn.execute("INSERT INTO shifts VALUES (?,?,?,?,?)", (shift_id, shift_date, state.get("window_start"),
                     state.get("checkpoint"), encoded({k:v for k,v in state.items() if k != "items"})))
        quarantine = []
        for ordinal, item in enumerate(state["items"]):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
                quarantine.append({"ordinal": ordinal, "reason": "缺有效 local ID", "raw": item})
                continue
            family, kind = source_class(item)
            mid, identity, keys = canonical_identity(item, shift_date)
            if conn.execute("SELECT 1 FROM materials WHERE material_id=?", (mid,)).fetchone():
                # 保住同碼原始列；不靜默合併，送隔離等待判讀。
                quarantine.append({"ordinal": ordinal, "local_item_id": item["id"], "reason": "同碼多筆，隔離保留"})
                mid, identity = mid+f":ordinal:{ordinal}", "provisional_conflict"
            dates = extract_dates(item, shift_date)
            link = source_link(item, family)
            revision_id = "rev:"+sha({"material_id": mid, "payload": item})
            material = dict(material_id=mid, schema_version=SCHEMA_VERSION, identity_status=identity,
                            provider=(item.get("platform") or {}).get("provider", family), publisher=family,
                            source_family=family, kind=kind, source_keys=keys, **dates, source_link=link,
                            link_missing_reason=link["missing_reason"], current_revision_id=revision_id,
                            visibility_status="unavailable" if kind == "note" else "observed",
                            script_status=item.get("script_status"), search_text="\n".join(
                                str(item.get(k) or "") for k in ("id", "raw_entry", "src_text", "category", "needs_review")))
            params = {k: encoded(v) if isinstance(v, (dict, list)) or k == "material_date_range" else v
                      for k,v in material.items()}
            columns = list(params)
            conn.execute(f"INSERT INTO materials ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                         [params[k] for k in columns])
            conn.execute("INSERT INTO material_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (revision_id, mid, None, None, sha(item.get("src_text")),
                          sha({k:item.get(k) for k in ("raw_entry", "fields", "script_status")}),
                          sha({k:item.get(k) for k in ("category", "tc", "platform", "needs_review")}),
                          "initial_snapshot", dates["source_updated_at_utc"],
                          utc_text(parse_timestamp(state["updated_at"])) if state.get("updated_at") else None, encoded(item)))
            p = item.get("platform") or {}
            conn.execute("INSERT INTO material_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (snapshot_id, item["id"], ordinal, mid, revision_id, shift_id,
                          item.get("first_seen_checkpoint"), item.get("first_seen_run_id"),
                          item.get("last_checked_checkpoint"), item.get("last_checked_run_id"),
                          p.get("candidate_checkpoint"), item.get("entry_updated_ts"), encoded(item)))
            conn.execute("INSERT INTO identity_aliases VALUES (?,?,?,?,?)", (
                shift_id, item["id"]+f":ordinal:{ordinal}", mid,
                encoded({"snapshot_id": snapshot_id, "ordinal": ordinal}), "provisional" if identity != "strong" else "verified"))
            tc = item.get("tc") or {}
            for axis in ("T", "C"):
                for value in tc.get(axis, []):
                    conn.execute("INSERT OR IGNORE INTO material_tags VALUES (?,?,?,?,?)", (mid, axis, value, None, "stored"))
            if kind == "note":
                conn.execute("INSERT INTO candidate_dispositions VALUES (?,?,?,?,?,?,?,?,?)", (
                    snapshot_id, ordinal, item["id"], "legacy_unresolved", "unresolved",
                    item.get("needs_review"), None, None, EXTRACTOR_VERSION))
        receipt.update(status="partial" if quarantine else "complete", quarantine=quarantine,
                       counts=counts(conn), completed_at_utc=utc_text(datetime.now(UTC)))
        receipt["counts"].update(input_records=len(state["items"]),
                                content_records=conn.execute("SELECT COUNT(*) FROM materials WHERE kind!='note'").fetchone()[0],
                                note_records=conn.execute("SELECT COUNT(*) FROM materials WHERE kind='note'").fetchone()[0])
        conn.execute("UPDATE ingest_receipts SET status=?, receipt_json=? WHERE snapshot_id=?",
                     (receipt["status"], encoded(receipt), snapshot_id))
        conn.commit()
        write_json(output_dir / "receipts" / (snapshot_id+".json"), receipt)
        after = counts(conn)
        return {"snapshot_id": snapshot_id, "狀態": receipt["status"], "重複匯入": False,
                "新增": {k: after[k]-before[k] for k in before}, "總數": after,
                "內容筆數": receipt["counts"]["content_records"], "備註筆數": receipt["counts"]["note_records"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # 收據可從 DB 重建；以同目錄暫存檔替換避免半份 JSON。
    temp = path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    temp.replace(path)


def query(conn, date_start=None, date_end=None, source=None, keyword=None, t=None, c=None,
          include_notes=False, overlap=False, limit=100, offset=0):
    conditions, params = [], []
    if not include_notes:
        conditions.append("m.kind!='note'")
    for value in (date_start, date_end):
        if value:
            date.fromisoformat(value)
    if date_start and date_end and date_start > date_end:
        raise ValueError("日期起點不能晚於終點")
    for value, operator, bound in ((date_start, ">=", "$[1]"), (date_end, "<=", "$[0]")):
        if value:
            field = f"COALESCE(json_extract(m.material_date_range, '{bound}'), m.material_date)" if overlap else "m.material_date"
            conditions.append(f"{field}{operator}?")
            params.append(value)
    if source:
        conditions.append("m.source_family=?")
        params.append(source.upper())
    if keyword:
        conditions.append("instr(lower(m.search_text),lower(?))>0")
        params.append(keyword)
    for axis, value in (("T", t), ("C", c)):
        if value:
            conditions.append("EXISTS (SELECT 1 FROM material_tags g WHERE g.material_id=m.material_id AND g.axis=? AND g.value=?)")
            params.extend((axis, value))
    where = " AND ".join(conditions) or "1=1"
    total = conn.execute("SELECT COUNT(*) FROM materials m WHERE "+where, params).fetchone()[0]
    rows = conn.execute("SELECT material_id,source_family,kind,material_date,material_date_range,material_date_basis,"
                        "material_at_utc,source_published_at_utc,source_transmitted_at_utc,source_updated_at_utc,"
                        "source_created_at_utc,source_arrived_at_utc,recorded_at_utc,"
                        "(SELECT s.shift_date FROM material_observations o JOIN shifts s USING(shift_id) WHERE o.material_id=m.material_id LIMIT 1) AS shift_date,"
                        "date_quality,date_confidence,first_seen_at_utc,first_seen_precision,source_link,script_status "
                        "FROM materials m WHERE "+where+" ORDER BY material_date,material_id LIMIT ? OFFSET ?",
                        params+[limit, offset]).fetchall()
    items = []
    for row in rows:
        value = dict(row)
        value["material_date_range"] = json.loads(value["material_date_range"])
        value["source_link"] = json.loads(value["source_link"])
        first = value["first_seen_at_utc"]
        value["first_seen_taipei"] = datetime.fromisoformat(first.replace("Z", "+00:00")).astimezone(TAIPEI).isoformat() if first else None
        material_at = value["material_at_utc"]
        value["material_at_taipei"] = datetime.fromisoformat(material_at.replace("Z", "+00:00")).astimezone(TAIPEI).isoformat() if material_at else None
        items.append(value)
    return {"總筆數": total, "本頁筆數": len(items), "offset": offset, "下一頁": offset+len(items) if offset+len(items)<total else None,
            "display_timezone": "Asia/Taipei", "素材": items}


def report(output_dir):
    output_dir = Path(output_dir)
    conn = connect_db(output_dir / "warehouse.sqlite")
    try:
        groups = [dict(r) for r in conn.execute(
            "SELECT source_family,kind,date_quality,material_date_basis,COUNT(*) AS count FROM materials "
            "GROUP BY source_family,kind,date_quality,material_date_basis ORDER BY source_family,date_quality,material_date_basis")]
        columns = "material_id,source_family,material_date,material_date_range,material_date_basis,date_quality,date_issues,content_dates"
        def rows(where):
            result = []
            for r in conn.execute("SELECT "+columns+" FROM materials WHERE "+where+" ORDER BY material_id"):
                v = dict(r)
                for k in ("material_date_range", "date_issues", "content_dates"):
                    v[k] = json.loads(v[k])
                result.append(v)
            return result
        receipts = [json.loads(r[0]) for r in conn.execute("SELECT receipt_json FROM ingest_receipts")]
        quality = {"schema_version": SCHEMA_VERSION, "extractor_version": EXTRACTOR_VERSION,
                   "來源與日期品質": groups, "同等主日期待重判": rows("date_quality='ambiguous'"),
                   "退路與未知": rows("date_quality IN ('ingestion_fallback','unknown') OR material_date_basis LIKE '%fallback'"),
                   "限制": "日期品質與匯入完成分開；note 非可用素材，側錄段數非顯示則數；無候選清單，A7 全站覆蓋未知"}
        reports = output_dir / "reports"
        write_json(reports / "date-quality.json", quality)
        lines = ["# Phase 0 日期品質報告", "", f"Schema {SCHEMA_VERSION}；擷取器 `{EXTRACTOR_VERSION}`。",
                 "", quality["限制"], "", "| 來源 | 類型 | 日期品質 | 日期依據 | 筆數 |", "|---|---|---|---|---:|"]
        for g in groups:
            lines.append(f"| {g['source_family']} | {g['kind']} | {g['date_quality']} | {g['material_date_basis']} | {g['count']} |")
        lines.extend(["", "## 同等主日期待重判", "", "最早日只是索引；完整候選與證據存於 JSON。", ""])
        for r in quality["同等主日期待重判"]:
            lines.append(f"- `{r['material_id']}`：{r['material_date_range']}；暫列 {r['material_date']}")
        lines.extend(["", "## 退路與未知", ""])
        for r in quality["退路與未知"]:
            lines.append(f"- `{r['material_id']}`：{r['material_date']}／{r['material_date_basis']}；"+"；".join(r["date_issues"]))
        (reports / "date-quality.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
        measured = {"資料表筆數": counts(conn), "內容": conn.execute("SELECT COUNT(*) FROM materials WHERE kind!='note'").fetchone()[0],
                    "備註": conn.execute("SELECT COUNT(*) FROM materials WHERE kind='note'").fetchone()[0],
                    "來源內容筆數": {r[0]:r[1] for r in conn.execute("SELECT source_family,COUNT(*) FROM materials WHERE kind!='note' GROUP BY source_family")},
                    "日期內容筆數": {r[0]:r[1] for r in conn.execute("SELECT material_date,COUNT(*) FROM materials WHERE kind!='note' GROUP BY material_date")},
                    "YNA範例": query(conn, keyword="YNA-buGW2sCr_do"),
                    "新制ID筆數": conn.execute("SELECT COUNT(*) FROM materials WHERE identity_status='strong' AND source_family IN ('YNA','CNA')").fetchone()[0],
                    "digit-leading影片": query(conn, keyword="", limit=2000)["素材"],
                    "匯入收據": receipts}
        edge_ids = {"YNA-7blpZHaLwik", "YNA-5vlRwHvWwkQ", "CNA-3SIb5qK0cqk", "YNA-8GnWofrZ_uQ", "YNA-5EFB8BHM0EE"}
        measured["digit-leading影片"] = [r for r in measured["digit-leading影片"] if r["material_id"] in edge_ids]
        write_json(reports / "phase0-measurements.json", measured)
        (reports / "phase0-measurements.md").write_text(
            "# Phase 0 實測\n\n```json\n"+json.dumps({k:v for k,v in measured.items() if k != "匯入收據"}, ensure_ascii=False, indent=2)+"\n```\n", encoding="utf-8")
        return {"報告路徑": str(reports), "日期品質群組數": len(groups), "ambiguous筆數": len(quality["同等主日期待重判"]),
                "退路與未知筆數": len(quality["退路與未知"]), "實測": {k:v for k,v in measured.items() if k not in ("digit-leading影片", "匯入收據")}}
    finally:
        conn.close()


def output_path(root):
    root = Path(root).resolve()
    repo = Path(__file__).resolve().parent.parent
    # 工具參數護欄不是 OS 存取隔離；不允許 Drive、repo 或輸入副本成為輸出根。
    if root.drive.upper() == "G:" or any(root == p or p in root.parents or root in p.parents for p in (INPUT_ROOT.resolve(), repo)):
        raise ValueError("輸出根須在 Drive、git 與唯讀輸入副本之外")
    return root / "phase0"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Phase 0 外電唯讀副本匯入／查詢／日期品質報告")
    parser.add_argument("--warehouse-root", default=os.environ.get("S2_WAREHOUSE_ROOT", str(DEFAULT_ROOT)), help="外電庫根目錄；自動使用 phase0 子目錄")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="匯入指定 0930 副本，重複快照零新增")
    imp.add_argument("--snapshot", default=str(SNAPSHOT_PATH), help="僅允許指定的 0930 唯讀副本")
    imp.add_argument("--txt", default=str(TXT_PATH), help="僅允許指定的 0930 交接 txt 副本")
    q = sub.add_parser("query", help="按素材日、來源、關鍵字與 T/C 查詢")
    q.add_argument("--date", help="素材日 YYYY-MM-DD")
    q.add_argument("--from", dest="date_start", help="素材日起點 YYYY-MM-DD")
    q.add_argument("--to", dest="date_end", help="素材日終點 YYYY-MM-DD")
    q.add_argument("--source", help="來源，例如 AP／NS／SIDE_CNN")
    q.add_argument("--keyword", help="正文／中文摘要／ID 關鍵字")
    q.add_argument("--t", help="當時保存的 T 標籤")
    q.add_argument("--c", help="當時保存的 C 標籤")
    q.add_argument("--include-notes", action="store_true", help="另含 note 備註紀錄")
    q.add_argument("--overlap", action="store_true", help="日期範圍包含 ambiguous 候選區間相交")
    q.add_argument("--limit", type=int, default=100, help="每頁上限 1～2000")
    q.add_argument("--offset", type=int, default=0, help="接續查詢偏移")
    sub.add_parser("report", help="輸出 Markdown＋JSON 日期品質與實測報告")
    args = parser.parse_args(argv)
    try:
        out = output_path(args.warehouse_root)
        if args.command == "import":
            # 先檢查所有路徑，才讀任何檔案；絕不自動尋找 live 或 Archive。
            if Path(args.snapshot).resolve() != SNAPSHOT_PATH.resolve() or Path(args.txt).resolve() != TXT_PATH.resolve():
                raise ValueError("Phase 0 只能讀指定的 0930 state／txt 唯讀副本")
            raw = SNAPSHOT_PATH.read_bytes()
            txt = TXT_PATH.read_bytes()
            result = import_bytes(raw, out, txt)
            result.update(輸入sha256=sha(raw), txt_sha256=sha(txt), 輸出目錄=str(out))
        elif args.command == "report":
            result = report(out)
        else:
            if args.date and (args.date_start or args.date_end):
                raise ValueError("--date 與 --from／--to 請擇一使用")
            if not 1 <= args.limit <= 2000 or args.offset < 0:
                raise ValueError("limit 必須為 1～2000，offset 不得負數")
            conn = connect_db(out / "warehouse.sqlite")
            try:
                result = query(conn, args.date or args.date_start, args.date or args.date_end,
                               args.source, args.keyword, args.t, args.c, args.include_notes,
                               args.overlap, args.limit, args.offset)
            finally:
                conn.close()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("狀態") == "partial" else 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("外電庫操作失敗："+str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
