<#
Task 2（最小 Claude Code 啟動設定）前置測試骨架。2026-08-12 準備，
**2026-08-18 A0→A3 四組實跑全過**（結果見 MASTER T1；三旗標已上線 s2_scan.ps1，
回退開關 -NoMinBoot）：
    prefix：A0=62.0k → A1=51.9k → A2=47.3k → A3=43.5k（−30%）
    四組皆：browser MCP 可用、D9 hook 探測「有擋」（A3 沒吃掉 --settings 的 hook）、
    離開碼 0、OAuth 正常。

依計畫書 `common/20260812-S2省Token優化計畫-修訂版.md` 的 Task 2、原版 GPT 計畫書
第五節 Step 1~7 的 A0→A3 對照方法：每次只加一個變因，不能一次全開，
否則出事分不清是哪個旗標造成的。

    A0  現行旗標（s2_scan.ps1 目前的呼叫方式，基準線）
    A1  + --strict-mcp-config
    A2  + --disable-slash-commands
    A3  + --setting-sources（**唯一有實質風險的一刀，見下方安全閘門**）

✅ **A3 安全閘門已過（2026-08-12 查證）**：
`~/.claude.json`（user scope）裡確認存在 `oauthAccount`——這是排程唯一的登入憑證來源，
所以先查證 `--setting-sources` 排不排除得到它。官方文件（Agent SDK docs，
「What settingSources does not control」表）明講 `~/.claude.json` global config
是 **always read**，完全不受 `--setting-sources` 控制；同表也列了 managed policy
settings／auto memory／claude.ai MCP connectors 同樣不受影響。
**`--setting-sources project` 不會讓 OAuth 登入態消失，可以測。**
`--setting-sources` 真正會排除的只是 user／local 層的 `settings.json`
（permissions／hooks／env／model 這些設定），不是憑證本身。

用法：
    # 先看四組指令長什麼樣，不執行、不花錢：
    pwsh scripts\test_s2_launcher.ps1

    # 只跑 A0（基準線），真的呼叫 claude：
    pwsh scripts\test_s2_launcher.ps1 -Live -OnlySteps A0

    # 跑 A0→A2（略過 A3，A3 要單獨用 -OnlySteps A3 且已過安全閘門才跑）：
    pwsh scripts\test_s2_launcher.ps1 -Live -OnlySteps A0,A1,A2

每組用同一個**輕量驗證 prompt**（不是完整三站掃帶），目的只是量開機成本、
確認工具還在，不是要跑一輪真的掃帶——所以便宜、可以隨時重跑。
跑完用 `s2_token_metrics.py` 讀對應的 session transcript，比較各組的
prefix／cache_read／工具清單差異。
#>
[CmdletBinding()]
param(
    [string]$Repo = 'E:\GitHub\TVBS-AIHunter',
    [string]$McpConfig = "$PSScriptRoot\s2_mcp.json",
    [string]$Model = 'sonnet',

    # 真的執行才加這個旗標；不加只印出每組會跑的指令，不呼叫 claude、不花 token。
    [switch]$Live,

    # 限定只跑哪幾組（預設全部，但 A3 建議永遠手動單獨指定，過了安全閘門才跑）。
    [ValidateSet('A0', 'A1', 'A2', 'A3')]
    [string[]]$OnlySteps = @('A0', 'A1', 'A2', 'A3')
)

$ErrorActionPreference = 'Stop'
$outDir = Join-Path $Repo 'scripts\_task2_test_out'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# ── 2026-08-18 補強（T1 實跑前）──
# 1. claude 的 cwd 設成 $outDir：transcript 落在專屬的
#    ~\.claude\projects\{sanitized-outDir}，不跟互動 session 混在同一個目錄——
#    否則量測器「抓最新 .jsonl」會搶到正在跑的互動 session（advisor 抓到的洞）。
# 2. 量測帶 --transcript-dir 明講＋--dry-run 只印不寫：TASK2-* 不是生產輪，
#    不要寫進 _token_metrics.jsonl 汙染帳（比較用的數字從印出結果抄）。
# 3. 四組都掛 D9 的 guard settings（現行生產 s2_scan.ps1 就是這樣跑），並在
#    verify prompt 加 hook 探測步驟——A3 的 --setting-sources 是否吃掉 --settings
#    的 hook，文件推不出結論，要親眼看 deny 有沒有出現（D9×T1 交會點）。
Set-Location -LiteralPath $outDir
$guardSettings = (Join-Path $Repo 'scripts\s2_guard_settings.json') -replace '\\', '/'
$sanitizedOut = $outDir -replace '[^a-zA-Z0-9]', '-'
$transcriptDir = "$env:USERPROFILE\.claude\projects\$sanitizedOut"

