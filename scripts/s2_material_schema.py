# -*- coding: utf-8 -*-
"""S2 素材 ID／source／src_text／run context 共用純函式（scoped 1259）。

嚴格 writer 與 existing lookup 分離。本模組零 I/O、不讀狀態檔。
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

NS_ID_RE = re.compile(r"^[A-Z]{2,6}-\d{1,4}(?:MO|TU|WE|TH|FR|SA|SU)$")
NS_SHAPE_RE = re.compile(r"^[A-Z]{2,6}-\d{1,4}[A-Z]{2}$", re.IGNORECASE)
CHECKPOINT_RE = re.compile(r"^\d{4}-\d{4}$")
URL_ID_RE = re.compile(r"^(?:YNA|CNA|OTH)(?:0[1-9]|[1-9]\d)$")
UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

AP_ID_RE = re.compile(r"^AP\d{7}$")
AP_CCTV_RE = re.compile(r"^APcctv\d{6}$")
AP_CNS_RE = re.compile(r"^APcns\d{6}$")
RT_ID_RE = re.compile(r"^RT\d{4}$")
RTV_ID_RE = re.compile(r"^RTV\d{4}$", re.IGNORECASE)
ENEX_ID_RE = re.compile(r"^ENEX\d{4,8}$")
ABC_ID_RE = re.compile(r"^ABC\d{6,16}$")
SIDE_ID_RE = re.compile(r"^(?:CNN|NHK)(?: \d{2}-\d{2})? \d{6}$")
YT_ID_RE = re.compile(r"^YT:.+$")
YNA_ID_RE = re.compile(r"^YNA(?:0[1-9]|[1-9]\d)$")
CNA_ID_RE = re.compile(r"^CNA(?:0[1-9]|[1-9]\d)$")
OTH_ID_RE = re.compile(r"^OTH(?:0[1-9]|[1-9]\d)$")

STRUCTURAL_REQUIRED_FIELDS = ("id", "source", "checkpoint", "status", "entry")
SRC_TEXT_POLICY = {"NS": "blocking", "AP": "advisory", "RT": "advisory"}
GATED_FAMILIES = frozenset({"AP", "RT", "NS"})
CORE_SOURCES = frozenset({
    "NS", "AP", "RT", "ENEX", "ABC", "SIDE", "YT", "YNA", "CNA",
})
OTH_RESERVED = frozenset({"oth", "other", "?", "ns", "ap", "rt", "enex", "abc",
                          "side", "yt", "yna", "cna"})
OTH_ALIASES = {
    "twitter": "X",
    "instagram": "IG",
    "youtube": "YouTube",
}

EMPTY_HEADERS = {
    "NS": ("DESC", "SCRIPT"),
    "AP": ("HEAD", "SCRIPT"),
    "RT": ("HEAD", "STORY"),
}

UNSET = object()


@dataclass
class ValidationIssue:
    code: str
    severity: str
    owner: str
    site: Optional[str] = None
    id: Optional[str] = None
    material_uid: None = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "owner": self.owner,
            "site": self.site,
            "id": self.id,
            "material_uid": None,
            "message": self.message,
        }


@dataclass
class SourceClass:
    family: str
    kind: str
    display: str
    legacy_compat: bool = False
    diagnostic: Optional[str] = None


@dataclass
class RunContext:
    checkpoint: str
    run_id: str
    checkpoint_label: Optional[str] = None


@dataclass
class PreflightRow:
    index: int
    raw_id: str
    lookup_id: str
    id_family: Optional[str]
    incoming_source_family: Optional[str]
    existing_key: Optional[str]
    existing_item_family: Optional[str]


def is_uuid_v4(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(UUID_V4_RE.fullmatch(value))


def _trim(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_illegal_ns_shape(value: Any) -> bool:
    """Looks like NS CODE (any two-letter tail) but weekday suffix is not in the whitelist."""
    s = _trim(value)
    return bool(NS_SHAPE_RE.fullmatch(s) and not NS_ID_RE.fullmatch(s.upper()))


def detect_id_family(value: Any, *, lookup_alias: bool = True) -> Optional[str]:
    s = _trim(value)
    if not s:
        return None
    if AP_ID_RE.fullmatch(s) or AP_CCTV_RE.fullmatch(s) or AP_CNS_RE.fullmatch(s):
        return "AP"
    if RT_ID_RE.fullmatch(s):
        return "RT"
    if lookup_alias and RTV_ID_RE.fullmatch(s):
        return "RT"
    if NS_ID_RE.fullmatch(s.upper()):
        # detect without mutating; NS family if upper would match
        if NS_ID_RE.fullmatch(s) or NS_ID_RE.fullmatch(s.upper()):
            # only claim NS if the upper form is legal (week suffix)
            if NS_ID_RE.fullmatch(s.upper()):
                return "NS"
    if YNA_ID_RE.fullmatch(s.upper()):
        return "YNA"
    if CNA_ID_RE.fullmatch(s.upper()):
        return "CNA"
    if OTH_ID_RE.fullmatch(s.upper()):
        return "OTH"
    if YT_ID_RE.fullmatch(s):
        return "YT"
    if ENEX_ID_RE.fullmatch(s):
        return "ENEX"
    if ABC_ID_RE.fullmatch(s):
        return "ABC"
    if SIDE_ID_RE.fullmatch(s):
        return "SIDE"
    return None


def _ap_canonical(s: str) -> Optional[str]:
    if AP_ID_RE.fullmatch(s) or AP_CCTV_RE.fullmatch(s) or AP_CNS_RE.fullmatch(s):
        return s
    return None


def canonicalize_id_for_lookup(value: Any, existing_ids: Optional[Mapping] = None) -> str:
    """Locate an existing key. Does not declare the value as a legal new writer ID."""
    s = _trim(value)
    existing = existing_ids or {}
    if s in existing:
        return s
    ap = _ap_canonical(s)
    if ap is not None:
        return ap
    if s.startswith("YT:"):
        return s
    if ENEX_ID_RE.fullmatch(s) or ABC_ID_RE.fullmatch(s) or SIDE_ID_RE.fullmatch(s):
        return s
    if RTV_ID_RE.fullmatch(s):
        # RTV#### → RT####, keep digits
        digits = re.sub(r"(?i)^RTV", "", s)
        return "RT" + digits
    if RT_ID_RE.fullmatch(s):
        return s
    up = s.upper()
    if NS_ID_RE.fullmatch(up):
        return up
    if YNA_ID_RE.fullmatch(up) or CNA_ID_RE.fullmatch(up) or OTH_ID_RE.fullmatch(up):
        return up
    return s


def validate_material_id_for_write(value: Any, expected_family: str):
    """Return (canonical, issue). issue is None on success."""
    fam = (expected_family or "").upper()
    raw = _trim(value)
    if not raw:
        return None, ValidationIssue(
            code="ID_EMPTY", severity="blocking", owner="schema.id",
            site=fam, id=None, message="素材 ID 為空")

    if fam == "NS":
        canon = raw.upper()
        if NS_ID_RE.fullmatch(canon):
            return canon, None
        return None, ValidationIssue(
            code="NS_ID_INVALID", severity="blocking", owner="schema.id",
            site="NS", id=raw, message=f"NS ID 不合法：{raw!r}")

    if fam in ("YNA", "CNA", "OTH"):
        canon = raw.upper()
        rx = {"YNA": YNA_ID_RE, "CNA": CNA_ID_RE, "OTH": OTH_ID_RE}[fam]
        if rx.fullmatch(canon) and canon.startswith(fam):
            return canon, None
        return None, ValidationIssue(
            code="URL_ID_INVALID", severity="blocking", owner="schema.id",
            site=fam, id=raw, message=f"{fam} ID 不合法或前綴不符：{raw!r}")

    if fam == "AP":
        if _ap_canonical(raw):
            return raw, None
        return None, ValidationIssue(
            code="AP_ID_INVALID", severity="blocking", owner="schema.id",
            site="AP", id=raw, message=f"AP ID 不合法或大小寫不符：{raw!r}")

    if fam == "YT":
        if raw.startswith("YT:") and len(raw) > 3:
            return raw, None
        return None, ValidationIssue(
            code="YT_ID_INVALID", severity="blocking", owner="schema.id",
            site="YT", id=raw, message=f"YT ID 須以 YT: 開頭：{raw!r}")

    if fam == "RT":
        if RT_ID_RE.fullmatch(raw):
            return raw, None
        return None, ValidationIssue(
            code="RT_ID_INVALID", severity="blocking", owner="schema.id",
            site="RT", id=raw, message=f"RT ID 不合法（writer 不收 RTV）：{raw!r}")

    if fam == "ENEX":
        if ENEX_ID_RE.fullmatch(raw):
            return raw, None
        return None, ValidationIssue(
            code="ENEX_ID_INVALID", severity="blocking", owner="schema.id",
            site="ENEX", id=raw, message=f"ENEX ID 不合法：{raw!r}")

    if fam == "ABC":
        if ABC_ID_RE.fullmatch(raw):
            return raw, None
        return None, ValidationIssue(
            code="ABC_ID_INVALID", severity="blocking", owner="schema.id",
            site="ABC", id=raw, message=f"ABC ID 不合法：{raw!r}")

    if fam == "SIDE":
        if SIDE_ID_RE.fullmatch(raw):
            return raw, None
        return None, ValidationIssue(
            code="SIDE_ID_INVALID", severity="blocking", owner="schema.id",
            site="SIDE", id=raw, message=f"SIDE ID 不合法：{raw!r}")

    return None, ValidationIssue(
        code="FAMILY_UNKNOWN", severity="blocking", owner="schema.id",
        site=fam or None, id=raw, message=f"未知 expected family：{expected_family!r}")


def canonicalize_oth_platform(source: Any) -> Optional[str]:
    s = _trim(source)
    if not s:
        return None
    if any(ord(ch) < 32 for ch in s) or "\n" in s or "\r" in s:
        return None
    if len(s) > 32:
        return None
    key = s.casefold()
    if key in OTH_RESERVED:
        return None
    if key in OTH_ALIASES:
        return OTH_ALIASES[key]
    return s


def source_token_family(source: Any) -> Optional[str]:
    """Classify a source *token* without looking at ID. Unknown/forged → None.

    CNN / CNN_newsource 是 NS reader alias，不在這裡當成 SIDE。
    """
    s = _trim(source)
    if not s:
        return None
    up = s.upper()
    aliases = {
        "NS": "NS", "CNN_NEWSOURCE": "NS",
        "AP": "AP", "RT": "RT", "ENEX": "ENEX", "ABC": "ABC",
        "SIDE": "SIDE", "SIDE_CNN": "SIDE", "SIDE_NHK": "SIDE",
        "YT": "YT", "YNA": "YNA", "CNA": "CNA",
    }
    if up in aliases:
        return aliases[up]
    if up == "CNN":
        return "NS"  # reader alias; SIDE IDs are classified via ID grammar
    if canonicalize_oth_platform(s):
        return "OTH"
    return None


def canonicalize_source_family(source: Any) -> Optional[str]:
    return source_token_family(source)


def validate_source_for_write(material_id: str, source: Any) -> Optional[ValidationIssue]:
    fam = detect_id_family(material_id, lookup_alias=False)
    src = _trim(source)
    if fam == "NS":
        if src.upper() == "NS":
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="NS", id=material_id, message=f"NS ID 須 source=NS，收到 {src!r}")
    if fam == "AP":
        if src.upper() == "AP":
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="AP", id=material_id, message=f"AP ID 須 source=AP，收到 {src!r}")
    if fam == "RT":
        if src.upper() == "RT":
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="RT", id=material_id, message=f"RT ID 須 source=RT，收到 {src!r}")
    if fam == "YNA":
        if src.upper() == "YNA":
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="YNA", id=material_id, message="YNA writer 不接受 source=YT 或其他值")
    if fam == "CNA":
        if src.upper() == "CNA":
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="CNA", id=material_id, message="CNA writer 不接受 source=YT 或其他值")
    if fam == "OTH":
        plat = canonicalize_oth_platform(src)
        if plat is None:
            return ValidationIssue(
                code="OTH_SOURCE_INVALID", severity="blocking", owner="schema.source",
                site="OTH", id=material_id,
                message=f"OTH source 須為真實平台名，禁止 OTH/OTHER/?/core：{src!r}")
        return None
    if fam == "YT":
        if src.upper() == "YT":
            return None
        # YT:<video> may also be stored as OTH display platform via classify_read;
        # writer for family YT still wants YT.
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="YT", id=material_id, message=f"YT ID 須 source=YT，收到 {src!r}")
    if fam in ("ENEX", "ABC"):
        if src.upper() == fam:
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site=fam, id=material_id, message=f"{fam} ID 須 source={fam}，收到 {src!r}")
    if fam == "SIDE":
        up = src.upper()
        if up in ("SIDE", "CNN", "NHK", "SIDE_CNN", "SIDE_NHK"):
            return None
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
            site="SIDE", id=material_id, message=f"SIDE source 不合法：{src!r}")
    return ValidationIssue(
        code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.source",
        site=None, id=material_id, message=f"無法為 {material_id!r} 配對 source={src!r}")


def _item_family(existing_key: str, existing_item: Optional[Mapping]) -> Optional[str]:
    key_fam = detect_id_family(existing_key, lookup_alias=True)
    src = None
    if isinstance(existing_item, Mapping):
        src = _trim(existing_item.get("source"))
    src_fam = None
    if src:
        classified = classify_source_for_read(existing_key, src)
        src_fam = classified.family
    if key_fam and src_fam and key_fam != src_fam:
        # SIDE vs CNN alias: if key is SIDE, trust SIDE
        if key_fam == "SIDE" and src_fam == "NS":
            return "SIDE"
        if {key_fam, src_fam} <= {"YT", "OTH"}:
            return "OTH"
        return "__CONFLICT__"
    return key_fam or src_fam


def validate_existing_row_identity(existing_key, existing_item, incoming_id, incoming_source):
    looked = canonicalize_id_for_lookup(
        incoming_id, {existing_key: existing_item} if existing_key else None)
    if looked != existing_key:
        return ValidationIssue(
            code="EXISTING_ID_MISMATCH", severity="blocking", owner="schema.identity",
            site=None, id=str(incoming_id),
            message=f"incoming ID {incoming_id!r} 對不到 existing key {existing_key!r}")
    fam = _item_family(existing_key, existing_item)
    if fam == "__CONFLICT__":
        return ValidationIssue(
            code="EXISTING_FAMILY_CONFLICT", severity="blocking", owner="schema.identity",
            site=None, id=existing_key,
            message="既有 key 與 persisted source 自相矛盾")
    inc_src = _trim(incoming_source)
    if not inc_src:
        return None
    inc_fam = source_token_family(inc_src)
    if fam in GATED_FAMILIES and inc_fam != fam:
        return ValidationIssue(
            code="SOURCE_ID_MISMATCH", severity="blocking", owner="schema.identity",
            site=fam, id=existing_key,
            message=f"existing {fam} 不得用 source={inc_src!r} 進入救援路徑")
    return None


def classify_preflight_row(index: int, row: Any,
                           existing: Optional[Mapping] = None) -> PreflightRow:
    existing = existing or {}
    raw_id = _trim(row.get("id") if isinstance(row, Mapping) else "")
    lookup = canonicalize_id_for_lookup(raw_id, existing)
    id_fam = detect_id_family(raw_id, lookup_alias=True)
    inc_src = source_token_family(row.get("source") if isinstance(row, Mapping) else None)
    existing_key = lookup if lookup in existing else None
    existing_item = existing.get(existing_key) if existing_key else None
    exist_fam = _item_family(existing_key, existing_item) if existing_key else None
    return PreflightRow(
        index=index, raw_id=raw_id, lookup_id=lookup, id_family=id_fam,
        incoming_source_family=inc_src, existing_key=existing_key,
        existing_item_family=exist_fam,
    )


def row_is_gated(pr: PreflightRow) -> bool:
    fams = {pr.id_family, pr.incoming_source_family, pr.existing_item_family}
    return bool(fams & GATED_FAMILIES) or pr.existing_item_family == "__CONFLICT__"


def preflight_row_issues(pr: PreflightRow, row: Mapping,
                         existing: Optional[Mapping] = None) -> list:
    """Blocking identity issues for one add-batch row. Empty = ok to apply later."""
    issues = []
    if not isinstance(row, Mapping):
        return issues
    if pr.existing_item_family == "__CONFLICT__":
        issues.append(ValidationIssue(
            code="EXISTING_FAMILY_CONFLICT", severity="blocking",
            owner="schema.identity", id=pr.existing_key,
            message="既有 key 與 persisted source 自相矛盾"))
        return issues
    if pr.existing_key:
        issue = validate_existing_row_identity(
            pr.existing_key, (existing or {}).get(pr.existing_key),
            row.get("id"), row.get("source"))
        if issue:
            issues.append(issue)
        return issues
    raw_id = row.get("id")
    source = row.get("source")
    if not raw_id:
        return issues
    fam = detect_id_family(raw_id, lookup_alias=False) or pr.incoming_source_family
    if not fam:
        return issues
    canon, issue = validate_material_id_for_write(raw_id, fam)
    if issue:
        issues.append(issue)
        return issues
    issue = validate_source_for_write(canon, source)
    if issue:
        issues.append(issue)
    return issues


def classify_source_for_read(material_id: Any, source: Any) -> SourceClass:
    mid = _trim(material_id)
    src = _trim(source)
    src_up = src.upper()
    id_fam = detect_id_family(mid, lookup_alias=True)

    if id_fam == "SIDE":
        return SourceClass(family="SIDE", kind="side", display=src or "SIDE",
                           legacy_compat=False)

    if id_fam == "YNA":
        legacy = src_up == "YT"
        return SourceClass(family="YNA", kind="url", display="YNA",
                           legacy_compat=legacy)
    if id_fam == "CNA":
        legacy = src_up == "YT"
        return SourceClass(family="CNA", kind="url", display="CNA",
                           legacy_compat=legacy)
    if id_fam == "OTH":
        plat = canonicalize_oth_platform(src) or src
        return SourceClass(family="OTH", kind="url", display=plat or "OTH")

    if id_fam == "NS" and src_up in ("CNN_NEWSOURCE", "CNN"):
        return SourceClass(family="NS", kind="wire", display="NS", legacy_compat=True)
    if id_fam == "NS":
        return SourceClass(family="NS", kind="wire", display="NS",
                           legacy_compat=False)

    if id_fam == "YT" or (src_up == "YT" and mid.startswith("YT:")):
        return SourceClass(family="OTH", kind="url", display="YouTube",
                           legacy_compat=False)

    if id_fam in ("AP", "RT", "ENEX", "ABC"):
        kind = "wire" if id_fam in ("AP", "RT") else "platform"
        return SourceClass(family=id_fam, kind=kind, display=id_fam)

    if src_up == "CNN" and id_fam != "NS" and id_fam != "SIDE":
        return SourceClass(family="UNKNOWN", kind="unknown", display=src,
                           diagnostic="CNN_SOURCE_UNKNOWN_ID")

    if id_fam:
        return SourceClass(family=id_fam, kind="unknown", display=src or id_fam)

    plat = canonicalize_oth_platform(src)
    if plat:
        return SourceClass(family="OTH", kind="url", display=plat)
    return SourceClass(family="UNKNOWN", kind="unknown", display=src or mid)


# ── src_text ────────────────────────────────────────────────

_CJK_RE = re.compile(r"[㐀-鿿豈-﫿　-〿＀-￯]")


def _header_bodies(source: str, text: str) -> Optional[list]:
    """Parse known two-header format. None = not in header form (treat as raw body)."""
    headers = EMPTY_HEADERS.get(source)
    if not headers:
        return None
    h1, h2 = headers
    # split on second header even if first missing
    pat = re.compile(
        rf"^(?:{h1}:\s*(.*?)\s*)?{h2}:\s*(.*)\s*$",
        re.DOTALL | re.IGNORECASE,
    )
    m = pat.match(text)
    if not m:
        # also accept "H1:\nH2:" with optional bodies using line-oriented parse
        lines = text.split("\n")
        bodies = ["", ""]
        cur = None
        matched_any = False
        buf = {h1.upper(): [], h2.upper(): []}
        for line in lines:
            u = line.strip()
            up = u.upper()
            if up == h1.upper() + ":" or up.startswith(h1.upper() + ":"):
                cur = h1.upper()
                rest = line.split(":", 1)[1]
                buf[cur].append(rest)
                matched_any = True
            elif up == h2.upper() + ":" or up.startswith(h2.upper() + ":"):
                cur = h2.upper()
                rest = line.split(":", 1)[1]
                buf[cur].append(rest)
                matched_any = True
            elif cur:
                buf[cur].append(line)
        if matched_any:
            return ["\n".join(buf[h1.upper()]), "\n".join(buf[h2.upper()])]
        return None
    return [m.group(1) or "", m.group(2) or ""]


def src_text_missing(source: str, src_text: Any) -> bool:
    if src_text is None:
        return True
    if not isinstance(src_text, str):
        return False  # type error is a different issue
    if not src_text.strip():
        return True
    bodies = _header_bodies(source, src_text)
    if bodies is None:
        return not src_text.strip()
    return all(not (b or "").strip() for b in bodies)


def format_src_text(source: str, field_a: str, field_b: str) -> str:
    headers = EMPTY_HEADERS.get(source)
    if not headers:
        return ""
    a = "" if field_a is None else str(field_a)
    b = "" if field_b is None else str(field_b)
    if not a.strip() and not b.strip():
        return ""
    h1, h2 = headers
    return f"{h1}: {a}\n{h2}: {b}"


def src_text_contaminated(src_text: Any) -> bool:
    if not isinstance(src_text, str) or not src_text:
        return False
    lines = src_text.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        if _CJK_RE.search(s):
            return True
        break
    return False


def validate_src_text(source: str, src_text: Any) -> Optional[ValidationIssue]:
    policy = SRC_TEXT_POLICY.get(source)
    if not isinstance(src_text, str) and src_text is not None:
        return ValidationIssue(
            code="SRC_TEXT_TYPE", severity="blocking", owner="validator.src_text",
            site=source, message=f"{source} src_text 須為字串")
    if src_text_contaminated(src_text):
        return ValidationIssue(
            code="SRC_TEXT_CONTAMINATED", severity="blocking",
            owner="validator.src_text", site=source,
            message=f"{source} src_text 含 agent 中文說明")
    if policy and src_text_missing(source, src_text):
        return ValidationIssue(
            code="SRC_TEXT_MISSING", severity=policy, owner="validator.src_text",
            site=source, message=f"{source} 素材未帶 src_text")
    return None


def sync_src_text_missing(item: dict) -> None:
    src = item.get("source")
    if src in ("AP", "RT") and src_text_missing(src, item.get("src_text")):
        item["src_text_missing"] = True
    else:
        item.pop("src_text_missing", None)


# ── run context ─────────────────────────────────────────────

def validate_checkpoint(value: Any) -> Optional[ValidationIssue]:
    s = _trim(value)
    if CHECKPOINT_RE.fullmatch(s):
        return None
    return ValidationIssue(
        code="CHECKPOINT_INVALID", severity="blocking", owner="schema.run",
        message=f"checkpoint 須為 MMDD-HHMM，收到 {value!r}")


def validate_run_id(value: Any) -> Optional[ValidationIssue]:
    if is_uuid_v4(value):
        return None
    return ValidationIssue(
        code="RUN_ID_INVALID", severity="blocking", owner="schema.run",
        message=f"run_id 須為 lowercase UUID v4，收到 {value!r}")


def validate_checkpoint_label(value: Any) -> Optional[ValidationIssue]:
    if value is None or value is UNSET:
        return None
    if not isinstance(value, str):
        return ValidationIssue(
            code="CHECKPOINT_LABEL_INVALID", severity="blocking", owner="schema.run",
            message="checkpoint_label 須為字串或省略")
    if value == "":
        return None
    if len(value) > 80:
        return ValidationIssue(
            code="CHECKPOINT_LABEL_INVALID", severity="blocking", owner="schema.run",
            message="checkpoint_label 最長 80 字")
    if any(ord(ch) < 32 for ch in value):
        return ValidationIssue(
            code="CHECKPOINT_LABEL_INVALID", severity="blocking", owner="schema.run",
            message="checkpoint_label 不得含 CR/LF/NUL/control")
    return None


def resolve_run_context(checkpoint, run_id=None, checkpoint_label=None,
                        env_checkpoint=None, env_run_id=None,
                        env_checkpoint_label=None, envelope_checkpoint=None,
                        envelope_run_id=None, envelope_label=None,
                        generate_if_missing=True):
    """Resolve a single run context. CLI/envelope/env conflicts → issue."""
    def pick(name, cli, env, envelope):
        present = [(k, v) for k, v in (("cli", cli), ("env", env), ("envelope", envelope))
                   if v not in (None, "")]
        if not present:
            return None, None
        values = {v for _, v in present}
        if len(values) > 1:
            return None, ValidationIssue(
                code="RUN_CONTEXT_CONFLICT", severity="blocking", owner="schema.run",
                message=f"{name} 衝突：{present!r}")
        return present[0][1], None

    cp, issue = pick("checkpoint", checkpoint, env_checkpoint, envelope_checkpoint)
    if issue:
        return None, issue
    issue = validate_checkpoint(cp)
    if issue:
        return None, issue

    rid, issue = pick("run_id", run_id, env_run_id, envelope_run_id)
    if issue:
        return None, issue
    if rid in (None, ""):
        if not generate_if_missing:
            return None, ValidationIssue(
                code="RUN_ID_MISSING", severity="blocking", owner="schema.run",
                message="缺少 run_id")
        rid = str(uuid.uuid4())
    issue = validate_run_id(rid)
    if issue:
        return None, issue

    lab, issue = pick("checkpoint_label", checkpoint_label, env_checkpoint_label,
                      envelope_label)
    if issue:
        return None, issue
    if lab == "":
        lab = None
    issue = validate_checkpoint_label(lab)
    if issue:
        return None, issue

    return RunContext(checkpoint=_trim(cp), run_id=rid,
                      checkpoint_label=lab), None


def _item_str_field(item: Mapping, key: str) -> Optional[str]:
    if not isinstance(item, Mapping):
        return None
    v = item.get(key)
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s if s else None


def _iter_items(items) -> list:
    if items is None:
        return []
    if isinstance(items, Mapping):
        out = []
        for k, v in items.items():
            if isinstance(v, dict):
                row = dict(v)
                row.setdefault("id", k)
                out.append(row)
            else:
                out.append(v)
        return out
    if isinstance(items, list):
        return list(items)
    return []


def select_run_items(items, checkpoint, run_id=None, root_run_id=None):
    """Pick items that belong to the current run.

    v2 (caller has run_id): include only exact (first_seen_checkpoint,
    first_seen_run_id) tuple. Both columns miss → exclude, no issue.
    Exactly one column hits current run → exclude + RUN_ITEM_TUPLE_MISMATCH.
    """
    selected = []
    issues = []
    seq = _iter_items(items)
    cp_cur = _trim(checkpoint)

    if run_id:
        rid_cur = _trim(run_id)
        for it in seq:
            if not isinstance(it, Mapping):
                continue
            rid = _item_str_field(it, "first_seen_run_id")
            cp = _item_str_field(it, "first_seen_checkpoint")
            hit_run = rid is not None and rid == rid_cur
            hit_cp = cp is not None and cp == cp_cur
            if hit_run and hit_cp:
                selected.append(it)
            elif hit_run or hit_cp:
                issues.append({
                    "code": "RUN_ITEM_TUPLE_MISMATCH",
                    "id": it.get("id"),
                    "first_seen_checkpoint": cp,
                    "first_seen_run_id": rid,
                    "current_checkpoint": cp_cur,
                    "current_run_id": rid_cur,
                })
        return {"items": selected, "issues": issues}

    if root_run_id not in (None, ""):
        return {"items": [], "issues": [{
            "code": "RUN_ITEM_LEGACY_AMBIGUOUS",
            "message": "root 已有 run_id，拒絕 checkpoint-only fallback",
        }]}
    candidates = []
    mixed = False
    for it in seq:
        if not isinstance(it, Mapping):
            continue
        cp = _item_str_field(it, "first_seen_checkpoint")
        if cp != cp_cur:
            continue
        if "first_seen_run_id" in it:
            mixed = True
            continue
        candidates.append(it)
    if mixed:
        return {"items": [], "issues": [{
            "code": "RUN_ITEM_LEGACY_AMBIGUOUS",
            "message": "mixed first_seen_run_id，拒絕 checkpoint-only fallback",
        }]}
    return {"items": candidates, "issues": []}


# ── payload selector / RawLoadResult (step 6 helpers live here) ──

KNOWN_PAYLOAD_KEYS = ("entries", "Items", "items", "PeopleItems", "results", "data")


def select_payload_key(root: dict) -> tuple:
    """Return (key, items) or (None, error_issue)."""
    if not isinstance(root, dict):
        return None, ValidationIssue(
            code="RAW_SHAPE", severity="blocking", owner="schema.raw",
            message="root 不是物件")
    if "entries" in root:
        val = root["entries"]
        if not isinstance(val, list):
            return None, ValidationIssue(
                code="RAW_SHAPE", severity="blocking", owner="schema.raw",
                message="entries 存在但不是 list")
        return "entries", val
    for k in ("Items", "items", "PeopleItems", "results", "data"):
        if k in root:
            val = root[k]
            if not isinstance(val, list):
                return None, ValidationIssue(
                    code="RAW_SHAPE", severity="blocking", owner="schema.raw",
                    message=f"{k} 存在但不是 list")
            return k, val
    return None, ValidationIssue(
        code="RAW_SHAPE", severity="blocking", owner="schema.raw",
        message="找不到 list payload")


@dataclass(frozen=True)
class RawLoadResult:
    items: list
    shell_desc: str
    root_shape: str
    payload_key: Optional[str]
    envelope: Optional[dict]

    @property
    def envelope_meta(self) -> dict:
        if not isinstance(self.envelope, dict):
            return {}
        return {k: v for k, v in self.envelope.items() if k != self.payload_key}

    def with_items(self, items: list) -> "RawLoadResult":
        if self.envelope is None or self.payload_key is None:
            return RawLoadResult(
                items=list(items), shell_desc=self.shell_desc,
                root_shape=self.root_shape, payload_key=self.payload_key,
                envelope=None)
        import copy
        env = copy.deepcopy(self.envelope)
        env[self.payload_key] = list(items)
        return RawLoadResult(
            items=list(items), shell_desc=self.shell_desc,
            root_shape=self.root_shape, payload_key=self.payload_key,
            envelope=env)


def serialize_raw_result(result: "RawLoadResult"):
    """I/O-free dump shape: envelope if present, else bare items list."""
    if result.envelope is not None:
        return result.envelope
    return result.items


def json_values_equal(a, b) -> bool:
    """Type-sensitive JSON equality: dict key order irrelevant, list order matters.

    Scalar JSON type AND value must match (int 1 ≠ float 1.0). bool is not int.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a) != set(b):
            return False
        return all(json_values_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(
            json_values_equal(x, y) for x, y in zip(a, b))
    return a == b


_CONCAT_MISSING = object()
_CONCAT_IDENTITY_KEYS = ("checkpoint", "checkpoint_label", "run_id")
_CONCAT_SPECIAL = frozenset(_CONCAT_IDENTITY_KEYS + ("new_topics", "advisory_issues"))


def _json_preview(value, missing=False) -> str:
    if missing:
        return "<missing>"
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(value)


def _concat_conflict_msg(key, path_a, val_a, path_b, val_b, miss_a=False, miss_b=False) -> str:
    return (
        f"✗ concat metadata 衝突：key={key}\n"
        f"  來源 A：{path_a}\n"
        f"  值 A：{_json_preview(val_a, miss_a)}\n"
        f"  來源 B：{path_b}\n"
        f"  值 B：{_json_preview(val_b, miss_b)}"
    )


def merge_concat_metadata(metas):
    """Merge envelope_meta dicts from concat inputs.

    metas: list of (path, envelope_meta dict).
    Returns (merged_dict, None) or (None, error_message).
    """
    if not metas:
        return {}, None

    def _conflict(key, i, j, vi, vj, miss_i=False, miss_j=False):
        return None, _concat_conflict_msg(
            key, metas[i][0], vi, metas[j][0], vj, miss_i, miss_j)

    merged = {}

    for key in _CONCAT_IDENTITY_KEYS:
        present = []
        for i, (_, m) in enumerate(metas):
            present.append((i, m[key] if key in m else _CONCAT_MISSING))
        if all(v is _CONCAT_MISSING for _, v in present):
            continue
        first_i, first_v = present[0]
        for i, v in present[1:]:
            miss_a = first_v is _CONCAT_MISSING
            miss_b = v is _CONCAT_MISSING
            if miss_a or miss_b or not json_values_equal(first_v, v):
                return _conflict(
                    key, first_i, i,
                    None if miss_a else first_v,
                    None if miss_b else v,
                    miss_a, miss_b)
        merged[key] = first_v

    topic_maps = []
    for i, (_, m) in enumerate(metas):
        if "new_topics" not in m:
            continue
        val = m["new_topics"]
        if not isinstance(val, dict):
            j = 0 if i else min(1, len(metas) - 1)
            other = metas[j][1]
            miss_j = "new_topics" not in other
            return _conflict(
                "new_topics", i, j, val,
                None if miss_j else other.get("new_topics"),
                False, miss_j)
        topic_maps.append((i, val))
    if topic_maps:
        topics = {}
        owners = {}
        for i, tm in topic_maps:
            for k, v in tm.items():
                if k in topics:
                    if not json_values_equal(topics[k], v):
                        return None, _concat_conflict_msg(
                            f"new_topics.{k}",
                            metas[owners[k]][0], topics[k],
                            metas[i][0], v)
                else:
                    topics[k] = v
                    owners[k] = i
        merged["new_topics"] = topics

    seen_adv = set()
    adv = []
    had_adv = False
    for i, (_, m) in enumerate(metas):
        if "advisory_issues" not in m:
            continue
        had_adv = True
        val = m["advisory_issues"]
        if not isinstance(val, list):
            j = 0 if i else min(1, len(metas) - 1)
            other = metas[j][1]
            miss_j = "advisory_issues" not in other
            return _conflict(
                "advisory_issues", i, j, val,
                None if miss_j else other.get("advisory_issues"),
                False, miss_j)
        for item in val:
            if isinstance(item, dict):
                ak = (item.get("code"), item.get("site"),
                      item.get("id"), item.get("message"))
            else:
                ak = (None, None, None, repr(item))
            if ak in seen_adv:
                continue
            seen_adv.add(ak)
            adv.append(item)
    if had_adv:
        merged["advisory_issues"] = adv

    all_keys = []
    seen_k = set()
    for _, m in metas:
        for k in m:
            if k in _CONCAT_SPECIAL or k in seen_k:
                continue
            seen_k.add(k)
            all_keys.append(k)
    for key in all_keys:
        vals = [(i, (m[key] if key in m else _CONCAT_MISSING))
                for i, (_, m) in enumerate(metas)]
        first_i, first_v = vals[0]
        for i, v in vals[1:]:
            miss_a = first_v is _CONCAT_MISSING
            miss_b = v is _CONCAT_MISSING
            if miss_a or miss_b or not json_values_equal(first_v, v):
                return _conflict(
                    key, first_i, i,
                    None if miss_a else first_v,
                    None if miss_b else v,
                    miss_a, miss_b)
        merged[key] = first_v

    return merged, None
