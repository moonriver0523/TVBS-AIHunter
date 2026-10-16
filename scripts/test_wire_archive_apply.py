"""以暫存假檔驗證搬移、衝突、中斷復原及唯讀預演。"""

import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

import wire_archive_apply as archive
import wire_archive_inventory as inventory_tool


class ArchiveApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / '庫'
        self.root.mkdir()
        self.mapping = self.base / '對照.csv'
        self.log = self.base / '紀錄.csv'
        self.write_mapping([('WA0001', 'RT 原片.MP4', '素材庫/RT 新片.mp4')])
        (self.root / 'RT 原片.MP4').write_bytes(b'video-one')

    def write_mapping(self, values):
        with self.mapping.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(archive.MAP_FIELDS)
            writer.writerows(values)

    def run_tool(self, **kwargs):
        return archive.run(self.mapping, self.root, self.log, emit=lambda _: None, **kwargs)

    def test_default_dry_run_does_not_create_files_or_directories(self):
        before = sorted(str(p.relative_to(self.base)) for p in self.base.rglob('*'))
        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(before, sorted(str(p.relative_to(self.base)) for p in self.base.rglob('*')))
        self.assertEqual((self.root / 'RT 原片.MP4').read_bytes(), b'video-one')

    def test_apply_undo_and_repeat(self):
        self.assertEqual(self.run_tool(apply=True), 0)
        self.assertEqual((self.root / '素材庫/RT 新片.mp4').read_bytes(), b'video-one')
        self.assertFalse((self.root / 'RT 原片.MP4').exists())
        self.assertEqual(self.run_tool(apply=True), 0)
        self.assertEqual(self.run_tool(undo=True), 0)
        self.assertTrue((self.root / '素材庫/RT 新片.mp4').exists())
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)
        self.assertEqual((self.root / 'RT 原片.MP4').read_bytes(), b'video-one')
        self.assertEqual(self.run_tool(apply=True), 0)

    def test_existing_target_stops_item_and_continues_other_item(self):
        self.write_mapping([('WA0001', 'RT 原片.MP4', '已存在.mp4'), ('WA0002', '第二片.mp4', '新/第二片.mp4')])
        (self.root / '已存在.mp4').write_bytes(b'keep-target')
        (self.root / '第二片.mp4').write_bytes(b'video-two')
        self.assertEqual(self.run_tool(apply=True), 1)
        self.assertEqual((self.root / '已存在.mp4').read_bytes(), b'keep-target')
        self.assertTrue((self.root / 'RT 原片.MP4').exists())
        self.assertEqual((self.root / '新/第二片.mp4').read_bytes(), b'video-two')
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)
        self.assertTrue((self.root / '第二片.mp4').exists())

    def test_duplicate_moves_to_quarantine_and_undo(self):
        self.write_mapping([('WA0001', 'RT 原片.MP4', '待刪/重複候選/RT 原片 WA0001.mp4')])
        self.assertEqual(self.run_tool(apply=True), 0)
        self.assertTrue((self.root / '待刪/重複候選/RT 原片 WA0001.mp4').exists())
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)
        self.assertTrue((self.root / 'RT 原片.MP4').exists())

    def test_journal_exists_before_first_move(self):
        real_move = archive.move_no_replace
        def inspect_then_move(src, dst):
            rows = archive.read_csv(self.log, archive.LOG_FIELDS)
            self.assertEqual(rows[0]['status'], 'planned')
            self.assertEqual(rows[0]['sha256'], archive.fingerprint(src)[1])
            real_move(src, dst)
        with patch.object(archive, 'move_no_replace', side_effect=inspect_then_move):
            self.assertEqual(self.run_tool(apply=True), 0)

    def test_undo_refuses_changed_file_and_existing_original(self):
        self.assertEqual(self.run_tool(apply=True), 0)
        target = self.root / '素材庫/RT 新片.mp4'
        target.write_bytes(b'changed')
        self.assertEqual(self.run_tool(undo=True, apply=True), 1)
        target.write_bytes(b'video-one')
        (self.root / 'RT 原片.MP4').write_bytes(b'new-original')
        self.assertEqual(self.run_tool(undo=True, apply=True), 1)
        self.assertEqual(target.read_bytes(), b'video-one')
        self.assertEqual((self.root / 'RT 原片.MP4').read_bytes(), b'new-original')

    def test_resume_after_interrupted_move(self):
        real_save = archive.save_log
        def interrupted(path, rows):
            if rows[0]['status'] == 'moved':
                raise KeyboardInterrupt()
            real_save(path, rows)
        with patch.object(archive, 'save_log', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_tool(apply=True)
        self.assertEqual(self.run_tool(apply=True), 0)
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)

    def test_resume_after_interrupted_undo(self):
        self.assertEqual(self.run_tool(apply=True), 0)
        real_save = archive.save_log
        def interrupted(path, rows):
            if rows[0]['status'] == 'undone':
                raise KeyboardInterrupt()
            real_save(path, rows)
        with patch.object(archive, 'save_log', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_tool(undo=True, apply=True)
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)
        self.assertEqual((self.root / 'RT 原片.MP4').read_bytes(), b'video-one')

    def test_foreign_temporary_journal_is_not_removed(self):
        temp = self.log.with_name(self.log.name + '.tmp')
        temp.write_bytes(b'other-process')
        with self.assertRaises(FileExistsError):
            archive.save_log(self.log, [])
        self.assertEqual(temp.read_bytes(), b'other-process')

    def test_all_300_mappings_round_trip_with_fake_files(self):
        records = archive.read_csv(archive.DEFAULT_MAP, archive.MAP_FIELDS)
        self.write_mapping([(r['id'], r['old_rel_path'], r['new_rel_path']) for r in records])
        for row in records:
            src = self.root.joinpath(*archive.validate_relative(row['old_rel_path']).parts)
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(row['id'].encode('ascii'))
        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(self.run_tool(apply=True), 0)
        self.assertEqual(self.run_tool(apply=True), 0)
        self.assertEqual(self.run_tool(undo=True, apply=True), 0)
        for row in records:
            src = self.root.joinpath(*archive.validate_relative(row['old_rel_path']).parts)
            self.assertEqual(src.read_bytes(), row['id'].encode('ascii'))

    def test_offline_inventory_does_not_access_root(self):
        inventory = self.base / '盤點.csv'
        inventory.write_text('rel_path\nRT 原片.MP4\n', encoding='utf-8-sig')
        with patch.object(Path, 'resolve', side_effect=AssertionError('禁止存取影片庫')):
            self.assertEqual(self.run_tool(inventory=inventory), 0)
        self.assertFalse(self.log.exists())
        with self.assertRaises(ValueError):
            self.run_tool(inventory=inventory, apply=True)

    def test_offline_missing_source_and_existing_target(self):
        inventory = self.base / '盤點.csv'
        inventory.write_text('rel_path\n素材庫/RT 新片.mp4\n', encoding='utf-8-sig')
        self.assertEqual(self.run_tool(inventory=inventory), 1)
        self.assertFalse(self.log.exists())

    def test_rejects_unsafe_paths_before_writing_log(self):
        for value in ['../escape.mp4', 'C:\\escape.mp4', '\\escape.mp4', 'safe/../escape', 'CON.mp4', 'file:stream', 'a./x', './x', 'a//b']:
            with self.subTest(path=value):
                self.write_mapping([('WA0001', 'RT 原片.MP4', value)])
                with self.assertRaises(ValueError):
                    self.run_tool(apply=True)
                self.assertFalse(self.log.exists())

    def test_rejects_duplicate_windows_targets_and_move_chains(self):
        for values in [
            [('A', 'one.mp4', 'new/A.mp4'), ('B', 'two.mp4', 'NEW/a.mp4')],
            [('A', 'one.mp4', 'two.mp4'), ('B', 'two.mp4', 'three.mp4')],
            [('A', 'one.mp4', 'new/a.mp4'), ('A', 'two.mp4', 'new/b.mp4')],
        ]:
            self.write_mapping(values)
            with self.assertRaises(ValueError):
                self.run_tool(apply=True)
            self.assertFalse(self.log.exists())

    def test_missing_source_and_wrong_journal_root(self):
        (self.root / 'RT 原片.MP4').unlink()
        self.assertEqual(self.run_tool(apply=True), 1)
        rows = archive.read_csv(self.log, archive.LOG_FIELDS)
        rows[0]['root'] = str(self.base)
        archive.save_log(self.log, rows)
        with self.assertRaises(ValueError):
            self.run_tool(apply=True)

    def test_changed_mapping_cannot_reuse_log(self):
        self.assertEqual(self.run_tool(apply=True), 0)
        self.write_mapping([('WA0001', 'RT 原片.MP4', '其他.mp4')])
        with self.assertRaises(ValueError):
            self.run_tool(undo=True, apply=True)


class InventorySafetyTests(unittest.TestCase):
    def test_reject_missing_root_without_overwriting_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'existing.csv'
            out.write_bytes(b'existing')
            with patch('sys.argv', ['inventory', '--root', str(Path(temp) / 'missing'), '--out', str(out)]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    inventory_tool.main()
            self.assertEqual(out.read_bytes(), b'existing')

    def test_reject_output_inside_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'inventory.csv'
            with patch('sys.argv', ['inventory', '--root', temp, '--out', str(out)]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    inventory_tool.main()
            self.assertFalse(out.exists())

    def test_partial_hash_covers_tail_between_one_and_two_mb(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / 'a.mp4', Path(temp) / 'b.mp4'
            first.write_bytes(b'a' * (1536 * 1024))
            second.write_bytes(b'a' * (1536 * 1024 - 1) + b'b')
            self.assertNotEqual(inventory_tool.partial_hash(first, first.stat().st_size),
                                inventory_tool.partial_hash(second, second.stat().st_size))


if __name__ == '__main__':
    unittest.main()
