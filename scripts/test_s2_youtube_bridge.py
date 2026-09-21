# -*- coding: utf-8 -*-
"""D23 bridge fixture tests.

本檔只使用假 client／fixture，不得連外；Phase 2 先寫 collect 紅燈，後續
Phase 3／4 再在同一個 public CLI seam 追加 finalize、游標與鎖測試。
"""
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_youtube_bridge as bridge  # noqa: E402


def item(video_id, published, channel_id, title=None):
    return {
        "contentDetails": {"videoId": video_id, "videoPublishedAt": published},
        "snippet": {
            "channelId": channel_id,
            "resourceId": {"videoId": video_id},
            "title": title or video_id,
            "description": "fixture description",
        },
    }


class FakeClient:
    def __init__(self, playlist_pages, videos, captions, shorts=None):
        self.playlist_pages = playlist_pages
        self.videos = videos
        self.captions = captions
        self.shorts = set(shorts or ())
        self.playlist_calls = []
        self.video_calls = []
        self.caption_calls = []
        self.shorts_calls = []

    def list_playlist_items(self, channel_id, page_token=None, max_results=50):
        self.playlist_calls.append((channel_id, page_token, max_results))
        return self.playlist_pages[page_token or "first"]

    def list_videos(self, video_ids):
        self.video_calls.append(list(video_ids))
        return {video_id: self.videos[video_id] for video_id in video_ids
                if video_id in self.videos}

    def get_captions(self, video_id, language, kind):
        self.caption_calls.append((video_id, language, kind))
        return self.captions.get(video_id)

    def is_short(self, video_id):
        self.shorts_calls.append(video_id)
        return video_id in self.shorts


def video(video_id, channel_id, published, duration="PT1M35S", privacy="public",
          live="none", region_restriction=None, actual_start_time=None,
          description="metadata description"):
    content_details = {"duration": duration}
    if region_restriction is not None:
        content_details["regionRestriction"] = region_restriction
    row = {
        "id": video_id,
        "snippet": {
            "channelId": channel_id,
            "publishedAt": published,
            "title": f"{video_id} metadata title",
            "description": description,
            "liveBroadcastContent": live,
        },
        "contentDetails": content_details,
        "status": {"privacyStatus": privacy, "uploadStatus": "processed"},
    }
    if actual_start_time is not None:
        row["liveStreamingDetails"] = {"actualStartTime": actual_start_time}
    return row


def cna_client():
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    pages = {
        "first": {"items": [
            item("AbCd_ef-123", "2026-09-20T14:55:00Z", channel),
            item("CnaVid_00-1", "2026-09-20T14:20:00Z", channel),
        ], "nextPageToken": "page-2"},
        "page-2": {"items": [
            item("XyZ987_ab-c", "2026-09-20T12:00:00Z", channel),
            item("AbCd_ef-123", "2026-09-20T13:00:00Z", channel),
        ], "nextPageToken": "page-3"},
        "page-3": {"items": [
            item("OldCna_00-1", "2026-09-20T11:49:00Z", channel),
        ]},
    }
    videos = {
        "AbCd_ef-123": video("AbCd_ef-123", channel, "2026-09-20T14:55:02Z"),
        "CnaVid_00-1": video("CnaVid_00-1", channel, "2026-09-20T14:20:00Z", privacy="private"),
        "XyZ987_ab-c": video("XyZ987_ab-c", channel, "2026-09-20T12:00:00Z", live="live"),
    }
    captions = {
        "AbCd_ef-123": {"language": "en", "kind": "auto", "segments": [
            {"start": 0, "text": "Leaders met today"},
            {"start": 1, "text": "Leaders met today"},
            {"start": 2, "text": "to discuss the plan."},
        ]},
    }
    return FakeClient(pages, videos, captions)


