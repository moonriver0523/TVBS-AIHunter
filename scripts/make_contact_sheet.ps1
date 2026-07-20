param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [string]$OutputPath,

    [ValidateRange(1, 3600)]
    [double]$IntervalSeconds = 10,

    [ValidateRange(1, 12)]
    [int]$Columns = 4,

    [ValidateRange(1, 12)]
    [int]$Rows = 3,

    [ValidateRange(128, 1920)]
    [int]$FrameWidth = 480,

    [string]$FontPath = "C:\Windows\Fonts\msjh.ttc",

    [switch]$NoText
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
    throw "Input video not found: $InputPath"
}

$ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($null -eq $ffmpegCommand) {
    throw "ffmpeg is not available on PATH."
}

$resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $inputDirectory = [System.IO.Path]::GetDirectoryName($resolvedInput)
    $inputStem = [System.IO.Path]::GetFileNameWithoutExtension($resolvedInput)
    $OutputPath = [System.IO.Path]::Combine($inputDirectory, "$inputStem.contact.jpg")
}

$outputDirectory = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($OutputPath))
if (-not (Test-Path -LiteralPath $outputDirectory -PathType Container)) {
    throw "Output directory not found: $outputDirectory"
}
if (Test-Path -LiteralPath $OutputPath) {
    throw "Refusing to overwrite existing output: $OutputPath"
}

$interval = $IntervalSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$tile = "${Columns}x${Rows}"
$baseFilter = "fps=1/$interval,scale=${FrameWidth}:-1"
$tileFilter = "tile=${tile}:padding=4:margin=4"
$plainFilter = "$baseFilter,$tileFilter"

$useText = -not $NoText
if ($useText -and -not (Test-Path -LiteralPath $FontPath -PathType Leaf)) {
    Write-Warning "Font file not found; creating an unlabeled contact sheet: $FontPath"
    $useText = $false
}

$temporaryOutput = [System.IO.Path]::Combine(
    $outputDirectory,
    ".contact-sheet-$([guid]::NewGuid().ToString('N')).jpg"
)

function Invoke-ContactSheet {
    param([string]$VideoFilter)

    & $ffmpegCommand.Source `
        -hide_banner `
        -loglevel warning `
        -n `
        -i $resolvedInput `
        -vf $VideoFilter `
        -frames:v 1 `
        -update 1 `
        $temporaryOutput

    return $LASTEXITCODE
}

try {
    $exitCode = 1
    if ($useText) {
        $escapedFontPath = $FontPath.Replace("\", "/").Replace(":", "\:")
        $textFilter = "drawtext=fontfile='$escapedFontPath':text='%{pts\:hms}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.65:x=10:y=h-th-10"
        $exitCode = Invoke-ContactSheet "$baseFilter,$textFilter,$tileFilter"

        if ($exitCode -ne 0) {
            if (Test-Path -LiteralPath $temporaryOutput) {
                Remove-Item -LiteralPath $temporaryOutput -Force -Confirm:$false
            }
            Write-Warning "drawtext failed; retrying without text labels."
            $exitCode = Invoke-ContactSheet $plainFilter
        }
    }
    else {
        $exitCode = Invoke-ContactSheet $plainFilter
    }

    if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $temporaryOutput -PathType Leaf)) {
        throw "ffmpeg did not create a contact sheet (exit code $exitCode)."
    }

    Move-Item -LiteralPath $temporaryOutput -Destination $OutputPath
    Write-Output "Created: $OutputPath"
}
finally {
    if (Test-Path -LiteralPath $temporaryOutput) {
        Remove-Item -LiteralPath $temporaryOutput -Force -Confirm:$false
    }
}
