#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D23：YNA／CNA YouTube → S2 add-batch bridge。

本模組把外部來源隔在兩個可重播的 CLI seam：

* ``collect``：只讀 state／cursor，抓完整窗口並產生 manifest，不寫入 state。
* ``finalize``：將 manifest 與人工 decisions 組成 add-batch wrapper；``--apply``
  時以按站鎖保護 add-batch，只有 state 成功後才原子推進 cursor。

Phase 0–5 僅使用 fixture。Phase 6 的人工沙箱可透過環境變數 API key 使用
YouTube Data API v3；字幕下載仍是獨立的授權／工具決策，不會由本模組暗中執行。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import s2_material_schema as schema


HERE = os.path.dirname(os.path.abspath(__file__))
UTC = timezone.utc

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
WINDOW_OVERLAP = timedelta(minutes=10)
DEFAULT_MAX_PLAYLIST_PAGES = 100
PUBLISHED_AT_TOLERANCE_SECONDS = 60

SITE_SPECS = {
    "CNA": {
        "channel_id": "UC83jt4dlz1Gjl58fzQrrKZg",
        "caption_language": "en",
        "caption_kind": "auto",
        "caption_precision": "source-auto",
    },
    "YNA": {
        "channel_id": "UCTHCOPwqNfZ0uiKOvFyhGwg",
        "caption_language": "zh-Hant",
        "caption_kind": "auto-translated",
        "caption_precision": "triage-only",
    },
}

SKIPPED_HHMM = frozenset({"0100", "2000"})
TAIWAN_REGION = "TW"
ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


class BridgeError(RuntimeError):
    """Blocking D23 bridge error; caller must not advance the cursor."""


class Phase6ExternalAccessBlocked(BridgeError):
    """Kept for callers which deliberately block an external integration."""


class FinalizeError(BridgeError):
    """Raised when a manifest cannot be safely converted into an apply-ready batch."""


class CursorConflict(BridgeError):
    """Raised when an old manifest would overwrite a newer cursor revision."""


class YtDlpNotFoundError(BridgeError):
    """Raised when the local yt-dlp executable cannot be started."""


class CaptionFetchBlockedError(BridgeError):
    """Raised when YouTube rejects yt-dlp as automated traffic."""


class YouTubeClient:
    """Small external boundary used by collect; tests inject a fake implementation."""

    def list_playlist_items(self, channel_id: str, page_token: Optional[str] = None,
                            max_results: int = 50) -> Mapping[str, Any]:
        raise NotImplementedError

    def list_videos(self, video_ids: list[str]) -> Mapping[str, Mapping[str, Any]]:
        raise NotImplementedError

    def get_captions(self, video_id: str, language: str, kind: str) -> Any:
        raise NotImplementedError

    def is_short(self, video_id: str) -> bool:
        raise NotImplementedError


class YtDlpCaptionFetcher:
    """Local yt-dlp adapter which returns the bridge's existing caption shape.

    ``runner`` is injectable so this boundary is fully testable without starting
    a process.  ``zh-Hant`` is deliberately passed through unchanged: it is the
    established YNA translated-caption language code in ``SITE_SPECS``.
    """

    BOT_BLOCK_MARKERS = (
        "sign in to confirm", "not a bot", "bot detection", "automated",
    )
    # HTTP 429 from yt-dlp is a WARNING, not a nonzero exit code — yt-dlp still
    # reports success for the surrounding metadata fetch. Left undetected, a
    # rate-limited request silently looks identical to "this video really has
    # no captions in this language" (2026-09-20 real-batch incident: most of a
    # 23-item YNA window was mis-deferred as caption-missing when the videos
    # had captions and were simply rate-limited by rapid back-to-back calls).
    RATE_LIMIT_MARKERS = ("429", "too many requests")

    def __init__(self, executable: str = "yt-dlp", *, runner: Any = None,
                 min_interval_seconds: float = 2.0, sleeper: Any = None):
        self._executable = executable
        self._runner = runner or subprocess.run
        self._min_interval_seconds = min_interval_seconds
        self._sleep = sleeper or time.sleep
        self._last_call_monotonic: Optional[float] = None

    @staticmethod
    def _segments_from_vtt(path: Path) -> list[dict[str, str]]:
        try:
            content = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            raise BridgeError(f"yt-dlp 字幕檔讀取失敗：{path.name}") from exc

        segments: list[dict[str, str]] = []
        previous_cue = ""
        for block in re.split(r"\r?\n\s*\r?\n", content):
            lines = [line.strip() for line in block.splitlines()]
            if not lines or lines[0].upper() == "WEBVTT" or lines[0].startswith(("NOTE", "STYLE", "REGION")):
                continue
            timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
            if timing_index is None:
                continue
            cue_lines = lines[timing_index + 1:]
            text = re.sub(r"<[^>]+>", "", " ".join(cue_lines))
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            # yt-dlp VTT frequently emits rolling cues ("Hello", then
            # "Hello world"). Keep only the newly revealed suffix.
            if previous_cue and text.startswith(previous_cue + " "):
                text = text[len(previous_cue):].strip()
            elif previous_cue and previous_cue.startswith(text):
                continue
            previous_cue = re.sub(r"\s+", " ", " ".join(cue_lines)).strip()
            if text and (not segments or text != segments[-1]["text"]):
                segments.append({"text": text})
        return segments

    def _throttle(self) -> None:
        if self._last_call_monotonic is None:
            return
        elapsed = time.monotonic() - self._last_call_monotonic
        remaining = self._min_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def get_captions(self, video_id: str, language: str, kind: str) -> Optional[dict[str, Any]]:
        self._throttle()
        self._last_call_monotonic = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="d23-ytdlp-") as directory:
            template = str(Path(directory) / "%(id)s.%(ext)s")
            command = [
                self._executable, "--skip-download", "--write-auto-sub", "--sub-lang", language,
                "--sub-format", "vtt", "--convert-subs", "vtt", "-o", template,
                f"https://www.youtube.com/watch?v={video_id}",
            ]
            try:
                result = self._runner(command, capture_output=True, text=True, check=False)
            except (FileNotFoundError, PermissionError) as exc:
                raise YtDlpNotFoundError("找不到或無法執行本機 yt-dlp；這不是字幕缺失") from exc
            stdout = _trim(getattr(result, "stdout", ""))
            stderr = _trim(getattr(result, "stderr", ""))
            diagnostic = f"{stdout}\n{stderr}".lower()
            # Checked before the exit-code gate: HTTP 429 leaves yt-dlp's
            # returncode at 0 (it only warns), so a returncode-only check would
            # never see it — see RATE_LIMIT_MARKERS docstring above.
            if any(marker in diagnostic for marker in self.BOT_BLOCK_MARKERS):
                raise CaptionFetchBlockedError("yt-dlp 被 YouTube bot 偵測阻擋，應稍後重試")
            if any(marker in diagnostic for marker in self.RATE_LIMIT_MARKERS):
                raise CaptionFetchBlockedError("yt-dlp 字幕下載被 YouTube 限流（HTTP 429），應稍後重試")
            if getattr(result, "returncode", 0) != 0:
                raise BridgeError(f"yt-dlp 取得字幕失敗（exit code {result.returncode}）")
            vtt_files = sorted(Path(directory).glob("*.vtt"))
            if not vtt_files:
                return None
            segments: list[dict[str, str]] = []
            for vtt_file in vtt_files:
                try:
                    segments.extend(self._segments_from_vtt(vtt_file))
                finally:
                    # Do not retain raw subtitle files beyond this one fetch.
                    try:
                        vtt_file.unlink()
                    except FileNotFoundError:
                        pass
            if not segments:
                return None
            return {"language": language, "kind": kind, "segments": segments}