def cursor(last_end="2026-09-20T12:00:00Z", revision=4):
    return {"schema_version": 1, "revision": revision, "sites": {
        "CNA": {
            "last_success_checkpoint": "0920-0100",
            "last_complete_end_utc": last_end,
            "deferred_video_ids": [],
            "recent_video_ids": [],
        },
        "YNA": {
            "last_success_checkpoint": "0920-0100",
            "last_complete_end_utc": last_end,
            "deferred_video_ids": [],
            "recent_video_ids": [],
        },
    }}


def report(name, passed, detail=""):
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def test_collect_paginates_and_accounts():
    client = cna_client()
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    ids = [it["id"] for it in manifest["items"]]
    assert ids == ["CNA-AbCd_ef-123"]
    assert len(client.playlist_calls) == 3
    assert client.playlist_calls[0][2] == 50
    assert client.video_calls == [["AbCd_ef-123", "CnaVid_00-1", "XyZ987_ab-c"]]
    assert client.caption_calls == [("AbCd_ef-123", "en", "auto")]
    assert manifest["counts"]["ready"] == 1
    assert manifest["counts"]["deferred"] == 1
    assert manifest["counts"]["skipped"] == 1
    assert {row["video_id"]: row["reason"] for row in manifest["skipped"]} == {
        "XyZ987_ab-c": "livestream-excluded"
    }
    assert manifest["counts"]["window_total"] == 3
    assert manifest["counts"]["accounted"] == 3
    assert manifest["items"][0]["src_text"] == "Leaders met today\nto discuss the plan."
    assert manifest["items"][0]["platform"]["caption"] == {
        "language": "en", "kind": "auto", "precision": "source-auto"
    }


def test_existing_state_does_not_redownload_caption():
    client = cna_client()
    state = {"items": [{"id": "CNA-AbCd_ef-123", "script_status": "has_script"}]}
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data=state,
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"] == []
    assert any(x["reason"] == "already-in-state" for x in manifest["skipped"])
    assert client.caption_calls == []


def test_deferred_queue_retries_even_when_playlist_no_longer_contains_video():
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    deferred_id = "CnaVid_00-1"
    client = FakeClient(
        {"first": {"items": []}},
        {deferred_id: video(deferred_id, channel, "2026-09-20T14:20:00Z")},
        {deferred_id: {"language": "en", "kind": "auto", "segments": [{"text": "retry"}]}},
    )
    cur = cursor()
    cur["sites"]["CNA"]["deferred_video_ids"] = [deferred_id]
    cur["sites"]["CNA"]["recent_video_ids"] = [deferred_id]
    result = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cur, state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert [row["id"] for row in result["items"]] == ["CNA-CnaVid_00-1"]
    assert result["deferred"] == []
    assert client.video_calls == [[deferred_id]]
    assert client.caption_calls == [(deferred_id, "en", "auto")]


def test_skipped_checkpoint_makes_no_external_calls():
    client = cna_client()
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0100", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T01:01:00Z",
    )
    assert manifest["status"] == "skipped"
    assert manifest["counts"] == {
        "playlist_pages": 0, "playlist_items_seen": 0, "window_total": 0,
        "ready": 0, "skipped": 0, "dropped": 0, "deferred": 0, "accounted": 0,
    }
    assert client.playlist_calls == []
    assert client.video_calls == []
    assert client.caption_calls == []


