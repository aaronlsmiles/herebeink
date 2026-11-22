<#
.SYNOPSIS
  Train the measured splat with LichtFeld Studio on the RTX laptop.

.DESCRIPTION
  Records the GPU, checks the driver, checks that this LichtFeld build knows every flag used here,
  trains 500 iterations on the 20-image dry-run set, then the full 30,000 iterations, and copies the
  result to out\splat_raw.ply. Everything printed is also saved under out\.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\train.ps1 -Exe "C:\Program Files\LichtFeld Studio\bin\LichtFeld-Studio.exe"
#>
param(
  [string]$Exe = "lichtfeld-studio",
  [string]$Dataset = ".\train",
  [string]$DryDataset = ".\train_dry",
  [string]$Out = ".\out",
  [int]$Iterations = 30000,
  [int]$MaxCap = 1500000,
  [switch]$SkipDryRun
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Write-Step([string]$Text) { Write-Host ""; Write-Host "== $Text" -ForegroundColor Cyan }

function Invoke-LichtFeld([string]$Log, [string[]]$Arguments) {
  # Windows PowerShell turns a native program's stderr into errors; let it through and judge by the exit code.
  $saved = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $Log
  $code = $LASTEXITCODE
  $ErrorActionPreference = $saved
  if ($code -ne 0) { throw "LichtFeld Studio stopped with exit code $code. The full output is in $Log." }
}

function Find-NewestPly([string]$Folder) {
  Get-ChildItem -Path $Folder -Recurse -Filter *.ply -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

Write-Step "1. The GPU (record these four in STATUS)"
$gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader) | Select-Object -First 1
if (-not $gpu) { throw "nvidia-smi gave no answer: is the NVIDIA driver installed?" }
$gpu | Set-Content (Join-Path $Out "gpu.txt")
$name, $vram, $driver, $cap = $gpu.Split(",") | ForEach-Object { $_.Trim() }
Write-Host "GPU: $name   VRAM: $vram   driver: $driver   compute capability: $cap"
# LichtFeld's Windows builds carry kernels for compute capability 7.5 (RTX 20 / GTX 16) and up only.
if ([double]::Parse($cap, [Globalization.CultureInfo]::InvariantCulture) -lt 7.5) {
  throw "This card's compute capability is $cap; LichtFeld Studio needs 7.5 or newer (RTX 20 / GTX 16 series or later). Train with Brush instead (see README)."
}
if ([int]($driver.Split(".")[0]) -lt 570) {
  throw "Driver $driver is older than 570, which LichtFeld Studio needs. Update it from the NVIDIA app, then run this again."
}

Write-Step "2. Does this LichtFeld Studio know the flags this script uses?"
if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) {
  throw "Cannot find LichtFeld Studio at '$Exe'. Pass its full path: -Exe 'C:\...\LichtFeld-Studio.exe'"
}
$help = (& $Exe --help 2>&1 | ForEach-Object { "$_" }) -join "`n"
$help | Set-Content (Join-Path $Out "lichtfeld-help.txt")
$needed = @("--headless", "--train", "--strategy", "--max-cap", "--sh-degree", "--max-width", "--eval")
$missing = $needed | Where-Object { $help -notmatch [regex]::Escape($_) }
if ($missing) {
  throw "This build's --help does not list: $($missing -join ', '). Read out\lichtfeld-help.txt, change the arguments below to its names, and run again."
}
Write-Host "All flags found. (Help saved to out\lichtfeld-help.txt.)"

$common = @("--headless", "--train", "--strategy", "mcmc", "--sh-degree", "3", "-r", "1", "--max-width", "1440")

if (-not $SkipDryRun) {
  Write-Step "3. Dry run: 20 images, 500 iterations (a minute or two)"
  $dryOut = Join-Path $Out "dry"
  Invoke-LichtFeld (Join-Path $Out "dry-output.txt") (@("-d", $DryDataset, "-o", $dryOut, "-i", "500", "--max-cap", "100000") + $common)
  if (-not (Find-NewestPly $dryOut)) { throw "The dry run finished but wrote no .ply under $dryOut. Read out\dry-output.txt." }
  Write-Host "Dry run wrote a splat. The loader reads this dataset layout."
}

Write-Step "4. Full training: $Iterations iterations, at most $MaxCap splats (expect one to three hours)"
$fullOut = Join-Path $Out "full"
$clock = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-LichtFeld (Join-Path $Out "full-output.txt") (@("-d", $Dataset, "-o", $fullOut, "-i", "$Iterations", "--max-cap", "$MaxCap", "--eval") + $common)
$clock.Stop()
$ply = Find-NewestPly $fullOut
if (-not $ply) { throw "Training finished but wrote no .ply under $fullOut. Read out\full-output.txt." }
Copy-Item $ply.FullName (Join-Path $Out "splat_raw.ply") -Force
$minutes = [math]::Round($clock.Elapsed.TotalMinutes, 1)
"minutes: $minutes`nsource: $($ply.FullName)`nbytes: $($ply.Length)" | Set-Content (Join-Path $Out "train-summary.txt")

Write-Step "Done in $minutes minutes"
Write-Host "Copy these back to the Mac, into pipeline\work\splat\ :"
Write-Host "  out\splat_raw.ply, out\gpu.txt, out\train-summary.txt, out\full-output.txt"