class ProductionYouTubeClient(YouTubeClient):
    """YouTube Data API v3 boundary for the Phase 6 manual sandbox.

    The key is intentionally held only in memory and is never copied into a
    manifest, batch, log, or exception.  Subtitle download is delegated to the
    local ``yt-dlp`` adapter because the API key can only access metadata.
    """

    API_ROOT = "https://www.googleapis.com/youtube/v3"
    API_KEY_ENV = "YOUTUBE_API_KEY"

    def __init__(self, api_key: Optional[str] = None, *, timeout_seconds: int = 30,
                 caption_fetcher: Optional[YtDlpCaptionFetcher] = None):
        self._api_key = _trim(api_key if api_key is not None else os.environ.get(self.API_KEY_ENV))
        if not self._api_key:
            raise BridgeError(
                f"真實 YouTube collect 需要環境變數 {self.API_KEY_ENV}；"
                "未設定時請改用 --fixture-dir，且不會自動降級。"
            )
        self._timeout_seconds = timeout_seconds
        self._caption_fetcher = caption_fetcher or YtDlpCaptionFetcher()

    def _request_json(self, resource: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        query = dict(params)
        query["key"] = self._api_key
        url = f"{self.API_ROOT}/{resource}?{urlencode(query)}"
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}),
                         timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise BridgeError(f"YouTube Data API {resource} 請求失敗：HTTP {exc.code}") from exc
        except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            # Do not expose ``exc``: urllib errors can include the request URL,
            # which contains the API key query parameter.
            raise BridgeError(f"YouTube Data API {resource} 請求失敗（網路或回應格式）") from exc
        if not isinstance(payload, Mapping):
            raise BridgeError(f"YouTube Data API {resource} 回應不是 JSON 物件")
        return payload

    @staticmethod
    def _uploads_playlist_id(channel_id: str) -> str:
        # playlistItems.list takes a playlistId, not a channelId. The channel's
        # uploads playlist follows YouTube's documented convention of swapping
        # the "UC" channel-ID prefix for "UU"; there is no separate API call
        # needed to look this up.
        trimmed = _trim(channel_id)
        if not trimmed.startswith("UC"):
            raise BridgeError(f"channel_id 不是預期的 UC 前綴，無法推導上傳播放清單：{channel_id!r}")
        return "UU" + trimmed[2:]

    def list_playlist_items(self, channel_id, page_token=None, max_results=50):
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": self._uploads_playlist_id(channel_id),
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        return self._request_json("playlistItems", params)

    def list_videos(self, video_ids):
        if not video_ids:
            return {}
        payload = self._request_json("videos", {
            "part": "snippet,contentDetails,status,liveStreamingDetails",
            "id": ",".join(video_ids),
        })
        rows = payload.get("items")
        if not isinstance(rows, list):
            raise BridgeError("YouTube Data API videos 回應缺少 items")
        return {
            _trim(row.get("id")): row
            for row in rows
            if isinstance(row, Mapping) and _trim(row.get("id"))
        }

    def get_captions(self, video_id, language, kind):
        return self._caption_fetcher.get_captions(video_id, language, kind)

    SHORTS_URL_ROOT = "https://www.youtube.com/shorts/"

    def is_short(self, video_id):
        # YouTube Data API v3 has no isShort field. Ask youtube.com/shorts/<id>
        # directly: a real Short serves that URL as-is, a normal video 302s to
        # /watch. Best-effort only — network failure here must not block an
        # otherwise-valid item, so the caller treats BridgeError as "unknown".
        url = f"{self.SHORTS_URL_ROOT}{video_id}"
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                         timeout=self._timeout_seconds) as response:
                final_url = response.geturl()
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise BridgeError(f"YouTube shorts 頁面檢查失敗：HTTP {exc.code}") from exc
        except (URLError, OSError) as exc:
            raise BridgeError("YouTube shorts 頁面檢查失敗（網路）") from exc
        return "/shorts/" in final_url


