# -*- coding: utf-8 -*-
"""A48：只解析既有 RT 請求鍵；不抓取、不改身份、不寫 state。"""
import re
from datetime import datetime


RT_GUID_RE = re.compile(
    r"(?:tag:reuters\.com,[0-9]{4}:|urn:newsml:reuters\.com:(?:[0-9]{8}:)?)"
    r"newsml_RW[0-9]{4}(?P<date>[0-9]{8})RP1:(?P<version>[0-9]+)"
)


def parse_rt_guid(guid):
    """保留版次字串（含前導零）；只有曆日，不製造 UTC 午夜或發布時刻。"""
    result = {"guid_created_date": None, "guid_version": None,
              "meta_missing_reason": []}
    if guid is None or guid == "":
        code, detail = "field_absent", "既有 RT detail 未保留請求 GUID"
    elif not isinstance(guid, str):
        code, detail = "parse_error", "RT GUID 型別不是字串，原值保留"
    else:
        match = RT_GUID_RE.fullmatch(guid)
        if match:
            result["guid_version"] = match["version"]
            try:
                result["guid_created_date"] = datetime.strptime(match["date"], "%d%m%Y").date().isoformat()
                return result
            except ValueError:
                code, detail = "parse_error", "RT GUID 建立曆日無效，原值與版次保留"
        else:
            code, detail = "parse_error", "RT GUID 不符已確認的 RW 四碼／DDMMYYYY／RP1 數字版次格式，原值保留"
    result["meta_missing_reason"].append({"field": "guid", "code": code, "detail": detail})
    return result


def rt_source_meta(raw):
    """固定白名單投影；失敗理由留在 platform，永不混進正文或 needs_review。"""
    guid = raw.get("guid")
    parsed = parse_rt_guid(guid)
    return {"meta_schema_version": 1, "site": "RT", "guid": guid, **parsed,
            "source_created_date": parsed["guid_created_date"],
            "source_ids": ([{"namespace": "reuters.guid", "value": guid,
                             "status": "candidate", "raw_field": "guid",
                             "version": parsed["guid_version"]}]
                           if isinstance(guid, str) and guid else []),
            "time_evidence": [{"raw_field": "guid", "raw_value": guid,
                               "semantic": "source_created_date", "precision": "date",
                               "source_timezone": None, "at_utc": None,
                               "date_value": parsed["guid_created_date"],
                               "extractor_version": 1}]}
