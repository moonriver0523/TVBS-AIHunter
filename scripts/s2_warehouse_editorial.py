"""Offline v5 bundle derivation and optional human-authored rundowns (stdlib only).

Current revisions, exact canonical registry grouping, >=2 global members and
A33 per-shift ranks follow demo_build_v5_bundles. No proposal text is generated.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import s2_rundown_propose as A33
import s2_ctv_candidates as A34


def bucket(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:2]


def derive(payloads, materials, observations, registry=None):
    """Return bundles by shift, explicit editorial projection and alias resolver.

    Ambiguous legacy aliases are deliberately omitted; never choose an arbitrary
    observation when two material identities share the same legacy spelling.
    """
    registry = A33._load_registry() if registry is None else registry
    obs = defaultdict(set)
    aliases = defaultdict(set)
    for day, mid, payload in observations:
        obs[mid].add(day)
        aliases[f"legacy:{day}:{payload.get('source', '')}:{payload.get('id', '')}"].add(mid)
    resolver = {alias: next(iter(ids)) for alias, ids in aliases.items() if len(ids) == 1}
    resolver.update({mid: mid for mid in payloads})
    items = [dict(p, _demo_id=mid) for mid, p in sorted(payloads.items())]
    by_day = defaultdict(list)
    for name, group in A33.group_by_canonical(items, registry).items():
        members = group["items"]
        if len(members) < 2:
            continue
        score, reasons = A33.score(members)
        bid = "b-" + hashlib.sha256(name.encode()).hexdigest()[:12]
        days = sorted({day for p in members for day in obs[p["_demo_id"]]})
        for day in days:
            subset = [p for p in members if day in obs[p["_demo_id"]]]
            by_day[day].append(dict(id=bid, name=name, ids=[p["_demo_id"] for p in subset],
                                   score=score, reasons=reasons, qualifies=bool(A33.qualifies(members)),
                                   shifts={day: dict(count=len(subset), score=A33.score(subset)[0],
                                                     qualifies=bool(A33.qualifies(subset)))}))
    for bundles in by_day.values():
        bundles.sort(key=lambda b: (-b["qualifies"], -b["score"], b["name"]))
    rows = defaultdict(list)
    for mid, p in sorted(payloads.items()):
        r = materials[mid]
        fields = p.get("fields") or {}
        ctv, why = A34.is_candidate(p)
        meta = dict(notes=fields.get("notes"), bite=fields.get("bite"), codes=fields.get("codes"),
                    ctv=ctv, ctv_reason=why, known=bool(fields), hilite=A34._marks(p.get("raw_entry"))[2])
        meta = {k: v for k, v in meta.items() if v not in (None, [], "", False)}
        cat = p.get("category") or {}
        if not isinstance(cat, dict):
            cat = dict(zip(("大分類", "中主題", "小分題"), str(cat).split("/", 2)))
        # Only explicit fields; no whole payload, platform, compiled or source text.
        row = dict(id=mid, code=str(p.get("id") or ""), src=str(p.get("source") or ""),
                   kind="side" if r["kind"] == "side_recording" or str(p.get("source", "")).startswith("SIDE_") else r["kind"],
                   text=str(p.get("raw_entry") or ""), md=r["material_date"], mdr=r["material_date_range"],
                   q=r["date_quality"], dc=r["date_confidence"], cat=cat,
                   T=(p.get("tc") or {}).get("T", []), C=(p.get("tc") or {}).get("C", []),
                   link=r["source_link"].get("url") or "", obs=[{"shift": "s2:" + d} for d in sorted(obs[mid])],
                   meta=meta)
        rows[min(obs[mid], default="unknown")].append(row)
    references = defaultdict(list)
    for alias, mid in sorted(resolver.items()):
        references[bucket(alias)].append(dict(id=alias, material_id=mid, day=min(obs[mid], default="unknown")))
    return by_day, rows, references, resolver


def optional_rundown(path, resolver, payloads):
    """Map only known/unambiguous references, reporting every unresolved ID.

    Keep candidate prose intact. Missing materials stay explicit in gaps and are
    removed from actionable item/bite lists so an editor cannot silently use them.
    """
    path = Path(path)
    candidates = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else []
    if not isinstance(candidates, list):
        raise ValueError(f"候選稿單須為陣列：{path}")
    candidates = deepcopy(candidates)
    ids, unresolved, mapped, stale_bites = set(), set(), set(), []
    for c in candidates:
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not isinstance(c.get("segments"), list):
            raise ValueError(f"候選稿單格式錯誤：{path}")
        for key in ("稿名", "形式", "主軸"):
            if not isinstance(c.get(key), str):
                raise ValueError(f"候選稿單缺少 {key}：{path}")
        def resolve(old):
            ids.add(old)
            mid = resolver.get(old)
            if not mid:
                unresolved.add(old)
            elif old != mid:
                mapped.add(old)
            return mid
        missing = set()
        for s in c["segments"]:
            kept = []
            for item in s["items"]:
                old = item["material_id"]
                mid = resolve(old)
                if mid:
                    item["material_id"] = mid
                    kept.append(item)
                else:
                    missing.add(old)
            s["items"] = kept
        bites = []
        selected = {i["material_id"] for s in c["segments"] for i in s["items"]}
        for b in c.get("bites", []):
            mid = resolve(b["material_id"])
            if mid in selected and b["text"] in (payloads[mid].get("raw_entry") or ""):
                b["material_id"] = mid
                bites.append(b)
            elif mid:
                stale_bites.append(dict(candidate=c["id"], material_id=mid))
        c["bites"] = bites
        c["gaps"] = c.get("gaps", []) + ["本版無法對映素材：" + x for x in sorted(missing)]
        c["a34_ids"] = [mid for old in c.get("a34_ids", []) if (mid := resolve(old))]
    report = dict(input_present=path.exists(), referenced_ids=len(ids), remapped_ids=len(mapped),
                  unresolved_count=len(unresolved), unresolved_ids=sorted(unresolved), stale_bites=stale_bites)
    return candidates, report