# ── 輕量驗證 prompt：不掃帶，只驗證「工具還在、能跑」 ──────────────────
# 目的：A0→A3 每組都便宜到可以隨便重跑；真正的「掃帶還能不能用」驗收
# 要等這組低風險驗證都過了，再挑一個真實時段用 -TestMode 跑一次完整三站。
$verifyPrompt = @'
這是 Task 2 啟動設定驗證，不是正式掃帶，不要收任何素材、不要動狀態檔。
只做以下四件事，做完就結束：
1. 呼叫 mcp__browser__browser_navigate 打開 https://example.com
2. 呼叫 mcp__browser__browser_evaluate 執行 `() => document.title`，把結果印出來
3. 列出你目前能用的工具名稱清單（如果 skill／slash command 相關工具還在，一併列出）
4. 用 Bash 工具執行這條指令，並把工具回覆一字不漏轉述（這是 hook 防護探測，
   預期會被擋下——被擋下就是正確結果，不要重試、不要換寫法）：
   python -c "import json; json.load(open('probe-s2-state.json'))"
   轉述完請明講：「hook探測=有擋」或「hook探測=沒擋」。
只做這四步，不要多做，不要嘗試連線 NS／AP／RT 三站。
'@

# ── 四組旗標定義 ─────────────────────────────────────────────────────
# ⚠️ 每組都是「上一組 + 一個新變因」，不要跳著測，否則出事定位不到是哪個旗標。
$configs = [ordered]@{
    A0 = @()  # 基準線：跟 s2_scan.ps1 現行呼叫方式一致（不含 --effort，這裡不測 effort）
    A1 = @('--strict-mcp-config')
    A2 = @('--strict-mcp-config', '--disable-slash-commands')
    # A3：--setting-sources project 排除 user scope。過安全閘門後才解除下面的註解式警告。
    A3 = @('--strict-mcp-config', '--disable-slash-commands', '--setting-sources', 'project')
}

foreach ($step in $OnlySteps) {
    $flags = $configs[$step]
    $checkpoint = "TASK2-$step-$(Get-Date -Format 'HHmmss')"
    $args = @(
        '-p', $verifyPrompt,
        '--permission-mode', 'bypassPermissions',
        '--model', $Model,
        '--mcp-config', $McpConfig,
        '--add-dir', $Repo,
        '--settings', $guardSettings,   # 現行生產就掛著（D9），四組一致才是真 A0 基準
        '--output-format', 'stream-json', '--verbose'
    ) + $flags

    Write-Host "=== $step ===" -ForegroundColor Cyan
    Write-Host "claude $($args -join ' ')"

    if (-not $Live) {
        Write-Host "（-Live 沒帶，只顯示指令，不執行）`n" -ForegroundColor DarkGray
        continue
    }

    if ($step -eq 'A3') {
        Write-Host "A3：--setting-sources project（OAuth 憑證 always read，見檔頭安全閘門查證，可以測）" -ForegroundColor DarkGray
    }

    $logPath = Join-Path $outDir "$checkpoint.jsonl"
    $t0 = Get-Date
    & claude @args *> $logPath
    $code = $LASTEXITCODE
    $mins = [Math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    Write-Host "$step 完成：離開碼=$code 耗時=${mins}秒 log=$logPath"

    # 量測：跟 s2_scan.ps1 收工掛勾用同一支工具。
    # --transcript-dir 明講（cwd=$outDir 的專屬目錄，不搶互動 session 的檔）；
    # --dry-run 只印不寫（TASK2-* 不是生產輪，不進 _token_metrics.jsonl）。
    try {
        python "$PSScriptRoot\s2_token_metrics.py" --checkpoint $checkpoint `
            --transcript-dir $transcriptDir --dry-run `
            --flags "task2=$step" 2>&1 | Tee-Object -FilePath (Join-Path $outDir "$checkpoint.metrics.txt")
    } catch {
        Write-Warning "量測失敗：$($_.Exception.Message)"
    }
    Write-Host ""
}

if (-not $Live) {
    Write-Host "全部只是預覽。要真的跑：pwsh test_s2_launcher.ps1 -Live -OnlySteps A0" -ForegroundColor Yellow
}
