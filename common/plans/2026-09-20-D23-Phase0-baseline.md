# D23 Phase 0 基線

本紀錄與 D23 實作分支 `feat/d23-youtube-bridge` 綁定，供後續 Phase 驗收比較。Phase 0
只建立去憑證 fixture，不呼叫 YouTube、字幕服務、正式 state 或排程。

## 基線環境

- 基線 commit：`3e7f312`（D23 使用者核准實作）
- 工作樹：`feat/d23-youtube-bridge`
- Python 測試以 `python -X utf8` 直接執行；`s2_render.py` 的 CLI fixture 測試因未提供三個輸入檔而依既有行為 SKIP。

## 未接線前結果

下列既有測試在新增 D23 程式前全部通過；`test_s2_render.py` 為既有條件式 SKIP，沒有失敗：

```text
test_s2_material_schema.py       PASS
test_s2_id_paths.py              PASS
test_s2_source_reader.py         PASS
test_s2_render_empty_sub.py      PASS
test_s2_add_batch_shapes.py      PASS
test_s2_add_batch_tc.py          PASS
test_s2_add_batch_newtopic.py    PASS
test_s2_platform.py              PASS=77 FAIL=0
test_s2_platform_extract.py      PASS=94 FAIL=0
test_s2_platform_merge_newtopic.py PASS
test_s2_render.py                SKIP (需要 state／定版／render 三個輸入檔)
```

這份基線不包含正式排程執行；`s2_scan.ps1`、Windows 工作排程 XML、正式 state 與
`.s2-scan.lock` 均未觸碰。