def test_yna_uses_zh_hant_and_marks_triage_only():
    channel = bridge.SITE_SPECS["YNA"]["channel_id"]
    client = FakeClient(
        {"first": {"items": [
            item("YnaVid_ko-1", "2026-09-20T14:59:00+00:00", channel),
            item("ZyX321_ko-a", "2026-09-20T12:05:00Z", channel),
            item("OldYna_00-1", "2026-09-20T11:49:00Z", channel),
        ]}},
        {
            "YnaVid_ko-1": video("YnaVid_ko-1", channel, "2026-09-20T14:59:01Z", duration="PT2M"),
            "ZyX321_ko-a": video("ZyX321_ko-a", channel, "2026-09-20T12:05:00Z", duration="PT30S"),
        },
        {"YnaVid_ko-1": {"language": "zh-Hant", "kind": "auto-translated",
                         "segments": [{"text": "南韓政府今天表示"}, {"text": "南韓政府今天表示"}]},
         "ZyX321_ko-a": {"language": "zh-Hant", "kind": "auto-translated", "segments": []}},
    )
    manifest = bridge.collect_manifest(
        site="YNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"][0]["id"] == "YNA-YnaVid_ko-1"
    assert manifest["items"][0]["src_text"] == "南韓政府今天表示"
    assert manifest["items"][0]["platform"]["caption"] == {
        "language": "zh-Hant", "kind": "auto-translated", "precision": "triage-only"
    }
    assert client.caption_calls == [
        ("YnaVid_ko-1", "zh-Hant", "auto-translated"),
        ("ZyX321_ko-a", "zh-Hant", "auto-translated"),
    ]
    assert manifest["counts"]["deferred"] == 1


def test_channel_mismatch_is_blocking():
    client = cna_client()
    bad = item("AbCd_ef-123", "2026-09-20T14:55:00Z", "wrong-channel")
    client.playlist_pages["first"]["items"][0] = bad
    try:
        bridge.collect_manifest(
            site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
            client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
        )
    except bridge.BridgeError as exc:
        assert "channel" in str(exc).lower()
    else:
        raise AssertionError("channel mismatch must block collection")


def test_region_restricted_outside_taiwan_is_skipped_not_deferred():
    """D23 裁決：regionRestriction 排除 TW 屬永久狀態，直接歸 skipped（不再重試），
    不可跟 caption-missing 等可能恢復的狀況一樣進 deferred 佇列每輪重打。"""
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z",
        region_restriction={"allowed": ["SG"]},
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert [row["video_id"] for row in manifest["items"]].count("AbCd_ef-123") == 0
    assert [row["video_id"] for row in manifest["deferred"]].count("AbCd_ef-123") == 0
    skipped_ids = {row["video_id"]: row for row in manifest["skipped"]}
    assert skipped_ids["AbCd_ef-123"]["reason"] == "region-restricted"
    assert skipped_ids["AbCd_ef-123"]["region_restriction"] == {"allowed": ["SG"]}
    # cna_client()'s own fixture also has a "live" video (XyZ987_ab-c), which
    # now lands in skipped too (livestream-excluded), not deferred.
    assert skipped_ids["XyZ987_ab-c"]["reason"] == "livestream-excluded"
    assert manifest["counts"]["skipped"] == 2

    # Skipped video IDs are recorded in cursor.recent_video_ids so a permanently
    # region-blocked video is never re-fetched and re-classified every round.
    next_cursor = bridge.advance_cursor(cursor(), manifest)
    assert "AbCd_ef-123" in next_cursor["sites"]["CNA"]["recent_video_ids"]
    assert "AbCd_ef-123" not in next_cursor["sites"]["CNA"]["deferred_video_ids"]


def test_region_restricted_blocked_list_containing_taiwan_is_skipped():
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z",
        region_restriction={"blocked": ["TW", "CN"]},
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"] == []
    skipped_ids = {row["video_id"] for row in manifest["skipped"]}
    assert "AbCd_ef-123" in skipped_ids


def test_region_restriction_allowing_taiwan_still_proceeds_to_ready():
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z",
        region_restriction={"allowed": ["TW", "SG"]},
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert len(manifest["items"]) == 1
    assert manifest["items"][0]["video_id"] == "AbCd_ef-123"


def test_past_livestream_recording_is_excluded_even_after_ending():
    """D23 裁決：直播一律不收，含已結束、liveBroadcastContent 已變回 none 的
    往日直播錄影（用 liveStreamingDetails.actualStartTime 判斷曾經直播過）。"""
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z",
        actual_start_time="2026-09-20T14:00:00Z",  # ended; liveBroadcastContent already "none"
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"] == []
    skipped = {row["video_id"]: row for row in manifest["skipped"]}
    assert skipped["AbCd_ef-123"]["reason"] == "livestream-excluded"
    assert skipped["AbCd_ef-123"]["was_ever_live"] is True


