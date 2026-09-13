# 用關鍵字(通常是6碼TC或英文片段,避免console亂碼)在歐印萬資料夾裡解出正確檔名
# 用法: pwsh -NoProfile -File resolve_name.ps1 -Keyword 150120

param(
    [Parameter(Mandatory = $true)][string]$Keyword,
    [string]$Folder = "G:\我的雲端硬碟\Autopilot\(掃帶歐印萬) 檔名取TC起頭 6位數"
)

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

Get-ChildItem -LiteralPath $Folder -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\Archive\\' -and $_.Name -like "*$Keyword*" } |
    Select-Object -ExpandProperty FullName
