# A43 file-backed batch patch v1

日期：2026-09-24

## 契約

兩條 draft rewrite seam 共用同一個 JSON 外殼：

```json
{
  "schema_version": 1,
  "site": "enex",
  "target_sha256": "64 lowercase hex characters",
  "changes": [
    {
      "id": "ENEX1001",
      "set": {
        "entry": "…",
        "category": "…",
        "tc": "…",
        "skip": "…"
      }
    }
  ]
}
```

- v1 的全域人工欄位白名單是 `entry/category/tc/skip`；`id/src_text/detailId/source/checkpoint/sb_count` 等機械欄位一律拒絕。platform 骨架可用四欄；NS/AP/RT entries 的既有草稿契約沒有 `skip`，所以該 seam 只接受 `entry/category/tc`，不接受後續 build 不會消費的假欄位。
- `set` 是局部 patch，只覆寫明列欄位。未列欄位與保留鍵原樣保留；空 `set` 拒絕。
- ENEX／ABC ID 先 canonicalize；帶／不帶 `ENEX`、`ABC` 前綴視為同一 ID，因此兩種拼法同批出現會以 duplicate ID 拒絕。NS/AP/RT 沿用原 ID，不自行猜前綴。
- `site` 必須和 CLI `--site` 相同。patch 與 target 不記路徑關聯；CLI 選 target，`target_sha256` 綁定 agent 準備 patch 時看到的精確 bytes。
- apply 前先驗 schema、站別、全部 ID、欄位、active gate-lock 權限與 lint/no-regression，再於 replace 前重驗 SHA。任一失敗均不寫 target。
- 單檔以同目錄 temporary＋`fsync`＋`os.replace` 寫入。platform 的 skeleton 與衍生 entries 先全部 staged，entries 先 replace、權威 skeleton 最後 replace；第二步失敗會把第一步還原，CLI 不會以成功狀態留下半套結果。
- `--dry-run` 走同一套驗證並輸出 changed IDs/fields、lint reason counts（core）及預期 output SHA，不寫檔、不清 lock。
- `--init-patch OUT` 建立 `changes: []` 的 scaffold 並填入目前 target SHA；已存在的 OUT 不覆寫。scaffold 建好後工具會印出唯一 apply 指令。

## CLI

```text
python scripts/s2_platform_bridge.py rewrite-entry --site enex \
  --skeleton enex_skeleton_1700.json --entries enex_entries_1700.json \
  --init-patch enex_patch_1700.json

python scripts/s2_platform_bridge.py rewrite-entry --site enex \
  --skeleton enex_skeleton_1700.json --entries enex_entries_1700.json \
  --patch-file enex_patch_1700.json [--dry-run]

python scripts/s2_batch_prep.py rewrite-entry --site rt \
  --entries rt_entries_1700.json --init-patch rt_patch_1700.json

python scripts/s2_batch_prep.py rewrite-entry --site rt \
  --entries rt_entries_1700.json --patch-file rt_patch_1700.json [--dry-run]
```

舊 `--id/--set` 保留且與 `--patch-file` 互斥。`add-batch` 維持 add-only；正式 state 既有稿仍走 `s2_state.py update-entry --batch`。

## Sanitized fixture 與基線

`scripts/fixtures/a43_batch_patch/baseline.json` 保存 0922-1700 的 39 個 ENEX targeted Edit turns 與 0922-2359 的 9 個 ABC turns。只留順序、合成 ID、變更欄位集合及數值遙測，不含真實 ID、路徑、來源文字或 Edit payload。

```text
python scripts/s2_batch_patch_baseline.py
python scripts/s2_batch_patch_baseline.py --materialize <empty-output-dir>
```

第一個命令重算 48 targeted Edit turns、25,002,406 cache-read tokens、474 全輪 tool turns、65 全輪 Edit calls、7,393,439 source-log bytes，以及 targeted tool-input/output 與 lint-output bytes。第二個命令產生可直接餵兩條 platform CLI 的 39＋9 skeleton/patch replay，不讀寫 production state。