def test_upcoming_video_is_deferred_for_later_retry():
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z", live="upcoming"
    )
    result = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert result["items"] == []
    assert result["deferred"][0]["reason"] == "upcoming-live-broadcast"


def test_collect_cli_requires_explicit_checkpoint():
    try:
        bridge.build_parser().parse_args([
            "collect", "--site", "cna", "--state", "state.json", "--cursor", "cursor.json", "--out", "x.manifest.json"
        ])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("manual collect must require --checkpoint")


def test_short_video_is_excluded():
    client = cna_client()
    client.shorts.add("AbCd_ef-123")
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"] == []
    skipped = {row["video_id"]: row for row in manifest["skipped"]}
    assert skipped["AbCd_ef-123"]["reason"] == "short-excluded"
    assert "AbCd_ef-123" in client.shorts_calls


def test_shorts_check_failure_is_non_blocking_warning():
    """Shorts 判定是額外的最佳努力檢查；查不到時不可讓整批 collect 失敗，
    只留 warning、當作不是 Shorts 繼續走正常分類。"""
    client = cna_client()
    original_is_short = client.is_short

    def failing_is_short(video_id):
        if video_id == "AbCd_ef-123":
            raise bridge.BridgeError("shorts 頁面檢查逾時（模擬）")
        return original_is_short(video_id)

    client.is_short = failing_is_short
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert [row["id"] for row in manifest["items"]] == ["CNA-AbCd_ef-123"]
    assert any("shorts-check-failed" in w["reason"] for w in manifest["warnings"])


def test_sufficient_description_is_used_directly_without_fetching_captions():
    """D23 裁決（2026-09-20）：description 夠完整就直接當 src_text，不必等字幕
    ——省 yt-dlp 呼叫，也不受字幕限流影響。"""
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    rich_description = (
        "南韓官方今天證實，一架軍機在例行訓練中於外海墜毀，兩名機組員已獲救送醫。"
        "國防部表示將成立調查小組釐清事故原因，並暫停同型機隊飛行任務直到調查完成。"
    )
    assert len(rich_description) >= bridge.DESCRIPTION_SUFFICIENT_MIN_CHARS
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z", description=rich_description
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert len(manifest["items"]) == 1
    row = manifest["items"][0]
    assert row["src_text"] == rich_description
    assert row["platform"]["caption"] == {
        "source": "description", "kind": "description", "precision": "source-text"
    }
    assert "AbCd_ef-123" not in client.caption_calls  # never called get_captions


