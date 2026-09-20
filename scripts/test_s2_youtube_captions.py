# -*- coding: utf-8 -*-
"""Offline tests for the yt-dlp caption adapter; no process or network calls."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_youtube_bridge as bridge  # noqa: E402


def test_fetcher_parses_vtt_and_removes_temporary_file():
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        output_template = command[command.index("-o") + 1]
        vtt = output_template.replace("%(id)s.%(ext)s", "AbCd_ef-123.en.vtt")
        with open(vtt, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n\n"
                    "00:01.000 --> 00:02.000\nHello world\n\n"
                    "00:02.000 --> 00:03.000\nworld\n")
        return subprocess.CompletedProcess(command, 0, "", "")

    fetcher = bridge.YtDlpCaptionFetcher(runner=fake_run)
    result = fetcher.get_captions("AbCd_ef-123", "en", "auto")
    assert result == {"language": "en", "kind": "auto",
                      "segments": [{"text": "Hello"}, {"text": "world"}]}
    assert seen["command"][:10] == [
        "yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "en",
        "--sub-format", "vtt", "--convert-subs", "vtt", "-o",
    ]
    output_template = seen["command"][10]
    assert not os.path.exists(output_template.replace("%(id)s.%(ext)s", "AbCd_ef-123.en.vtt"))


def test_fetcher_missing_executable_is_environment_error():
    def fake_run(command, **kwargs):
        raise FileNotFoundError("yt-dlp")

    try:
        bridge.YtDlpCaptionFetcher(runner=fake_run).get_captions("video", "en", "auto")
    except bridge.YtDlpNotFoundError as exc:
        assert "yt-dlp" in str(exc)
    else:
        raise AssertionError("missing executable must not look like missing captions")


def test_fetcher_no_output_means_caption_missing():
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "", "")

    assert bridge.YtDlpCaptionFetcher(runner=fake_run).get_captions("video", "en", "auto") is None


def test_fetcher_bot_detection_raises_distinct_error():
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, "", "ERROR: Sign in to confirm you're not a bot"
        )

    try:
        bridge.YtDlpCaptionFetcher(runner=fake_run).get_captions("video", "en", "auto")
    except bridge.CaptionFetchBlockedError:
        pass
    else:
        raise AssertionError("bot blocking must not look like missing captions")


def test_bot_blocked_caption_is_distinct_manifest_deferred_reason():
    class BlockedClient:
        def list_playlist_items(self, channel_id, page_token=None, max_results=50):
            return {"items": [{
                "contentDetails": {"videoId": "AbCd_ef-123", "videoPublishedAt": "2026-09-20T14:00:00Z"},
                "snippet": {"channelId": channel_id, "resourceId": {"videoId": "AbCd_ef-123"}},
            }]}

        def list_videos(self, video_ids):
            channel = bridge.SITE_SPECS["CNA"]["channel_id"]
            return {"AbCd_ef-123": {"snippet": {"channelId": channel, "publishedAt": "2026-09-20T14:00:00Z", "liveBroadcastContent": "none"}, "contentDetails": {"duration": "PT1M"}, "status": {"privacyStatus": "public", "uploadStatus": "processed"}}}

        def get_captions(self, video_id, language, kind):
            raise bridge.CaptionFetchBlockedError("Sign in to confirm you're not a bot")

        def is_short(self, video_id):
            return False

    result = bridge.collect_manifest(
        site="CNA", checkpoint="0920-0430",
        cursor_data={"revision": 1, "sites": {"CNA": {"last_complete_end_utc": "2026-09-20T12:00:00Z"}}},
        state_data={"items": []}, client=BlockedClient(),
        collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    assert result["deferred"] == [{"video_id": "AbCd_ef-123", "reason": "caption-fetch-blocked", "id": "CNA-AbCd_ef-123"}]


def test_caption_language_and_kind_match_site_specs():
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        output_template = command[command.index("-o") + 1]
        language = command[command.index("--sub-lang") + 1]
        vtt = output_template.replace("%(id)s.%(ext)s", f"video.{language}.vtt")
        with open(vtt, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n00:00.000 --> 00:01.000\ncaption\n")
        return subprocess.CompletedProcess(command, 0, "", "")

    fetcher = bridge.YtDlpCaptionFetcher(runner=fake_run)
    for site in ("CNA", "YNA"):
        spec = bridge.SITE_SPECS[site]
        payload = fetcher.get_captions("video", spec["caption_language"], spec["caption_kind"])
        assert payload["language"] == spec["caption_language"]
        assert payload["kind"] == spec["caption_kind"]
        command = calls[-1]
        assert command[command.index("--sub-lang") + 1] == spec["caption_language"]


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("ALL PASS")


if __name__ == "__main__":
    main()
