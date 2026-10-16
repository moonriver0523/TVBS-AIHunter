#!/usr/bin/env python3
"""外電存帶庫對照執行器。預設唯讀預演，只有 --apply 才搬移。

預演可加 --inventory 原始盤點.csv 完全離線核對，不接觸影片庫。
--undo 預設也只預演；--undo --apply 才依執行紀錄還原。
執行紀錄預設在對照 CSV 旁，尾綴為「-已執行紀錄.csv」。
"""

import argparse
import csv
import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import sys

DEFAULT_ROOT = r'G:\我的雲端硬碟\Claude共用\外電存帶庫'
DEFAULT_MAP = Path(__file__).resolve().parents[1] / 'common/wire-archive/外電存帶庫-改名對照.csv'
MAP_FIELDS = ['id', 'old_rel_path', 'new_rel_path']
LOG_FIELDS = MAP_FIELDS + ['root', 'status', 'size_bytes', 'sha256', 'message']
STATUSES = {'planned', 'moved', 'error', 'noop', 'undone'}


def path_key(value):
    """Windows 路徑以不分大小寫比較，CSV 允許正斜線。"""
    return str(PureWindowsPath(value)).casefold()


def validate_relative(value):
    p = PureWindowsPath(value)
    if not value or p.drive or p.root or not p.parts:
        raise ValueError(f'不是相對路徑：{value!r}')
    # 在正規化之前拒絕空段、點、上層目錄及 Windows 特殊名稱。
    parts = re.split(r'[/\\]', value)
    for part in parts:
        if (not part or part in {'.', '..'} or part.endswith((' ', '.'))
                or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or PureWindowsPath(part).is_reserved()):
            raise ValueError(f'不安全的路徑：{value!r}')
    return p


def read_csv(path, required):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f'CSV 缺少必要欄位：{required}')
        rows = list(reader)
    if not rows:
        raise ValueError('CSV 沒有資料')
    return rows


def validate_mapping(rows):
    ids, sources, targets = set(), set(), set()
    for row in rows:
        if not row['id'] or row['id'] in ids:
            raise ValueError(f'識別碼空白或重複：{row["id"]}')
        ids.add(row['id'])
        for field, seen in [('old_rel_path', sources), ('new_rel_path', targets)]:
            validate_relative(row[field])
            key = path_key(row[field])
            if key in seen:
                raise ValueError(f'{field} 路徑重複：{row[field]}')
            seen.add(key)
        if (path_key(row['old_rel_path']) == path_key(row['new_rel_path'])
                and row['old_rel_path'] != row['new_rel_path']):
            raise ValueError('僅大小寫改名需先改成不同名稱，避免 Windows 路徑混淆')
    # 不支援交換／串連搬移，避免覆寫或後續還原順序歧義。
    for row in rows:
        if (path_key(row['new_rel_path']) in sources
                and row['old_rel_path'] != row['new_rel_path']):
            raise ValueError(f'目標也是來源：{row["new_rel_path"]}')


def safe_path(root, relative):
    p = root.joinpath(*validate_relative(relative).parts)
    resolved = p.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f'路徑透過連結超出影片庫：{relative}')
    # 不跟隨 junction／symbolic link，避免把檔案搬入意外位置。
    for parent in [p, *p.parents]:
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError(f'路徑含連結：{relative}')
    return p