def test_thin_description_falls_back_to_captions():
    client = cna_client()
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    client.videos["AbCd_ef-123"] = video(
        "AbCd_ef-123", channel, "2026-09-20T14:55:02Z", description="太短了"
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert len(manifest["items"]) == 1
    row = manifest["items"][0]
    assert row["src_text"] == "Leaders met today\nto discuss the plan."
    assert row["platform"]["caption"]["kind"] == "auto"
    assert ("AbCd_ef-123", "en", "auto") in client.caption_calls


def test_description_boilerplate_lines_are_stripped_before_sufficiency_check():
    channel_footer_only = (
        "▣ 연합뉴스TV 경제정보 '머니뭅' 구독하기\n"
        "https://www.youtube.com/@moneymove_TV\n\n"
        "▣ 연합뉴스TV 유튜브 채널 구독\n"
        "https://www.youtube.com/@yonhapnewstv23\n"
    )
    cleaned = bridge._clean_description(channel_footer_only)
    assert cleaned == ""
    assert bridge._description_is_sufficient(cleaned) is False

    mixed = channel_footer_only + "北韓今天下午發射了一枚彈道飛彈，飛行約450公里，是今年第14次挑釁。"
    cleaned_mixed = bridge._clean_description(mixed)
    assert "youtube.com" not in cleaned_mixed
    assert "▣" not in cleaned_mixed
    assert "北韓今天下午發射了一枚彈道飛彈" in cleaned_mixed


def test_missing_join_is_deferred_and_fifty_ids_are_batched():
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    rows = [item(f"A{i:010d}", f"2026-09-20T14:{i // 60:02d}:{i % 60:02d}Z", channel)
            for i in range(51)]
    pages = {"first": {"items": rows}}
    videos = {
        row["contentDetails"]["videoId"]: video(
            row["contentDetails"]["videoId"], channel,
            row["contentDetails"]["videoPublishedAt"], duration="PT30S"
        ) for row in rows[:-1]
    }
    captions = {
        video_id: {"language": "en", "kind": "auto", "segments": [{"text": "caption"}]}
        for video_id in videos
    }
    client = FakeClient(pages, videos, captions)
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert [len(batch) for batch in client.video_calls] == [50, 1]
    assert len(manifest["items"]) == 50
    assert manifest["deferred"] == [{
        "video_id": "A0000000050", "reason": "metadata-missing", "id": "CNA-A0000000050"
    }]
    assert manifest["counts"]["accounted"] == 51


def test_playlist_fallback_and_mismatch_are_explicit():
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    fallback = {
        "contentDetails": {"videoPublishedAt": "2026-09-20T14:00:00Z"},
        "snippet": {"channelId": channel, "resourceId": {"videoId": "AbCd_ef-123"}},
    }
    client = FakeClient(
        {"first": {"items": [fallback]}},
        {"AbCd_ef-123": video("AbCd_ef-123", channel, "2026-09-20T14:00:01Z")},
        {"AbCd_ef-123": {"language": "en", "kind": "auto", "segments": [{"text": "ok"}]}},
    )
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"][0]["id"] == "CNA-AbCd_ef-123"
    assert manifest["items"][0]["platform"]["video_id"] == "AbCd_ef-123"

    mismatch = dict(fallback)
    mismatch["contentDetails"] = {
        "videoId": "ZyX321_ko-a", "videoPublishedAt": "2026-09-20T14:00:00Z"
    }
    bad_client = FakeClient({"first": {"items": [mismatch]}}, {}, {})
    try:
        bridge.collect_manifest(
            site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
            client=bad_client, collect_started_at_utc="2026-09-20T15:00:00Z",
        )
    except bridge.BridgeError as exc:
        assert "videoId" in str(exc)
    else:
        raise AssertionError("contentDetails/resourceId mismatch must block")


def test_invalid_primary_published_at_is_deferred_instead_of_silently_falling_back():
    channel = bridge.SITE_SPECS["CNA"]["channel_id"]
    bad_time = item("AbCd_ef-123", "not-a-timestamp", channel)
    client = FakeClient(
        {"first": {"items": [bad_time]}},
        {"AbCd_ef-123": video("AbCd_ef-123", channel, "2026-09-20T14:55:00Z")},
        {"AbCd_ef-123": {"language": "en", "kind": "auto", "segments": [{"text": "must not fetch"}]}},
    )
    result = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert result["items"] == []
    assert result["deferred"][0]["reason"] == "published-at-invalid"
    assert client.caption_calls == []


def test_fixture_adapter_is_offline_and_no_output_overwrite():
    fixture_dir = os.path.join(HERE, "fixtures", "d23_youtube")
    client = bridge.FixtureYouTubeClient(fixture_dir, "CNA")
    manifest = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
        client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert manifest["items"][0]["id"] == "CNA-AbCd_ef-123"
    assert "api_key" not in json.dumps(manifest).lower()
    with __import__("tempfile").TemporaryDirectory(prefix="d23-output-") as td:
        out = os.path.join(td, "manifest.json")
        bridge.write_json_no_overwrite(out, manifest)
        try:
            bridge.write_json_no_overwrite(out, manifest)
        except bridge.BridgeError as exc:
            assert "拒絕覆寫" in str(exc)
        else:
            raise AssertionError("existing output must not be overwritten")


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


def test_production_api_uses_mock_http_and_never_leaks_key_to_artifacts():
    secret = "AIza-phase6-test-secret-do-not-log"
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        if "/playlistItems?" in request.full_url:
            return FakeHttpResponse({"items": []})
        if "/videos?" in request.full_url:
            return FakeHttpResponse({"items": []})
        raise AssertionError(request.full_url)

    original_urlopen = bridge.urlopen
    old_key = os.environ.get("YOUTUBE_API_KEY")
    bridge.urlopen = fake_urlopen
    os.environ["YOUTUBE_API_KEY"] = secret
    try:
        client = bridge.ProductionYouTubeClient(secret)
        playlist = client.list_playlist_items(bridge.SITE_SPECS["CNA"]["channel_id"], "next-page")
        videos = client.list_videos(["AbCd_ef-123"])
        manifest = bridge.collect_manifest(
            site="CNA", checkpoint="0920-0430", cursor_data=cursor(), state_data={"items": []},
            client=client, collect_started_at_utc="2026-09-20T15:00:00Z",
        )
        with tempfile.TemporaryDirectory(prefix="d23-api-key-output-") as td:
            state_path = os.path.join(td, "state.json")
            cursor_path = os.path.join(td, "cursor.json")
            out_path = os.path.join(td, "manifest.json")
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"items": []}, f)
            with open(cursor_path, "w", encoding="utf-8") as f:
                json.dump(cursor(), f)
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = bridge.main(["collect", "--site", "cna", "--checkpoint", "0920-0430",
                                  "--state", state_path, "--cursor", cursor_path, "--out", out_path])
            assert rc == 0
            assert not stderr.getvalue()
            assert secret not in stdout.getvalue()
            assert secret not in open(out_path, encoding="utf-8").read()
    finally:
        bridge.urlopen = original_urlopen
        if old_key is None:
            os.environ.pop("YOUTUBE_API_KEY", None)
        else:
            os.environ["YOUTUBE_API_KEY"] = old_key

    assert playlist == {"items": []}
    assert videos == {}
    assert len(calls) == 4
    assert all(secret in url for url, _ in calls)
    assert all(timeout == 30 for _, timeout in calls)
    playlist_calls = [url for url, _ in calls if "/playlistItems?" in url]
    assert playlist_calls, "expected at least one playlistItems.list call"
    for url in playlist_calls:
        # playlistItems.list has no channelId parameter; it must be called with
        # the derived uploads playlistId (UC... -> UU...).
        assert "channelId=" not in url, url
        assert "playlistId=UU83jt4dlz1Gjl58fzQrrKZg" in url, url
    batch = bridge.finalize_manifest({
        "schema_version": 1, "status": "complete", "site": "CNA", "checkpoint": "0920-0430",
        "collect_started_at_utc": "2026-09-20T15:00:00Z", "items": [], "skipped": [],
        "dropped": [], "deferred": [],
        "counts": {"window_total": 0, "ready": 0, "skipped": 0, "dropped": 0,
                   "deferred": 0, "accounted": 0},
    }, {"_new_topics": {}})
    assert secret not in json.dumps(manifest)
    assert secret not in json.dumps(batch)
    with tempfile.TemporaryDirectory(prefix="d23-api-key-batch-") as td:
        batch_path = os.path.join(td, "batch.json")
        bridge.write_json_no_overwrite(batch_path, batch)
        assert secret not in open(batch_path, encoding="utf-8").read()


