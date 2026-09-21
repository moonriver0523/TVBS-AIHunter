# -*- coding: utf-8 -*-
"""s2_material_schema.py 純函式 fixtures（scoped 1259 步驟 1）。

用法：python -X utf8 scripts/test_s2_material_schema.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


import s2_material_schema as M  # noqa: E402


# ── NS grammar ──────────────────────────────────────────────

def test_ns_id():
    good = ["SN-1MO", "SE-005WE", "SN-1000FR", "SN-1000TH", "SN-1000WE",
            "DIG-01TU", "HIST-02TU", "IN-07SU"]
    bad = ["SN-1000XX", "S-1MO", "ABCDEFG-1MO", "SN-12345MO", "SN-1",
           "sn-1MO", "SN-1mo", "SN-1 MO"]
    for v in good:
        report(f"NS good {v}", bool(M.NS_ID_RE.fullmatch(v)))
    for v in bad:
        report(f"NS bad {v}", M.NS_ID_RE.fullmatch(v) is None)


# ── URL / checkpoint / UUID ─────────────────────────────────

def test_url_checkpoint_uuid():
    report("YNA01", bool(M.URL_ID_RE.fullmatch("YNA01")))
    report("YNA99", bool(M.URL_ID_RE.fullmatch("YNA99")))
    report("YNA00 reject", M.URL_ID_RE.fullmatch("YNA00") is None)
    report("CNA09", bool(M.URL_ID_RE.fullmatch("CNA09")))
    report("OTH01", bool(M.URL_ID_RE.fullmatch("OTH01")))
    report("YNA1 reject", M.URL_ID_RE.fullmatch("YNA1") is None)
    report("YNA100 reject", M.URL_ID_RE.fullmatch("YNA100") is None)
    scheduled = "YNA-AbCd_ef-123"
    report("scheduled YNA shape", M.SCHEDULED_YOUTUBE_ID_RE.fullmatch(scheduled) is not None)
    report("scheduled CNA shape", M.SCHEDULED_YOUTUBE_ID_RE.fullmatch("CNA-XyZ987_ab-c") is not None)
    report("cp 0917-1300", bool(M.CHECKPOINT_RE.fullmatch("0917-1300")))
    report("cp 18:00 reject", M.CHECKPOINT_RE.fullmatch("18:00") is None)
    uid = "2fc482da-2bc8-4e9e-b43a-55922e17dd3e"
    report("uuid v4", M.is_uuid_v4(uid))
    report("uuid upper reject", not M.is_uuid_v4(uid.upper()))
    report("uuid v1 reject", not M.is_uuid_v4("2fc482da-2bc8-1e9e-b43a-55922e17dd3e"))


# ── strict writer ───────────────────────────────────────────

def test_strict_writer():
    canon, issue = _ok_or_pair(M.validate_material_id_for_write(" sn-1mo ", "NS"))
    report("NS write SN-1MO", canon == "SN-1MO" and issue is None)
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("SN-1000XX", "NS"))
    report("NS write XX reject", canon is None and issue is not None)

    canon, issue = _ok_or_pair(M.validate_material_id_for_write("AP4677621", "AP"))
    report("AP write keep case", canon == "AP4677621" and issue is None)
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("ap4677621", "AP"))
    report("AP write wrong case reject", canon is None and issue is not None)
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("APcctv123456", "AP"))
    report("APcctv write", canon == "APcctv123456")
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("APcns123456", "AP"))
    report("APcns write", canon == "APcns123456")

    canon, issue = _ok_or_pair(M.validate_material_id_for_write("RT2286", "RT"))
    report("RT write", canon == "RT2286")
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("RTV2286", "RT"))
    report("RTV not writer", canon is None)

    canon, issue = _ok_or_pair(M.validate_material_id_for_write("YNA01", "YNA"))
    report("YNA write", canon == "YNA01")
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("YNA-AbCd_ef-123", "YNA"))
    report("scheduled YNA write preserves case", canon == "YNA-AbCd_ef-123" and issue is None)
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("yna-AbCd_ef-123", "YNA"))
    report("scheduled YNA normalizes prefix only", canon == "YNA-AbCd_ef-123" and issue is None)
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("yna01", "YNA"))
    report("YNA upper", canon == "YNA01")
    canon, issue = _ok_or_pair(M.validate_material_id_for_write("CNA01", "YNA"))
    report("CNA vs expected YNA reject", canon is None)

    canon, issue = _ok_or_pair(M.validate_material_id_for_write("YT:abc_Def-1", "YT"))
    report("YT keep suffix", canon == "YT:abc_Def-1")

    issue = M.validate_source_for_write("SN-1MO", "NS")
    report("NS source ok", issue is None)
    issue = M.validate_source_for_write("SN-1MO", "AP")
    report("NS/AP mismatch blocking", issue is not None and issue.severity == "blocking")
    issue = M.validate_source_for_write("YNA01", "YT")
    report("YNA source=YT reject", issue is not None)
    issue = M.validate_source_for_write("YNA-AbCd_ef-123", "CNA")
    report("scheduled YNA/CNA mismatch reject", issue is not None)
    issue = M.validate_source_for_write("OTH01", "OTH")
    report("OTH source=OTH reserved reject", issue is not None)
    issue = M.validate_source_for_write("OTH01", "X")
    report("OTH source=X ok", issue is None)
    issue = M.validate_source_for_write("OTH01", "Twitter")
    report("OTH Twitter alias", issue is None)  # writer aliases to X internally; pairing ok after alias
    issue = M.validate_source_for_write("OTH01", "YouTube")
    report("OTH YouTube display ok", issue is None)
    issue = M.validate_source_for_write("OTH01", "?")
    report("OTH ? reject", issue is not None)


def _ok_or_pair(r):
    if isinstance(r, tuple):
        return r
    if r is None:
        return None, object()
    return r, None


# ── lookup dispatcher ───────────────────────────────────────

def test_dispatcher():
    existing = {
        "AP4677621": {},
        "APcctv111111": {},
        "RT2286": {},
        "SN-1MO": {},
        "YT:KeepCase": {},
        "weird-key": {},
        "ENEX1234": {},
    }
    report("exact existing", M.canonicalize_id_for_lookup("weird-key", existing) == "weird-key")
    report("AP canonical", M.canonicalize_id_for_lookup("AP4677621", existing) == "AP4677621")
    report("YT exact", M.canonicalize_id_for_lookup("YT:KeepCase", existing) == "YT:KeepCase")
    report("RTV alias", M.canonicalize_id_for_lookup("RTV2286", existing) == "RT2286")
    report("NS upper", M.canonicalize_id_for_lookup("sn-1mo", existing) == "SN-1MO")
    report("YNA upper", M.canonicalize_id_for_lookup("yna01") == "YNA01")
    report("scheduled lookup preserves suffix case",
           M.canonicalize_id_for_lookup("yna-AbCd_ef-123") == "YNA-AbCd_ef-123")
    report("scheduled family preserves suffix case",
           M.detect_id_family("YNA-AbCd_ef-123", lookup_alias=False) == "YNA")
    report("unknown trim only", M.canonicalize_id_for_lookup("  fooBar  ") == "fooBar")
    report("ENEX case keep", M.canonicalize_id_for_lookup("ENEX1234", existing) == "ENEX1234")

    issue = M.validate_existing_row_identity(
        "AP4677621", {"source": "AP"}, "AP4677621", "AP")
    report("existing identity ok", issue is None)
    issue = M.validate_existing_row_identity(
        "AP4677621", {"source": "AP"}, "AP4677621", "QAB")
    report("existing forged source reject", issue is not None)


# ── src_text ────────────────────────────────────────────────

def test_src_text():
    report("NS missing blocking", M.src_text_missing("NS", None) is True)
    report("AP missing advisory flag", M.src_text_missing("AP", "") is True)
    report("RT empty headers missing",
           M.src_text_missing("RT", "HEAD:\nSTORY:") is True)
    report("AP body present",
           M.src_text_missing("AP", "HEAD: hi\nSCRIPT:") is False)
    report("whitespace body not rewritten as missing",
           M.src_text_missing("AP", "HEAD:  \nSCRIPT: x") is False)
    report("NS empty headers missing",
           M.src_text_missing("NS", "DESC:\nSCRIPT:") is True)

    report("formatter all empty", M.format_src_text("AP", "", "") == "")
    fmt = M.format_src_text("AP", "hi", "")
    report("formatter keep header if any body", fmt.startswith("HEAD:") and "hi" in fmt)

    issue = M.validate_src_text("NS", 123)
    report("non-string blocking", issue is not None and issue.severity == "blocking")
    dirty = "HEAD: hello\n（說明：這是中文 agent note SHOTLIST）"
    issue = M.validate_src_text("RT", dirty)
    report("agent note contamination blocking",
           issue is not None and issue.severity == "blocking")

    it = {"source": "AP", "src_text": ""}
    M.sync_src_text_missing(it)
    report("sync AP empty sets flag", it.get("src_text_missing") is True)
    it["src_text"] = "HEAD: x\nSCRIPT: y"
    M.sync_src_text_missing(it)
    report("sync AP filled pops flag", "src_text_missing" not in it)
    it = {"source": "NS", "src_text": None}
    M.sync_src_text_missing(it)
    report("sync NS never persisted flag", "src_text_missing" not in it)

    issue = M.validate_src_text("NS", "")
    report("NS empty blocking", issue is not None and issue.severity == "blocking")
    issue = M.validate_src_text("AP", "")
    report("AP empty advisory", issue is not None and issue.severity == "advisory")
    report("material_uid always null",
           issue.material_uid is None if issue else False)


# ── source classifier ───────────────────────────────────────

def test_classify_read():
    c = M.classify_source_for_read("YNA01", "YNA")
    report("YNA direct", c.family == "YNA" and c.kind == "url" and c.legacy_compat is False)
    c = M.classify_source_for_read("YNA01", "YT")
    report("legacy YT+YNA", c.family == "YNA" and c.legacy_compat is True)
    c = M.classify_source_for_read("CNA02", "YT")
    report("legacy YT+CNA", c.family == "CNA" and c.legacy_compat is True)
    c = M.classify_source_for_read("SN-1MO", "CNN_newsource")
    report("CNN_newsource→NS", c.family == "NS" and c.kind == "wire" and c.legacy_compat is True)
    c = M.classify_source_for_read("SN-1MO", "CNN")
    report("CNN→NS", c.family == "NS" and c.legacy_compat is True)
    c = M.classify_source_for_read("CNN 120000", "CNN")
    report("SIDE_CNN not swallowed", c.family == "SIDE")
    c = M.classify_source_for_read("YT:abcdef", "YT")
    report("generic YT is OTH url", c.family == "OTH" and c.kind == "url")
    c = M.classify_source_for_read("OTH01", "X")
    report("OTH+X", c.family == "OTH")


# ── run resolver ────────────────────────────────────────────

def test_run_resolver():
    ctx, issue = M.resolve_run_context(
        checkpoint="0917-1300", run_id="2fc482da-2bc8-4e9e-b43a-55922e17dd3e",
        checkpoint_label="補漏")
    report("resolve ok", issue is None and ctx.run_id.startswith("2fc482da")
           and ctx.checkpoint == "0917-1300" and ctx.checkpoint_label == "補漏")
    ctx, issue = M.resolve_run_context(checkpoint="18:00")
    report("bad checkpoint", issue is not None)
    ctx, issue = M.resolve_run_context(
        checkpoint="0917-1300", run_id="not-a-uuid")
    report("bad run_id", issue is not None)
    ctx, issue = M.resolve_run_context(
        checkpoint="0917-1300", checkpoint_label="a" * 81)
    report("label too long", issue is not None)
    ctx, issue = M.resolve_run_context(
        checkpoint="0917-1300", checkpoint_label="bad\nline")
    report("label newline", issue is not None)
    ctx, issue = M.resolve_run_context(
        checkpoint="0917-1300",
        run_id="2fc482da-2bc8-4e9e-b43a-55922e17dd3e",
        env_run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    report("cli/env conflict", issue is not None)
    ctx, issue = M.resolve_run_context(checkpoint="0917-1300")
    report("generate uuid v4", issue is None and M.is_uuid_v4(ctx.run_id))
    a = M.resolve_run_context(checkpoint="0917-1300")[0].run_id
    b = M.resolve_run_context(checkpoint="0917-1300")[0].run_id
    report("generate once per call not sticky", a != b)

    issue = M.detect_id_family("AP4677621")
    report("family AP", issue == "AP")
    report("family NS", M.detect_id_family("SN-1MO") == "NS")
    report("family RTV as RT lookup", M.detect_id_family("RTV2286") == "RT")
    report("family unknown", M.detect_id_family("QAB") is None)


def test_select_run_items():
    rid_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    rid_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    cp = "0918-1300"
    both = {"id": "X1", "first_seen_checkpoint": cp, "first_seen_run_id": rid_a}
    miss = {"id": "X2", "first_seen_checkpoint": "0918-0900",
            "first_seen_run_id": rid_b}
    one = {"id": "X3", "first_seen_checkpoint": cp, "first_seen_run_id": rid_b}
    r = M.select_run_items([both, miss, one], cp, rid_a)
    report("select both-equal", [it["id"] for it in r["items"]] == ["X1"])
    report("select both-miss silent",
           all(i.get("id") != "X2" for i in r["issues"]))
    report("select one-sided DIAG",
           any(i.get("id") == "X3" and i.get("code") == "RUN_ITEM_TUPLE_MISMATCH"
               for i in r["issues"]))


# ── issue shape ─────────────────────────────────────────────

def test_issue_shape():
    issue = M.ValidationIssue(
        code="SRC_TEXT_MISSING", severity="advisory", owner="validator.src_text",
        site="RT", id="RT2286", message="RT 素材未帶 src_text")
    d = issue.to_dict()
    report("issue keys", set(d) >= {
        "code", "severity", "owner", "site", "id", "material_uid", "message"})
    report("issue uid null", d["material_uid"] is None)


if __name__ == "__main__":
    test_ns_id()
    test_url_checkpoint_uuid()
    test_strict_writer()
    test_dispatcher()
    test_src_text()
    test_classify_read()
    test_run_resolver()
    test_select_run_items()
    test_issue_shape()
    sys.exit(0 if ok else 1)
