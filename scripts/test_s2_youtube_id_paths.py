# -*- coding: utf-8 -*-
"""D23 Phase 1：scheduled YouTube ID 走過品質掃、render 與 mark-ingested seam。"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_mark_ingested as mark_ingested  # noqa: E402
import s2_render as render  # noqa: E402
import s2_validate as validate  # noqa: E402


def report(name, passed, detail=""):
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def main():
    ok = True
    entries = [
        "YNA-AbCd_ef-123 (南韓測試) ▎摘要。▎無BITE。▎01:35",
        "CNA-XyZ987_ab-c (CNA測試) ▎摘要。▎無BITE。▎00:30",
    ]
    lines = ["======國際======", ""] + entries
    material = validate.material_lines(lines)
    ok &= report("s2_validate.material_lines 認 scheduled YNA/CNA",
                 [line for _, line in material] == entries, repr(material))

    rendered = render.render_item({
        "id": "YNA-AbCd_ef-123",
        "source": "YNA",
        "first_seen_checkpoint": "0920-0430",
        "raw_entry": entries[0],
    }, "0920")
    ok &= report("s2_render.render_item 保留 scheduled ID", rendered and
                 rendered[0].endswith(entries[0]), repr(rendered))

    with tempfile.TemporaryDirectory(prefix="d23-id-paths-") as td:
        path = os.path.join(td, "0920-CNA.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(entries[1] + "\n")
        _, codes = mark_ingested.keys_in_file(path)
        ok &= report("s2_mark_ingested.keys_in_file 認 scheduled ID",
                     codes == {"CNA-XyZ987_ab-c"}, repr(codes))

    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
