# 歐印萬掃帶資料夾即時監控腳本
# 固定間隔比對已知檔名集合，發現新的媒體檔且穩定(連續兩輪大小不變)後印出 NEW_FILE {完整路徑}
# 用法: pwsh -NoProfile -File oyinwan_watch.ps1 [-Folder <path>] [-IntervalSeconds 10]

param(
    [string]$Folder = "G:\我的雲端硬碟\Autopilot\(掃帶歐印萬) 檔名取TC起頭 6位數",
    [int]$IntervalSeconds = 10
)

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Get-MediaFiles {
    Get-ChildItem -LiteralPath $Folder -Recurse -Include *.wav, *.mxf, *.mp4 -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\Archive\\' }
}

$known = @{}
Get-MediaFiles | ForEach-Object { $known[$_.FullName] = $true }

Write-Output "WATCH_START $(Get-Date -Format o) known=$($known.Count) folder=$Folder"

$pending = @{}

while ($true) {
    Start-Sleep -Seconds $IntervalSeconds
    $current = Get-MediaFiles
    foreach ($f in $current) {
        if ($known.ContainsKey($f.FullName)) { continue }

        if ($pending.ContainsKey($f.FullName)) {
            $prev = $pending[$f.FullName]
            if ($f.Length -eq $prev.Length -and $f.Length -gt 0) {
                Write-Output "NEW_FILE $($f.FullName)"
                $known[$f.FullName] = $true
                $pending.Remove($f.FullName)
            } else {
                $pending[$f.FullName] = [PSCustomObject]@{ Length = $f.Length }
            }
        } else {
            $pending[$f.FullName] = [PSCustomObject]@{ Length = $f.Length }
        }
    }
}
