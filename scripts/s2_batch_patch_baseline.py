#!/usr/bin/env python3
"""Verify and materialize the sanitized A43 9/22 batch-patch fixture.

The checked-in fixture contains only sequence shape and numeric telemetry.  Real
IDs, paths, source text, and Edit payloads are intentionally absent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURE = HERE / "fixtures" / "a43_batch_patch" / "baseline.json"


def load_fixture(path=DEFAULT_FIXTURE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def synthetic_id(session, sequence):
    return f"{session['id_prefix']}{sequence:0{int(session['id_width'])}d}"


def fields_for(session, sequence):
    for group in session["field_groups"]:
        if int(group["from"]) <= sequence <= int(group["through"]):
            return tuple(group["fields"])
    raise ValueError(f"{session['label']} sequence {sequence} has no field group")


def enumerate_events(session):
    count = len(session["cache_read_input_tokens"])
    arrays = ("output_tokens", "tool_input_bytes")
    for name in arrays:
        if len(session[name]) != count:
            raise ValueError(f"{session['label']} {name} length mismatch")
    for index in range(count):
        sequence = index + 1
        yield {
            "sequence": sequence,
            "id": synthetic_id(session, sequence),
            "fields": list(fields_for(session, sequence)),
            "cache_read_input_tokens": session["cache_read_input_tokens"][index],
            "output_tokens": session["output_tokens"][index],
            "tool_input_bytes": session["tool_input_bytes"][index],
        }


def summarize(fixture):
    sessions = fixture["sessions"]
    events = [event for session in sessions for event in enumerate_events(session)]
    summary = {
        "targeted_edit_turns": len(events),
        "targeted_cache_read_input_tokens": sum(
            event["cache_read_input_tokens"] for event in events
        ),
        "targeted_output_tokens": sum(event["output_tokens"] for event in events),
        "targeted_tool_input_bytes": sum(event["tool_input_bytes"] for event in events),
        "lint_output_bytes": sum(
            run["output_bytes"] for session in sessions for run in session["lint_runs"]
        ),
        "round_tool_turns": sum(session["round"]["tool_turns"] for session in sessions),
        "round_edit_calls": sum(session["round"]["edit_calls"] for session in sessions),
        "source_log_bytes": sum(session["round"]["source_log_bytes"] for session in sessions),
        "sessions": [
            {
                "label": session["label"],
                "site": session["site"],
                "targeted_edit_turns": len(list(enumerate_events(session))),
                "modified": [
                    {"id": event["id"], "fields": event["fields"]}
                    for event in enumerate_events(session)
                ],
                "lint_runs": session["lint_runs"],
            }
            for session in sessions
        ],
    }
    expected = fixture["expected_totals"]
    mismatches = {
        key: {"expected": value, "actual": summary.get(key)}
        for key, value in expected.items()
        if summary.get(key) != value
    }
    if mismatches:
        raise ValueError(f"baseline totals mismatch: {mismatches}")
    if not all(session["lint_runs"][-1]["clean"] for session in sessions):
        raise ValueError("each historical sequence must end with a clean lint run")
    return summary


def replay_payload(session):
    rows = []
    changes = []
    for event in enumerate_events(session):
        item_id = event["id"]
        row = {
            "id": item_id,
            "source": session["site"].upper(),
            "entry": f"{item_id} (VO) ▎sanitized before。▎畫面：fixture。無BITE。",
            "category": "國際/A43 fixture before",
            "tc": "",
            "skip": "",
            "sb_count": 0,
        }
        if session["site"] == "abc":
            row.update(src_text=f"sanitized source {event['sequence']}",
                       detailId=f"fixture-{event['sequence']}")
        values = {}
        for field in event["fields"]:
            if field == "entry":
                values[field] = (
                    f"{item_id} (VO) ▎sanitized after。▎畫面：fixture。無BITE。"
                )
            elif field == "category":
                values[field] = "國際/A43 fixture after"
            elif field == "tc":
                values[field] = "T1/C1"
            elif field == "skip":
                values[field] = "sanitized exclusion"
        rows.append(row)
        changes.append({"id": item_id, "set": values})
    return rows, changes


def materialize(fixture, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written = []
    for session in fixture["sessions"]:
        rows, changes = replay_payload(session)
        skeleton = output / f"{session['site']}_skeleton.json"
        patch = output / f"{session['site']}.patch.json"
        for path in (skeleton, patch):
            if path.exists():
                raise FileExistsError(f"fixture output exists, refusing overwrite: {path}")
        skeleton_bytes = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
        skeleton.write_bytes(skeleton_bytes)
        patch.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "site": session["site"],
                    "target_sha256": hashlib.sha256(skeleton_bytes).hexdigest(),
                    "changes": changes,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        written.append({"site": session["site"], "skeleton": str(skeleton),
                        "patch": str(patch), "changes": len(changes)})
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--materialize", metavar="DIR")
    args = parser.parse_args(argv)
    fixture = load_fixture(args.fixture)
    result = {"summary": summarize(fixture)}
    if args.materialize:
        result["materialized"] = materialize(fixture, args.materialize)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
