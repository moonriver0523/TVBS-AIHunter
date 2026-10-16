#!/usr/bin/env python3
"""外電存帶庫盤點（唯讀）：掃資料夾，輸出每支影片的原始事實 CSV。

不改名、不搬移、不刪除任何檔。欄位：相對路徑、子資料夾、檔名、副檔名、
大小(bytes)、修改時間、片長(秒)、寬、高、編碼、部分雜湊（前後各 1MB＋大小）。

用法：
  python scripts/wire_archive_inventory.py [--root <庫路徑>] [--out <csv>]
預設 root＝G:\\我的雲端硬碟\\Claude共用\\外電存帶庫，
預設 out＝common/wire-archive/外電存帶庫-原始盤點.csv
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = r'G:\我的雲端硬碟\Claude共用\外電存帶庫'
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'common', 'wire-archive', '外電存帶庫-原始盤點.csv')
VIDEO_EXT = {'.mp4', '.mxf', '.mpg', '.mpeg', '.mov', '.mkv', '.avi', '.m4v', '.wmv'}
FIELDS = ['rel_path', 'subfolder', 'filename', 'ext', 'size_bytes', 'mtime',
          'duration_sec', 'width', 'height', 'vcodec', 'partial_hash']


def probe(path):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name,width,height:format=duration',
             '-of', 'json', path],
            capture_output=True, timeout=60)
        j = json.loads(r.stdout.decode('utf-8', 'replace') or '{}')
        s = (j.get('streams') or [{}])[0]
        d = (j.get('format') or {}).get('duration')
        return (round(float(d), 1) if d else '', s.get('width', ''), s.get('height', ''),
                s.get('codec_name', ''))
    except Exception:
        return ('', '', '', '')


def partial_hash(path, size):
    h = hashlib.sha1()
    h.update(str(size).encode())
    with open(path, 'rb') as f:
        h.update(f.read(1 << 20))
        if size > (1 << 20):
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=DEFAULT_ROOT)
    ap.add_argument('--out', default=DEFAULT_OUT)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    out = Path(a.out).resolve()
    if not root.is_dir():
        ap.error(f'盤點根目錄不存在或不是資料夾：{root}')
    if out.is_relative_to(root):
        ap.error('輸出 CSV 必須放在盤點根目錄外，確保存帶庫唯讀')
    a.root, a.out = str(root), str(out)
    rows, skipped = [], []
    for dp, _dn, fns in os.walk(a.root):
        _dn.sort()
        for fn in sorted(fns):
            ext = os.path.splitext(fn)[1].lower()
            full = os.path.join(dp, fn)
            if ext not in VIDEO_EXT:
                if fn.lower() != 'desktop.ini':
                    skipped.append(os.path.relpath(full, a.root))
                continue
            st = os.stat(full)
            dur, w, h, vc = probe(full)
            rel = os.path.relpath(full, a.root)
            rows.append({
                'rel_path': rel,
                'subfolder': os.path.dirname(rel),
                'filename': fn,
                'ext': ext,
                'size_bytes': st.st_size,
                'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
                'duration_sec': dur, 'width': w, 'height': h, 'vcodec': vc,
                'partial_hash': partial_hash(full, st.st_size),
            })
    rows.sort(key=lambda row: row['rel_path'])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f'影片 {len(rows)} 支 → {a.out}')
    if skipped:
        print('非影片檔略過：', *skipped, sep='\n  ')


if __name__ == '__main__':
    sys.exit(main())