def test_real_collect_missing_key_reports_error_without_output_or_leak():
    secret = "AIza-phase6-test-secret-do-not-log"
    old = os.environ.pop("YOUTUBE_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory(prefix="d23-missing-key-") as td:
            state_path = os.path.join(td, "state.json")
            cursor_path = os.path.join(td, "cursor.json")
            out_path = os.path.join(td, "manifest.json")
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"items": []}, f)
            with open(cursor_path, "w", encoding="utf-8") as f:
                json.dump(cursor(), f)
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = bridge.main(["collect", "--site", "cna", "--checkpoint", "0920-0430",
                                  "--state", state_path, "--cursor", cursor_path, "--out", out_path])
            assert rc == 2
            assert "YOUTUBE_API_KEY" in stderr.getvalue()
            assert secret not in stderr.getvalue()
            assert secret not in stdout.getvalue()
            assert not os.path.exists(out_path)
    finally:
        if old is not None:
            os.environ["YOUTUBE_API_KEY"] = old


def test_api_http_error_redacts_key_from_stderr():
    secret = "AIza-phase6-test-secret-do-not-log"

    def failing_urlopen(request, timeout):
        raise bridge.URLError(f"request URL included key={secret}")

    old_key, original_urlopen = os.environ.get("YOUTUBE_API_KEY"), bridge.urlopen
    os.environ["YOUTUBE_API_KEY"] = secret
    bridge.urlopen = failing_urlopen
    try:
        with tempfile.TemporaryDirectory(prefix="d23-api-error-") as td:
            state_path = os.path.join(td, "state.json")
            cursor_path = os.path.join(td, "cursor.json")
            out_path = os.path.join(td, "manifest.json")
            for path, value in ((state_path, {"items": []}), (cursor_path, cursor())):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(value, f)
            stderr = StringIO()
            with redirect_stderr(stderr):
                rc = bridge.main(["collect", "--site", "cna", "--checkpoint", "0920-0430",
                                  "--state", state_path, "--cursor", cursor_path, "--out", out_path])
            assert rc == 2
            assert "YouTube Data API playlistItems 請求失敗" in stderr.getvalue()
            assert secret not in stderr.getvalue()
            assert not os.path.exists(out_path)
    finally:
        bridge.urlopen = original_urlopen
        if old_key is None:
            os.environ.pop("YOUTUBE_API_KEY", None)
        else:
            os.environ["YOUTUBE_API_KEY"] = old_key