def fingerprint(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return str(path.stat().st_size), h.hexdigest()


def matches(path, row):
    return (path.is_file() and row['sha256']
            and fingerprint(path) == (row['size_bytes'], row['sha256']))


def save_log(path, rows):
    """先落完整對照再搬檔；狀態採原子替換且同步到磁碟。"""
    temp = path.with_name(path.name + '.tmp')
    created = False
    try:
        with temp.open('x', encoding='utf-8-sig', newline='') as f:
            created = True
            writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if created and temp.exists():
            temp.unlink()


def move_no_replace(src, dst):
    if dst.exists():
        raise FileExistsError(f'目標已存在：{dst}')
    # Windows rename 本身禁止覆寫，且同一影片庫內搬移不複製內容。
    # 此工具處理 Windows 存帶庫；禁止在其他平台 apply，防止 rename 覆寫語意不同。
    if os.name != 'nt':
        raise OSError('實際搬移僅支援 Windows；其他平台可使用離線預演')
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.rename(src, dst)


def run(mapping, root, log=None, apply=False, undo=False, inventory=None, emit=print):
    rows = read_csv(mapping, MAP_FIELDS)
    rows = [{k: row[k] for k in MAP_FIELDS} for row in rows]
    validate_mapping(rows)
    log = Path(log) if log else Path(mapping).with_name(Path(mapping).stem + '-已執行紀錄.csv')
    if inventory:
        if apply or undo:
            raise ValueError('--inventory 只適用於正向唯讀預演')
        facts = read_csv(inventory, ['rel_path'])
        available = {path_key(r['rel_path']) for r in facts}
        errors = 0
        emit(f'離線預演：對照 {len(rows)} 筆；盤點 {len(facts)} 筆；未存取影片庫')
        for row in rows:
            old, new = row['old_rel_path'], row['new_rel_path']
            error = ('來源未列於盤點' if path_key(old) not in available else
                     '目標已列於盤點' if path_key(new) in available and old != new else '')
            errors += bool(error)
            emit(f'{row["id"]} {"錯誤 " + error if error else "預演"}：{old} → {new}')
        emit(f'合計 {len(rows)} 筆；錯誤 {errors}；實際搬移 0；未建立執行紀錄')
        return 1 if errors else 0

    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'影片庫不存在：{root}')
    if log.resolve().is_relative_to(root):
        raise ValueError('執行紀錄必須放在影片庫外')
    # 先驗證全部路徑，才容許產生紀錄或搬移。
    for row in rows:
        safe_path(root, row['old_rel_path'])
        safe_path(root, row['new_rel_path'])
    if log.exists():
        journal = read_csv(log, LOG_FIELDS)
        if [{k: r[k] for k in MAP_FIELDS} for r in journal] != rows:
            raise ValueError('執行紀錄與對照不符，請使用原對照或指定另一份 --log')
        if any(r['root'] != str(root) or r['status'] not in STATUSES for r in journal):
            raise ValueError('執行紀錄的影片庫或狀態不符')
    elif undo:
        raise ValueError('找不到執行紀錄，無法還原')
    else:
        journal = [dict(r, root=str(root), status='planned', size_bytes='', sha256='', message='')
                   for r in rows]
        if apply:
            # x 模式佔用紀錄名稱，避免另一個程序覆蓋既有紀錄。
            with log.open('x', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
                writer.writeheader()
                writer.writerows(journal)
                f.flush()
                os.fsync(f.fileno())

    moved = skipped = errors = 0
    for row in reversed(journal) if undo else journal:
        old, new = safe_path(root, row['old_rel_path']), safe_path(root, row['new_rel_path'])
        src, dst = (new, old) if undo else (old, new)
        try:
            if old == new:
                if not old.is_file():
                    raise FileNotFoundError(f'來源不存在：{old}')
                if apply:
                    row['status'] = 'noop'
                    save_log(log, journal)
                skipped += 1
                emit(f'{row["id"]} 原位保留')
                continue
            if not undo and row['status'] == 'moved':
                if not matches(new, row) or old.exists():
                    raise ValueError('已搬移項目的檔案狀態改變，停止該項')
                skipped += 1
                emit(f'{row["id"]} 已完成，略過')
                continue
            if undo and row['status'] in {'undone', 'noop'}:
                if row['status'] == 'undone' and (not matches(old, row) or new.exists()):
                    raise ValueError('已還原項目的檔案狀態改變，停止該項')
                skipped += 1
                emit(f'{row["id"]} 已還原或無動作，略過')
                continue
            if undo and not new.exists() and matches(old, row):
                if apply:
                    row.update(status='undone', message='中斷後核對還原完成')
                    save_log(log, journal)
                skipped += 1
                emit(f'{row["id"]} 核對先前還原完成')
                continue
            if undo and row['status'] in {'planned', 'error'} and old.exists():
                if row['sha256'] and not matches(old, row):
                    raise ValueError('未搬移項目的來源已改變')
                skipped += 1
                emit(f'{row["id"]} 未搬移，略過')
                continue
            # 若先前中斷發生在 rename 與紀錄更新之間，正向重跑可補記完成。
            if not undo and not old.exists() and matches(new, row):
                if apply:
                    row['status'], row['message'] = 'moved', '中斷後核對補記'
                    save_log(log, journal)
                skipped += 1
                emit(f'{row["id"]} 核對先前搬移完成')
                continue
            if not src.is_file():
                raise FileNotFoundError(f'來源不存在：{src}')
            if dst.exists():
                raise FileExistsError(f'目標已存在：{dst}')
            if undo and not matches(src, row):
                raise ValueError('檔案與搬移時的完整 SHA-256 不符，停止還原該項')
            if apply:
                if not undo:
                    size, digest = fingerprint(src)
                    if row['sha256'] and (size, digest) != (row['size_bytes'], row['sha256']):
                        raise ValueError('檔案與前次紀錄不符')
                    row.update(size_bytes=size, sha256=digest, status='planned', message='')
                    save_log(log, journal)
                move_no_replace(src, dst)
                row.update(status='undone' if undo else 'moved', message='')
                save_log(log, journal)
                moved += 1
            emit(f'{row["id"]} {"還原" if undo else "搬移"}{"" if apply else "預演"}：{src} → {dst}')
        except (OSError, ValueError) as exc:
            errors += 1
            # 保留 moved 狀態，避免失敗的 undo 失去可還原性。
            if apply:
                row['message'] = str(exc)
                save_log(log, journal)
            emit(f'{row["id"]} 錯誤：{exc}')
    emit(f'合計 {len(rows)} 筆；實際搬移 {moved}；略過 {skipped}；錯誤 {errors}')
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping', type=Path, default=DEFAULT_MAP)
    parser.add_argument('--root', type=Path, default=Path(DEFAULT_ROOT))
    parser.add_argument('--log', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='唯讀預演（預設）')
    mode.add_argument('--apply', action='store_true', help='實際執行搬移或還原')
    parser.add_argument('--undo', action='store_true', help='依紀錄還原；預設只預演')
    parser.add_argument('--inventory', type=Path, help='只讀盤點 CSV 的離線預演')
    args = parser.parse_args(argv)
    try:
        return run(args.mapping, args.root, args.log, args.apply, args.undo, args.inventory)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(f'錯誤：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
