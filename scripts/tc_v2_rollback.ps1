#Requires -Version 7
# ⚠️ 2026-08-31 補（全流程 locale 編碼稽核）：本檔是 UTF-8 **無 BOM**、含 880 個
# 中文字元。Windows PowerShell 5.1 沒有 BOM 就會照系統 ANSI（本機 Big5/950）解，
# 中文被誤解後可能把後續程式碼整段吞進註解、離開碼還是 0——回滾腳本靜默沒做事
# 是最糟的一種失敗。其餘 s2_*.ps1 不是有 BOM 就是有這行 Requires，本檔原本兩者
# 皆無。釘死 PS7（預設 UTF-8）比補 BOM 保險，且與其他腳本一致。
#
# A10 v2（T/C 矩陣）一鍵回滾。2026-08-24 上線時建立。
#
# 用途：2000 輪（或之後任何一輪）出問題時，把規則與程式退回 v2 上線前的狀態，
#       下一輪自動吃到舊版本，**不必重啟排程／launcher／watchdog**。
#
# 用法：
#   pwsh -File scripts\tc_v2_rollback.ps1            # 檢查並回滾
#   pwsh -File scripts\tc_v2_rollback.ps1 -DryRun    # 只看會做什麼，不動手
#
# 🔴 回滾也要挑窗口：s2_state.py 是**每次呼叫重新讀檔**，輪次進行中把 set-tc
#    revert 掉，已經呼叫過的 agent 會拿到 `invalid choice` 硬錯，而不是靜靜
#    退回兜底——那正是上線時刻意避免的形狀，只是從回退方向發生。
#    本腳本會先擋掉「有輪次在跑」的情況。
#
# 回滾後狀態檔裡已寫入的 tc 欄位**留著無害**：舊版 render 根本不看它，
# 新版 render 有就用、沒有就跑 tag_tc()。⛔ 不要去清狀態檔。

[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$base = 'tc-v2-rollback-base'

Write-Host "== A10 v2 一鍵回滾 ==" -ForegroundColor Cyan
Write-Host "repo: $repo"

# ── 閘門 1：確認沒有輪次在跑 ─────────────────────────────────────────────
# ⛔ 不看鎖檔——改看 pwsh 行程判活。R16（.s2-scan.lock 永久殘留）已於 0824
# 由 s2_keepalive.ps1 的 finally 補上 Remove-Item 修好，理由已過期，但判活
# 邏輯本身仍正確、不改（2026-08-31 訂正註解，「萬用」查到）。
$running = @(Get-Process -Name pwsh -ErrorAction SilentlyContinue |
             Where-Object { $_.Id -ne $PID }).Count
if ($running -gt 0) {
    Write-Host "⚠️ 偵測到 $running 個 pwsh 行程——可能有輪次正在跑。" -ForegroundColor Yellow
    Write-Host "   輪次進行中回滾會讓已呼叫 set-tc 的 agent 拿到 invalid choice 硬錯。"
    Write-Host "   請確認 _輪次紀錄.txt 最後一行是 DONE 再執行。"
    if (-not $DryRun) {
        $ans = Read-Host "   仍要繼續？(yes/no)"
        if ($ans -ne 'yes') { Write-Host "已中止。"; exit 1 }
    }
}

# ── 閘門 2：確認回滾點存在 ───────────────────────────────────────────────
# ^{commit} 是必要的：annotated tag 的 rev-parse 回傳的是 tag 物件的 sha，
# 不是它指向的 commit——直接印會讓人對不上 git log，回滾當下最不需要的就是這種困惑。
$baseSha = (& git -C $repo rev-parse --short "$base^{commit}" 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $baseSha) {
    Write-Host "❌ 找不到 tag '$base'，無法自動回滾。" -ForegroundColor Red
    Write-Host "   手動作法：git -C $repo log --oneline | 找到 'A10 v2 階段1+2' 的前一個 commit"
    exit 1
}

$head = (& git -C $repo rev-parse --short HEAD)
$commits = @(& git -C $repo log --oneline "$base..HEAD" -- `
                scripts/s2_state.py scripts/s2_token_metrics.py `
                common/13f-S2-大分類與各站規則.md scripts/prototype/)
Write-Host "回滾點 : $baseSha ($base)"
Write-Host "目前    : $head"
Write-Host "會被還原的 v2 相關 commit：$($commits.Count) 筆"
$commits | ForEach-Object { Write-Host "  $_" }

# ── 閘門 3：工作區必須乾淨（只看要回滾的那幾個檔） ───────────────────────
$dirty = @(& git -C $repo status --porcelain -- `
             scripts/s2_state.py scripts/s2_token_metrics.py `
             scripts/s2_render.py scripts/s2_render_html.py common/13f-S2-大分類與各站規則.md)
if ($dirty) {
    Write-Host "❌ 這些檔案有未提交的改動，先處理掉再回滾：" -ForegroundColor Red
    $dirty | ForEach-Object { Write-Host "  $_" }
    exit 1
}

if ($DryRun) { Write-Host "`n(DryRun：以上都沒有真的執行)" -ForegroundColor Yellow; exit 0 }

# ── 執行：只還原這三個檔到回滾點，不動其他人的 commit ───────────────────
# 用 checkout <tag> -- <path> 而不是 git revert：
# revert 會依 commit 逐一產生反向 patch、可能衝突；直接取回滾點的檔案內容
# 結果確定、一次到位，而且不會碰到同期間其他 session 的改動。
& git -C $repo checkout "$base" -- `
    scripts/s2_state.py `
    scripts/s2_token_metrics.py `
    scripts/s2_render.py `
    scripts/s2_render_html.py `
    common/13f-S2-大分類與各站規則.md
if ($LASTEXITCODE -ne 0) { Write-Host "❌ checkout 失敗" -ForegroundColor Red; exit 1 }

& git -C $repo commit -q -m @"
回滾 A10 v2（T/C）：還原 s2_state / token_metrics / 13f 到 $base

2000 輪（或之後）出問題，依 scripts/tc_v2_rollback.ps1 一鍵還原。
狀態檔裡既有的 tc 欄位刻意留著不清——舊版 render 不看它，無害。
"@
if ($LASTEXITCODE -ne 0) { Write-Host "❌ commit 失敗" -ForegroundColor Red; exit 1 }

# ── 驗證：set-tc 應該已經不存在 ──────────────────────────────────────────
$still = Select-String -Path (Join-Path $repo 'scripts\s2_state.py') -Pattern 'set-tc' -SimpleMatch -Quiet
if ($still) {
    Write-Host "❌ 回滾後 s2_state.py 仍含 set-tc，請人工檢查！" -ForegroundColor Red
    exit 1
}
& git -C $repo rev-parse --short HEAD | ForEach-Object { Write-Host "`n✅ 回滾完成，HEAD=$_" -ForegroundColor Green }
Write-Host "   下一輪自動生效，不必重啟排程／launcher／watchdog。"
Write-Host "   ⚠️ 記得跑：python scripts\s2_rules_check.py（應為 EXIT=0）"