def main():
    tests = [test_collect_paginates_and_accounts,
             test_existing_state_does_not_redownload_caption,
             test_deferred_queue_retries_even_when_playlist_no_longer_contains_video,
             test_skipped_checkpoint_makes_no_external_calls,
             test_yna_uses_zh_hant_and_marks_triage_only,
             test_channel_mismatch_is_blocking,
             test_region_restricted_outside_taiwan_is_skipped_not_deferred,
             test_region_restricted_blocked_list_containing_taiwan_is_skipped,
             test_region_restriction_allowing_taiwan_still_proceeds_to_ready,
             test_past_livestream_recording_is_excluded_even_after_ending,
             test_upcoming_video_is_deferred_for_later_retry,
             test_collect_cli_requires_explicit_checkpoint,
             test_short_video_is_excluded,
             test_shorts_check_failure_is_non_blocking_warning,
             test_sufficient_description_is_used_directly_without_fetching_captions,
             test_thin_description_falls_back_to_captions,
             test_description_boilerplate_lines_are_stripped_before_sufficiency_check,
             test_missing_join_is_deferred_and_fifty_ids_are_batched,
             test_playlist_fallback_and_mismatch_are_explicit,
             test_invalid_primary_published_at_is_deferred_instead_of_silently_falling_back,
             test_fixture_adapter_is_offline_and_no_output_overwrite,
             test_production_api_uses_mock_http_and_never_leaks_key_to_artifacts,
             test_real_collect_missing_key_reports_error_without_output_or_leak,
             test_api_http_error_redacts_key_from_stderr]
    ok = True
    for test in tests:
        try:
            test()
            ok &= report(test.__name__, True)
        except Exception as exc:
            ok &= report(test.__name__, False, repr(exc))
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