class FixtureYouTubeClient(YouTubeClient):
    """Offline adapter for the sanitized Phase 0 JSON fixtures."""

    def __init__(self, fixture_dir: str, site: str):
        self.root = Path(fixture_dir)
        self.site = site.upper()
        self._videos = self._load_json("videos_join.json")
        self._captions = self._load_json("captions.json")
        self._shorts = self._load_json_optional("shorts.json") or []

    def _load_json(self, name: str) -> Any:
        try:
            with (self.root / name).open(encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError(f"fixture 讀取失敗：{self.root / name}（{exc}）") from exc

    def _load_json_optional(self, name: str) -> Any:
        # Older Phase 0 fixture directories predate the Shorts exclusion and
        # simply don't have this file; treat that as "no known shorts", not
        # an error.
        path = self.root / name
        if not path.exists():
            return None
        return self._load_json(name)

    def _playlist_file(self, page_token: Optional[str]) -> Path:
        if self.site == "CNA":
            suffix = "1" if not page_token else page_token.rsplit("-", 1)[-1]
            return self.root / f"cna_playlist_page{suffix}.json"
        return self.root / "yna_playlist_page1.json"

    def list_playlist_items(self, channel_id, page_token=None, max_results=50):
        path = self._playlist_file(page_token)
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeError(f"playlist fixture 讀取失敗：{path}（{exc}）") from exc

    def list_videos(self, video_ids):
        rows = self._videos.get("items", []) if isinstance(self._videos, dict) else []
        by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
        return {video_id: by_id[video_id] for video_id in video_ids if video_id in by_id}

    def get_captions(self, video_id, language, kind):
        return self._captions.get(f"{self.site}:{video_id}")

    def is_short(self, video_id):
        return video_id in self._shorts


def _trim(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_utc(value: Any, field: str) -> datetime:
    raw = _trim(value)
    if not raw:
        raise BridgeError(f"{field} 缺值")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BridgeError(f"{field} 不是合法 ISO-8601 timestamp：{value!r}") from exc
    if parsed.tzinfo is None:
        raise BridgeError(f"{field} 必須含 timezone：{value!r}")
    return parsed.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def checkpoint_is_skipped(checkpoint: str) -> bool:
    if schema.CHECKPOINT_RE.fullmatch(_trim(checkpoint)) is None:
        raise BridgeError(f"checkpoint 須為 MMDD-HHMM：{checkpoint!r}")
    return checkpoint[-4:] in SKIPPED_HHMM


def material_id(site: str, video_id: str) -> str:
    site = _trim(site).upper()
    raw = f"{site}-{video_id}"
    canonical, issue = schema.validate_material_id_for_write(raw, site)
    if issue:
        raise BridgeError(f"YouTube videoId 不符合 {site} ID schema：{issue.message}")
    return canonical


def parse_duration(value: Any) -> Optional[int]:
    """Parse ISO-8601 video duration; unknown stays None instead of 00:00."""
    raw = _trim(value)
    if not raw:
        return None
    match = ISO_DURATION_RE.fullmatch(raw)
    if not match:
        return None
    seconds = (
        float(match.group("days") or 0) * 86400
        + float(match.group("hours") or 0) * 3600
        + float(match.group("minutes") or 0) * 60
        + float(match.group("seconds") or 0)
    )
    return int(round(seconds))


def format_duration(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def normalize_caption(payload: Any) -> Optional[str]:
    """Collapse timestamped segments and consecutive rolling-caption duplicates."""
    if isinstance(payload, str):
        raw_lines = payload.splitlines()
    elif isinstance(payload, Mapping):
        segments = payload.get("segments")
        if isinstance(segments, list):
            raw_lines = [seg.get("text", "") for seg in segments if isinstance(seg, Mapping)]
        else:
            raw_lines = [payload.get("text", "")]
    else:
        return None

    out: list[str] = []
    for raw in raw_lines:
        text = re.sub(r"\s+", " ", _trim(raw))
        if not text or (out and text == out[-1]):
            continue
        out.append(text)
    return "\n".join(out) or None


def _caption_meta(payload: Any, spec: Mapping[str, str]) -> Optional[dict[str, str]]:
    if not isinstance(payload, Mapping):
        return None
    language = _trim(payload.get("language"))
    kind = _trim(payload.get("kind"))
    if language != spec["caption_language"] or kind != spec["caption_kind"]:
        return None
    return {
        "language": language,
        "kind": kind,
        "precision": spec["caption_precision"],
    }


def _playlist_video_id(row: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    content = row.get("contentDetails") if isinstance(row.get("contentDetails"), Mapping) else {}
    snippet = row.get("snippet") if isinstance(row.get("snippet"), Mapping) else {}
    primary = _trim(content.get("videoId"))
    fallback = _trim((snippet.get("resourceId") or {}).get("videoId")) \
        if isinstance(snippet.get("resourceId"), Mapping) else ""
    if primary and fallback and primary != fallback:
        raise BridgeError(f"playlist item videoId 不一致：contentDetails={primary!r} resourceId={fallback!r}")
    return primary or fallback or None, ("fallback" if not primary and fallback else None)


def _empty_counts() -> dict[str, int]:
    return {
        "playlist_pages": 0, "playlist_items_seen": 0, "window_total": 0,
        "ready": 0, "skipped": 0, "dropped": 0, "deferred": 0, "accounted": 0,
    }


def _state_item_ids(state_data: Any) -> set[str]:
    if not isinstance(state_data, Mapping):
        return set()
    items = state_data.get("items", [])
    if isinstance(items, Mapping):
        rows = [{"id": key, **(value if isinstance(value, Mapping) else {})}
                for key, value in items.items()]
    elif isinstance(items, list):
        rows = [row for row in items if isinstance(row, Mapping)]
    else:
        rows = []
    return {_trim(row.get("id")) for row in rows if _trim(row.get("id"))}


def _site_cursor(cursor_data: Any, site: str) -> tuple[dict[str, Any], Any]:
    if not isinstance(cursor_data, Mapping):
        raise BridgeError("cursor 必須是 JSON 物件")
    sites = cursor_data.get("sites")
    if not isinstance(sites, Mapping) or not isinstance(sites.get(site), Mapping):
        return {}, cursor_data.get("revision")
    return dict(sites[site]), cursor_data.get("revision")


def _fetch_playlist(client: YouTubeClient, site: str, lower: datetime,
                    max_pages: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, list[dict[str, Any]]]:
    spec = SITE_SPECS[site]
    rows: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    page_token = None
    seen_tokens: set[str] = set()
    crossed_lower = False
    for page_number in range(1, max_pages + 1):
        if page_token and page_token in seen_tokens:
            raise BridgeError(f"{site} playlist nextPageToken 重複，窗口不完整")
        if page_token:
            seen_tokens.add(page_token)
        payload = client.list_playlist_items(spec["channel_id"], page_token, max_results=50)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
            raise BridgeError(f"{site} playlist 回應缺少 items，窗口不完整")
        pages.append(dict(payload))
        for raw in payload["items"]:
            if not isinstance(raw, Mapping):
                dropped.append({"reason": "playlist-row-not-object", "raw": raw})
                continue
            try:
                video_id, id_note = _playlist_video_id(raw)
            except BridgeError:
                raise
            if not video_id:
                dropped.append({"reason": "missing-video-id", "raw": dict(raw)})
                continue
            snippet = raw.get("snippet") if isinstance(raw.get("snippet"), Mapping) else {}
            if _trim(snippet.get("channelId")) != spec["channel_id"]:
                raise BridgeError(
                    f"{site} playlist channel ID 不符：{snippet.get('channelId')!r}"
                )
            content = raw.get("contentDetails") if isinstance(raw.get("contentDetails"), Mapping) else {}
            published_raw = content.get("videoPublishedAt")
            published = None
            if published_raw:
                try:
                    published = parse_utc(published_raw, "playlist videoPublishedAt")
                except BridgeError as exc:
                    rows.append({"video_id": video_id, "raw": dict(raw), "published": None,
                                 "published_error": str(exc), "id_note": id_note})
                    continue
            if published is not None and published <= lower:
                crossed_lower = True
            rows.append({"video_id": video_id, "raw": dict(raw), "published": published,
                         "id_note": id_note})
        page_token = _trim(payload.get("nextPageToken")) or None
        if crossed_lower or not page_token:
            break
    else:
        raise BridgeError(
            f"{site} playlist 超過安全頁數上限 {max_pages}，尚未越過窗口下界；游標不得前進"
        )
    return rows, pages, len(pages), dropped


def _dedupe_playlist(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        video_id = row["video_id"]
        if video_id in seen:
            warnings.append({"video_id": video_id, "reason": "duplicate-playlist-id"})
            continue
        seen.add(video_id)
        unique.append(row)
    return unique, warnings


def _chunks(values: list[str], size: int = 50):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _metadata_join(client: YouTubeClient, video_ids: list[str]) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]]]:
    joined: dict[str, Mapping[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    for batch in _chunks(video_ids, 50):
        result = client.list_videos(batch)
        if not isinstance(result, Mapping):
            raise BridgeError("videos.list 回應不是物件，join 不完整")
        snapshots.append({"requested_ids": list(batch), "items": dict(result)})
        for video_id, row in result.items():
            if isinstance(row, Mapping):
                joined[str(video_id)] = row
    return joined, snapshots


def _deferred(video_id: str, reason: str, **extra: Any) -> dict[str, Any]:
    out = {"video_id": video_id, "reason": reason}
    out.update(extra)
    return out


def _is_blocked_in_taiwan(content_details: Mapping[str, Any]) -> bool:
    """regionRestriction never resolves itself; treat it as a permanent exclusion,
    not a retry-able deferral (D23 裁決：台灣看不到 = 直接排除，不進 deferred 佇列重打)."""
    restriction = content_details.get("regionRestriction")
    if not isinstance(restriction, Mapping):
        return False
    allowed = restriction.get("allowed")
    if isinstance(allowed, list) and TAIWAN_REGION not in allowed:
        return True
    blocked = restriction.get("blocked")
    if isinstance(blocked, list) and TAIWAN_REGION in blocked:
        return True
    return False


def collect_manifest(*, site: str, checkpoint: str, cursor_data: Mapping[str, Any],
                     state_data: Mapping[str, Any], client: YouTubeClient,
                     collect_started_at_utc: Optional[str] = None,
                     bootstrap_start_utc: Optional[str] = None,
                     max_pages: int = DEFAULT_MAX_PLAYLIST_PAGES) -> dict[str, Any]:
    site = _trim(site).upper()
    if site not in SITE_SPECS:
        raise BridgeError(f"site 只接受 CNA/YNA：{site!r}")
    if schema.CHECKPOINT_RE.fullmatch(_trim(checkpoint)) is None:
        raise BridgeError(f"checkpoint 須為 MMDD-HHMM：{checkpoint!r}")
    started = parse_utc(collect_started_at_utc or iso_utc(datetime.now(UTC)), "collect_started_at_utc")
    spec = SITE_SPECS[site]
    site_cursor, revision = _site_cursor(cursor_data, site)
    counts = _empty_counts()
    base = {
        "schema_version": 1,
        "status": "complete",
        "site": site,
        "checkpoint": checkpoint,
        "collect_started_at_utc": iso_utc(started),
        "cursor_revision": revision,
        "items": [],
        "skipped": [],
        "dropped": [],
        "deferred": [],
        "warnings": [],
        "counts": counts,
    }
    if checkpoint_is_skipped(checkpoint):
        base["status"] = "skipped"
        base["skip_reason"] = "本輪不掃 CNA／YNA（D23）"
        return base

    last_raw = site_cursor.get("last_complete_end_utc")
    if last_raw:
        last_end = parse_utc(last_raw, f"{site}.last_complete_end_utc")
    elif bootstrap_start_utc:
        last_end = parse_utc(bootstrap_start_utc, "bootstrap_start_utc")
    else:
        raise BridgeError(f"{site} 沒有成功游標；首次 collect 必須明帶 bootstrap_start_utc")
    lower = last_end - WINDOW_OVERLAP
    rows, pages, page_count, early_dropped = _fetch_playlist(
        client, site, lower, max_pages
    )
    counts["playlist_pages"] = page_count
    counts["playlist_items_seen"] = sum(
        len(page.get("items", [])) for page in pages if isinstance(page, Mapping)
    )
    base["window"] = {
        "lower_exclusive": iso_utc(lower),
        "upper_inclusive": iso_utc(started),
        "overlap_minutes": 10,
    }
    unique, warnings = _dedupe_playlist(rows)
    base["warnings"].extend(warnings)
    base["dropped"].extend(early_dropped)
    state_ids = _state_item_ids(state_data)
    recent_ids = {_trim(x) for x in site_cursor.get("recent_video_ids", []) if _trim(x)}
    deferred_ids = {_trim(x) for x in site_cursor.get("deferred_video_ids", []) if _trim(x)}

    # A deferred video can fall out of the moving playlist window.  Retry it through
    # videos.list anyway; otherwise a missing caption or transient join can never recover.
    seen_playlist_ids = {row["video_id"] for row in unique}
    for video_id in sorted(deferred_ids - seen_playlist_ids):
        unique.append({
            "video_id": video_id,
            "raw": {},
            "published": None,
            "id_note": "deferred-retry",
            "deferred_retry": True,
        })
    candidates: list[dict[str, Any]] = []
    for row in unique:
        published = row.get("published")
        is_deferred_retry = bool(row.get("deferred_retry"))
        if not is_deferred_retry and published is not None and published > started:
            base["warnings"].append({"video_id": row["video_id"], "reason": "future-published-item"})
            continue
        if not is_deferred_retry and published is not None and published <= lower:
            continue
        candidates.append(row)

    window_candidate_ids: set[str] = set()
    for row in candidates:
        mid = material_id(site, row["video_id"])
        window_candidate_ids.add(row["video_id"])
        if mid in state_ids:
            base["skipped"].append({"video_id": row["video_id"], "id": mid,
                                     "reason": "already-in-state"})
            continue
        if row["video_id"] in recent_ids and row["video_id"] not in deferred_ids:
            base["skipped"].append({"video_id": row["video_id"], "id": mid,
                                     "reason": "recent-video-id"})
            continue
        # deferred IDs are deliberately retried; they must not be filtered by recent_ids.

    # Keep a separate list after state/recent filtering; the odd-looking two-pass shape above
    # is intentionally avoided in the actual join list so captions are never fetched for skips.
    join_rows = []
    for row in candidates:
        mid = material_id(site, row["video_id"])
        if mid in state_ids:
            continue
        if row["video_id"] in recent_ids and row["video_id"] not in deferred_ids:
            continue
        join_rows.append(row)

    join_ids = [row["video_id"] for row in join_rows]
    joined, video_snapshots = _metadata_join(client, join_ids)
    base["raw"] = {"playlist_pages": pages, "videos_batches": video_snapshots}

    for row in join_rows:
        video_id = row["video_id"]
        mid = material_id(site, video_id)
        metadata = joined.get(video_id)
        if metadata is None:
            base["deferred"].append(_deferred(video_id, "metadata-missing", id=mid))
            continue
        snippet = metadata.get("snippet") if isinstance(metadata.get("snippet"), Mapping) else {}
        if _trim(snippet.get("channelId")) != spec["channel_id"]:
            raise BridgeError(
                f"{site} videos channel ID 不符：video={video_id!r} channel={snippet.get('channelId')!r}"
            )
        if row.get("published_error"):
            base["deferred"].append(_deferred(
                video_id, "published-at-invalid", id=mid, detail=row["published_error"]
            ))
            continue
        playlist_published = row.get("published")
        metadata_published = None
        if snippet.get("publishedAt"):
            try:
                metadata_published = parse_utc(snippet["publishedAt"], "videos.snippet.publishedAt")
            except BridgeError as exc:
                base["warnings"].append({"video_id": video_id, "reason": str(exc)})
        published = playlist_published or metadata_published
        if published is None:
            base["deferred"].append(_deferred(
                video_id, "published-at-invalid", id=mid, detail=row.get("published_error")
            ))
            continue
        if playlist_published and metadata_published:
            delta = abs((playlist_published - metadata_published).total_seconds())
            if delta > PUBLISHED_AT_TOLERANCE_SECONDS:
                base["warnings"].append({
                    "video_id": video_id, "reason": "published-at-needs-review",
                    "delta_seconds": delta,
                })
        is_deferred_retry = bool(row.get("deferred_retry"))
        if not is_deferred_retry and not (published > lower and published <= started):
            continue
        counts["window_total"] += 1
        status = metadata.get("status") if isinstance(metadata.get("status"), Mapping) else {}
        privacy = _trim(status.get("privacyStatus"))
        upload_status = _trim(status.get("uploadStatus"))
        if privacy != "public" or upload_status not in ("processed", "uploaded"):
            base["deferred"].append(_deferred(
                video_id, "video-not-public-or-processed", id=mid,
                privacy_status=privacy, upload_status=upload_status,
            ))
            continue
        content_details = metadata.get("contentDetails") if isinstance(metadata.get("contentDetails"), Mapping) else {}
        if _is_blocked_in_taiwan(content_details):
            base["skipped"].append({
                "video_id": video_id, "id": mid, "reason": "region-restricted",
                "region_restriction": dict(content_details.get("regionRestriction") or {}),
            })
            continue
        live_content = _trim(snippet.get("liveBroadcastContent")) or "none"
        live_streaming_details = metadata.get("liveStreamingDetails")
        was_ever_live = isinstance(live_streaming_details, Mapping) and bool(
            _trim(live_streaming_details.get("actualStartTime"))
        )
        if live_content != "none" or was_ever_live:
            # D23 裁決：直播（含已結束、事後變成一般 VOD 的往日直播錄影）一律不收，
            # 這是永久狀態不會靠重試改變，所以歸 skipped 而非 deferred。
            base["skipped"].append({
                "video_id": video_id, "id": mid, "reason": "livestream-excluded",
                "live_broadcast_content": live_content, "was_ever_live": was_ever_live,
            })
            continue
        try:
            is_short = client.is_short(video_id)
        except BridgeError as exc:
            base["warnings"].append({"video_id": video_id, "reason": f"shorts-check-failed: {exc}"})
            is_short = False
        if is_short:
            # D23 裁決：Shorts 一律不收；跟直播一樣是永久狀態，歸 skipped 不進 deferred 重試佇列。
            base["skipped"].append({"video_id": video_id, "id": mid, "reason": "short-excluded"})
            continue
        duration_seconds = parse_duration(
            (metadata.get("contentDetails") or {}).get("duration")
            if isinstance(metadata.get("contentDetails"), Mapping) else None
        )
        try:
            caption_payload = client.get_captions(
                video_id, spec["caption_language"], spec["caption_kind"]
            )
        except CaptionFetchBlockedError:
            base["deferred"].append(_deferred(
                video_id, "caption-fetch-blocked", id=mid
            ))
            continue
        caption_text = normalize_caption(caption_payload)
        caption_meta = _caption_meta(caption_payload, spec)
        if not caption_text or caption_meta is None:
            base["deferred"].append(_deferred(
                video_id, "caption-missing-or-wrong-track", id=mid,
                expected_language=spec["caption_language"], expected_kind=spec["caption_kind"],
            ))
            continue
        platform = {
            "site": site,
            "provider": "YouTube",
            "video_id": video_id,
            "channel_id": spec["channel_id"],
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at_utc": iso_utc(published),
            "duration_seconds": duration_seconds,
            "caption": caption_meta,
        }
        ready = {
            "id": mid,
            "site": site,
            "video_id": video_id,
            "published_at_utc": iso_utc(published),
            "title": _trim(snippet.get("title")) or _trim((row.get("raw") or {}).get("snippet", {}).get("title")),
            "description": _trim(snippet.get("description")),
            "duration_seconds": duration_seconds,
            "duration": format_duration(duration_seconds),
            "src_text": caption_text,
            "platform": platform,
            "status": "ready",
        }
        base["items"].append(ready)

    counts["ready"] = len(base["items"])
    counts["skipped"] = len(base["skipped"])
    counts["dropped"] = len(base["dropped"])
    counts["deferred"] = len(base["deferred"])
    # Playlist rows without a timestamp are conservatively treated as in-window until metadata
    # resolves them; metadata failures therefore remain accounted instead of vanishing.
    counts["window_total"] = len(window_candidate_ids) + len(base["dropped"])
    counts["accounted"] = counts["ready"] + counts["skipped"] + counts["dropped"] + counts["deferred"]
    if counts["accounted"] != counts["window_total"]:
        raise BridgeError(
            f"{site} manifest 對帳失敗：window_total={counts['window_total']} "
            f"accounted={counts['accounted']}"
        )
    base["deferred_video_ids"] = sorted({x["video_id"] for x in base["deferred"]})
    return base


def _decision_topics(decisions: Mapping[str, Any]) -> dict[str, Any]:
    old_key = decisions.get("_new_topics", None)
    new_key = decisions.get("new_topics", None)
    if old_key is not None and not isinstance(old_key, Mapping):
        raise FinalizeError("decisions 的 _new_topics 必須是物件")
    if new_key is not None and not isinstance(new_key, Mapping):
        raise FinalizeError("decisions 的 new_topics 必須是物件")
    if old_key is not None and new_key is not None and dict(old_key) != dict(new_key):
        raise FinalizeError("decisions 同時有 _new_topics 與 new_topics 且內容不一致")
    return dict(old_key if old_key is not None else (new_key or {}))


def _validate_decision_shape(material_id_value: str, decision: Mapping[str, Any]) -> tuple[str, Any]:
    if not isinstance(decision, Mapping):
        raise FinalizeError(f"{material_id_value} decision 必須是物件")
    has_entry = isinstance(decision.get("entry"), str) and bool(decision["entry"].strip())
    has_skip = isinstance(decision.get("skip"), str) and bool(decision["skip"].strip())
    if has_entry == has_skip:
        raise FinalizeError(f"{material_id_value} 必須恰有非空 entry 或非空 skip")
    if has_skip:
        return "skip", decision["skip"].strip()
    entry = decision["entry"]
    if not (entry == material_id_value or entry.startswith(material_id_value + " ")):
        raise FinalizeError(f"{material_id_value} entry 首碼必須完全一致")
    return "entry", entry


def _manifest_counts(manifest: Mapping[str, Any]) -> dict[str, int]:
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), Mapping) else {}
    return {key: int(counts.get(key, 0) or 0) for key in
            ("window_total", "ready", "skipped", "dropped", "deferred", "accounted")}


def finalize_manifest(manifest: Mapping[str, Any], decisions: Mapping[str, Any]) -> dict[str, Any]:
    """Pure manifest + decisions preflight returning an add-batch wrapper."""
    if not isinstance(manifest, Mapping):
        raise FinalizeError("manifest 必須是 JSON 物件")
    if not isinstance(decisions, Mapping):
        raise FinalizeError("decisions 必須是 keyed object，不接受裸陣列")
    site = _trim(manifest.get("site")).upper()
    checkpoint = _trim(manifest.get("checkpoint"))
    if site not in SITE_SPECS:
        raise FinalizeError(f"manifest site 不合法：{site!r}")
    if schema.CHECKPOINT_RE.fullmatch(checkpoint) is None:
        raise FinalizeError(f"manifest checkpoint 不合法：{checkpoint!r}")
    if manifest.get("status") == "skipped":
        ready_items = []
    else:
        ready_items = manifest.get("items")
        if not isinstance(ready_items, list):
            raise FinalizeError("manifest items 必須是陣列")
    dropped = manifest.get("dropped") or []
    if dropped:
        raise FinalizeError(f"manifest 有 {len(dropped)} 則 dropped，禁止產生 apply-ready batch")
    manifest_skipped = manifest.get("skipped") or []
    deferred = manifest.get("deferred") or []
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in ready_items:
        if not isinstance(item, Mapping):
            raise FinalizeError("manifest items 含非物件")
        item_id = _trim(item.get("id"))
        if not item_id or item_id in by_id:
            raise FinalizeError(f"manifest ready ID 缺值或重複：{item_id!r}")
        video_id = _trim(item.get("video_id"))
        if not video_id:
            raise FinalizeError(f"manifest {item_id} 缺 video_id")
        expected_id = material_id(site, video_id)
        if item_id != expected_id:
            raise FinalizeError(f"manifest {item_id} source/ID 不一致（應為 {expected_id}）")
        issue = schema.validate_source_for_write(item_id, site)
        if issue:
            raise FinalizeError(issue.message)
        if not isinstance(item.get("src_text"), str) or not item["src_text"].strip():
            raise FinalizeError(f"manifest {item_id} 缺非空 src_text")
        if not isinstance(item.get("platform"), Mapping) or not item["platform"]:
            raise FinalizeError(f"manifest {item_id} 缺 platform provenance")
        by_id[item_id] = item

    reserved = {"_new_topics", "new_topics"}
    unknown = sorted(set(decisions) - set(by_id) - reserved)
    if unknown:
        raise FinalizeError(f"decisions 有不在 manifest 的 ID：{', '.join(unknown)}")
    topics = _decision_topics(decisions)
    batch_entries: list[dict[str, Any]] = []
    decision_skips: list[dict[str, str]] = []
    for item_id, item in by_id.items():
        if item_id not in decisions:
            raise FinalizeError(f"ready item 未有 decisions：{item_id}")
        kind, value = _validate_decision_shape(item_id, decisions[item_id])
        if kind == "skip":
            decision_skips.append({"id": item_id, "reason": value})
            continue
        decision = decisions[item_id]
        row = {
            "id": item_id,
            "source": site,
            "checkpoint": checkpoint,
            "status": "has_script",
            "entry": value,
            "src_text": item["src_text"],
            "platform": dict(item["platform"]),
        }
        for key in ("category", "tc"):
            if key in decision and decision[key] is not None:
                row[key] = decision[key]
        if isinstance(item.get("sb_count"), int):
            row["sb_count"] = item["sb_count"]
        batch_entries.append(row)

    counts = _manifest_counts(manifest)
    expected = len(by_id) + len(manifest_skipped) + len(deferred)
    accounted = len(batch_entries) + len(decision_skips) + len(manifest_skipped) + len(deferred)
    if counts["dropped"]:
        raise FinalizeError("manifest dropped 非零")
    if counts["window_total"] and expected != counts["window_total"]:
        raise FinalizeError(
            f"manifest counts 不一致：window_total={counts['window_total']} "
            f"ready+skipped+deferred={expected}"
        )
    if accounted != expected:
        raise FinalizeError(f"finalize 對帳失敗：accounted={accounted} expected={expected}")
    return {
        "entries": batch_entries,
        "new_topics": topics,
        "receipt": {
            "schema_version": 1,
            "site": site,
            "checkpoint": checkpoint,
            "ready": len(by_id),
            "batch": len(batch_entries),
            "skipped": decision_skips,
            "manifest_skipped": list(manifest_skipped),
            "deferred": list(deferred),
            "dropped": list(dropped),
            "accounted": accounted,
        },
    }


def _cursor_path(args: argparse.Namespace) -> str:
    if args.cursor:
        return args.cursor
    if not args.file:
        raise FinalizeError("apply 必須明帶 --cursor，或提供 --file 讓 bridge 推導游標路徑")
    return os.path.join(os.path.dirname(os.path.abspath(args.file)), "s2-youtube-cursors.json")


def _verify_applied_state(state_path: str, entries: list[Mapping[str, Any]]) -> None:
    state = read_json(state_path)
    items = state.get("items", []) if isinstance(state, Mapping) else []
    if isinstance(items, list):
        by_id = {row.get("id"): row for row in items if isinstance(row, Mapping)}
    elif isinstance(items, Mapping):
        by_id = {key: value for key, value in items.items()}
    else:
        by_id = {}
    missing = [row.get("id") for row in entries if row.get("id") not in by_id]
    if missing:
        raise BridgeError(f"add-batch rc=0 但 state 缺少預期素材：{missing}")
    for row in entries:
        stored = by_id[row["id"]]
        if stored.get("source") != row["source"] or stored.get("src_text") != row["src_text"]:
            raise BridgeError(f"add-batch 後 state 欄位不符：{row['id']}")
        if stored.get("platform") != row.get("platform"):
            raise BridgeError(f"add-batch 後 platform provenance 不符：{row['id']}")


def _finalize_command(args: argparse.Namespace) -> int:
    manifest = read_json(args.manifest)
    decisions = read_json(args.entries)
    wrapper = finalize_manifest(manifest, decisions)
    # 3.7（訂正版）：手動觸發（未帶 --in-round）一律禁止 --apply，不論掃帶鎖是否存在——
    # state 沒有檔案鎖，只有排定輪次自己持有 .s2-scan.lock 時的單一寫入窗口才准直接套用。
    # 手動觸發只能產候選 batch（見下方 not args.apply 分支），交排定輪次的 --in-round 呼叫代套用。
    if args.apply and not args.in_round:
        raise FinalizeError(
            "--apply 只能由排定輪次的 --in-round 呼叫使用；手動觸發請省略 --apply，"
            "產出的候選 batch 檔另存到 _待整併/ 目錄，由下一個排定輪次代為套用（計畫書 3.7）"
        )
    if args.apply and not args.file:
        raise FinalizeError("--apply 必須明帶 --file，禁止猜正式 state 路徑")
    if not args.apply:
        write_json_no_overwrite(args.out, wrapper)
        print(json.dumps(wrapper["receipt"], ensure_ascii=False))
        return 0

    # --in-round：排定輪次自己的鎖窗口內執行，單一寫入者，不需要另外的按站鎖檔。
    cursor_path = _cursor_path(args)
    pending = _collect_pending_candidates(args.pending_dir, manifest["site"]) if args.pending_dir else []
    combined_entries = list(wrapper["entries"])
    for cand in pending:
        combined_entries.extend(cand["wrapper"].get("entries", []))
    current_cursor = load_cursor(cursor_path)
    next_cursor = None
    if manifest.get("status") != "skipped":
        next_cursor = advance_cursor(current_cursor, manifest)
    write_json_no_overwrite(args.out, wrapper)
    if combined_entries:
        combined_path = args.out + ".combined.json"
        write_json_no_overwrite(combined_path, {"entries": combined_entries, "new_topics": wrapper.get("new_topics", {})})
        cmd = [sys.executable, os.path.join(HERE, "s2_state.py"), "--file", args.file]
        if args.registry:
            cmd += ["--registry", args.registry]
        cmd += ["add-batch", "--entries", combined_path]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        result = __import__("subprocess").run(cmd, capture_output=True, env=env)
        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            raise BridgeError(f"s2_state.py add-batch 失敗，游標不得前進（rc={result.returncode}）")
        _verify_applied_state(args.file, combined_entries)
    # 候選檔只在整批 add-batch 成功後才歸檔；套用失敗的候選檔原樣保留，下一輪重試。
    for cand in pending:
        _archive_pending_candidate(cand["path"])
    if manifest.get("status") != "skipped":
        save_cursor_atomic(
            cursor_path, next_cursor, expected_revision=current_cursor["revision"]
        )
    print(json.dumps(wrapper["receipt"], ensure_ascii=False))
    return 0


def _collect_pending_candidates(pending_dir: str, site: str) -> list[dict[str, Any]]:
    """掃 `_待整併/` 找這一站尚未套用的候選 batch（3.7）。檔名慣例：
    `{MMDD}-YNA_CNA候選*-{site}*.json`；讀不到／非本 bridge 產出格式的檔案直接跳過，
    不得讓別人放在同一目錄的其他候選檔（如 17-網址素材整併.md 的人工 .txt）誤觸發。
    """
    if not os.path.isdir(pending_dir):
        return []
    found: list[dict[str, Any]] = []
    for name in sorted(os.listdir(pending_dir)):
        if not name.lower().endswith(".json"):
            continue
        if site.upper() not in name.upper():
            continue
        path = os.path.join(pending_dir, name)
        try:
            data = read_json(path)
        except BridgeError:
            continue
        if not isinstance(data, Mapping) or "entries" not in data:
            continue
        found.append({"path": path, "wrapper": data})
    return found


def _archive_pending_candidate(path: str) -> None:
    parent = os.path.dirname(path)
    archive_dir = os.path.join(parent, "已整併")
    os.makedirs(archive_dir, exist_ok=True)
    dest = os.path.join(archive_dir, os.path.basename(path))
    try:
        os.replace(path, dest)
    except OSError:
        pass


def read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError(f"JSON 讀取失敗：{path}（{exc}）") from exc


def write_json_no_overwrite(path: str, data: Any) -> None:
    if os.path.exists(path):
        raise BridgeError(f"輸出已存在，預設拒絕覆寫：{path}")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def empty_cursor() -> dict[str, Any]:
    return {"schema_version": 1, "revision": 0, "sites": {}}


def load_cursor(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return empty_cursor()
    data = read_json(path)
    if not isinstance(data, Mapping) or data.get("schema_version") != 1:
        raise CursorConflict(f"cursor schema 不支援：{path}")
    try:
        revision = int(data.get("revision", 0))
    except (TypeError, ValueError) as exc:
        raise CursorConflict(f"cursor revision 不合法：{path}") from exc
    sites = data.get("sites")
    if not isinstance(sites, Mapping):
        raise CursorConflict(f"cursor sites 不合法：{path}")
    return {"schema_version": 1, "revision": revision,
            "sites": {str(key): dict(value) for key, value in sites.items()
                       if isinstance(value, Mapping)}}


def save_cursor_atomic(path: str, cursor_data: Mapping[str, Any], expected_revision: int) -> int:
    """Compare current revision, then atomically write revision+1; return new revision."""
    current = load_cursor(path)
    actual = int(current.get("revision", 0))
    if actual != int(expected_revision):
        raise CursorConflict(
            f"cursor revision 過期：expected={expected_revision} actual={actual}，拒絕覆蓋"
        )
    payload = json.loads(json.dumps(cursor_data, ensure_ascii=False))
    payload["schema_version"] = 1
    payload["revision"] = actual + 1
    if not isinstance(payload.get("sites"), dict):
        raise CursorConflict("cursor sites 必須是物件")
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise CursorConflict(f"cursor 原子寫入失敗：{path}（{exc}）") from exc
    return payload["revision"]


def _manifest_video_ids(manifest: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    seen: list[str] = []
    for key in ("items", "skipped"):
        for row in manifest.get(key) or []:
            if not isinstance(row, Mapping):
                continue
            value = _trim(row.get("video_id"))
            if value and value not in seen:
                seen.append(value)
                resolved.append(value)
    deferred: list[str] = []
    for row in manifest.get("deferred") or []:
        if not isinstance(row, Mapping):
            continue
        value = _trim(row.get("video_id"))
        if value and value not in deferred:
            deferred.append(value)
    return resolved, deferred


def advance_cursor(cursor_data: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare a next cursor in memory; does not write it."""
    if manifest.get("status") == "skipped":
        raise CursorConflict("跳過輪不可推進 YouTube cursor")
    site = _trim(manifest.get("site")).upper()
    checkpoint = _trim(manifest.get("checkpoint"))
    if site not in SITE_SPECS or schema.CHECKPOINT_RE.fullmatch(checkpoint) is None:
        raise CursorConflict("manifest site/checkpoint 不合法，cursor 不前進")
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), Mapping) else {}
    if counts.get("dropped", 0) or (
            counts.get("window_total") is not None
            and counts.get("window_total") != counts.get("accounted")):
        raise CursorConflict("manifest 尚未完整對帳，cursor 不前進")
    try:
        manifest_revision = manifest.get("cursor_revision")
        current_revision = int(cursor_data.get("revision", 0))
        if manifest_revision is not None and int(manifest_revision) != current_revision:
            raise CursorConflict(
                f"manifest cursor revision 過期：manifest={manifest_revision} current={current_revision}"
            )
    except (TypeError, ValueError) as exc:
        raise CursorConflict("manifest/cursor revision 不合法") from exc
    next_cursor = json.loads(json.dumps(cursor_data, ensure_ascii=False))
    next_cursor.setdefault("schema_version", 1)
    next_cursor.setdefault("sites", {})
    old = dict(next_cursor["sites"].get(site) or {})
    resolved, deferred = _manifest_video_ids(manifest)
    old_deferred = [_trim(x) for x in old.get("deferred_video_ids", []) if _trim(x)]
    new_deferred = []
    for video_id in old_deferred + deferred:
        if video_id not in resolved and video_id not in new_deferred:
            new_deferred.append(video_id)
    recent = []
    for video_id in [_trim(x) for x in old.get("recent_video_ids", [])] + resolved + deferred:
        if video_id and video_id not in recent:
            recent.append(video_id)
    end = _trim(manifest.get("collect_started_at_utc"))
    parse_utc(end, "manifest collect_started_at_utc")
    old.update({
        "last_success_checkpoint": checkpoint,
        "last_complete_end_utc": end,
        "deferred_video_ids": new_deferred,
        "recent_video_ids": recent,
    })
    next_cursor["sites"][site] = old
    next_cursor["revision"] = current_revision
    return next_cursor


def _collect_command(args: argparse.Namespace) -> int:
    cursor_data = load_cursor(args.cursor)
    state_data = read_json(args.state)
    checkpoint = args.checkpoint or datetime.now().astimezone().strftime("%m%d-%H%M")
    client: YouTubeClient = (
        FixtureYouTubeClient(args.fixture_dir, args.site.upper())
        if args.fixture_dir else ProductionYouTubeClient()
    )
    manifest = collect_manifest(
        site=args.site, checkpoint=checkpoint, cursor_data=cursor_data,
        state_data=state_data, client=client,
        collect_started_at_utc=args.started_at_utc,
        bootstrap_start_utc=args.bootstrap_start_utc,
        max_pages=args.max_pages,
    )
    write_json_no_overwrite(args.out, manifest)
    print(json.dumps({"status": manifest["status"], "counts": manifest["counts"]}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="D23 YNA/CNA YouTube bridge（Phase 6 API sandbox）")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="collect；不寫 state／cursor")
    collect.add_argument("--site", required=True, choices=["cna", "yna"])
    collect.add_argument("--checkpoint")
    collect.add_argument("--state", required=True)
    collect.add_argument("--cursor", required=True)
    collect.add_argument("--out", required=True)
    collect.add_argument("--fixture-dir", help="offline fixture directory；省略時需設 YOUTUBE_API_KEY")
    collect.add_argument("--started-at-utc")
    collect.add_argument("--bootstrap-start-utc")
    collect.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PLAYLIST_PAGES)
    finalize = sub.add_parser("finalize", help="decisions → add-batch wrapper")
    finalize.add_argument("--manifest", required=True)
    finalize.add_argument("--entries", required=True, help="人工 decisions keyed object")
    finalize.add_argument("--out", required=True)
    finalize.add_argument("--apply", action="store_true")
    finalize.add_argument("--file", help="add-batch 目標 state；僅 --apply 必填")
    finalize.add_argument("--registry", help="測試／沙箱用 topic registry")
    finalize.add_argument("--cursor", help="apply 用每站 YouTube cursor；省略時取 state 同目錄")
    finalize.add_argument("--in-round", action="store_true",
                          help="只有排定輪次在自己的 .s2-scan.lock 鎖窗口內才可帶此旗標並 --apply；"
                               "手動觸發不得帶此旗標、也不得 --apply（計畫書 3.7）")
    finalize.add_argument("--pending-dir",
                          help="--in-round --apply 時掃這個目錄裡待套用的 YNA/CNA 候選 batch"
                               "（3.7；通常是 _待整併/），套用成功一併歸檔到其 已整併/ 子目錄")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "collect":
            return _collect_command(args)
        return _finalize_command(args)
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
