<#
.SYNOPSIS
    Restore data besar dari external drive (Windows padanan restore_data_from_external.sh).
    Mengembalikan data dari E:\projects\market\ ke project directory.
    File yang di-split (FAT32) akan di-rejoin otomatis.

.DESCRIPTION
    Windows equivalent of scripts/restore_data_from_external.sh.

.PARAMETER ProjectDir
    Project directory (default: C:\xampp\htdocs\market).

.PARAMETER ExternalBase
    External drive backup path (default: E:\projects\market).

.EXAMPLE
    .\restore_data_from_external.ps1
    .\restore_data_from_external.ps1 -ProjectDir D:\market -ExternalBase F:\backup

.NOTES
    Cross-platform: see also restore_data_from_external.sh for Linux.
    References: AGENTS.md §7 (Cross-Platform OS Awareness).
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = "C:\xampp\htdocs\market",
    [string]$ExternalBase = "E:\projects\market"
)

$ErrorActionPreference = 'Stop'

# ── Config ──────────────────────────────────────────────────────────
# Items to restore: destination path (relative to project) <- source subfolder
$RESTORE_ITEMS = @(
    @{ Dest = "data\market_research.db";  Src = "database" }
    @{ Dest = "data\market_paper.db";     Src = "database" }
    @{ Dest = "data\market_live.db";      Src = "database" }
    @{ Dest = "data\dataset-saham-idx";   Src = "dataset-saham-idx" }
    @{ Dest = "data\backups";             Src = "database\backups" }
    @{ Dest = "data\parquet_export";      Src = "parquet\export" }
    @{ Dest = "data\parquet_seeds";       Src = "parquet\seeds" }
)

# ── Helpers ─────────────────────────────────────────────────────────
function Log($msg)  { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" }
function Ok($msg)   { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] WARN $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERROR $msg" -ForegroundColor Red }

function Format-Size([int64]$bytes) {
    if ($bytes -ge 1GB) { return "{0:N2} GB" -f ($bytes / 1GB) }
    elseif ($bytes -ge 1MB) { return "{0:N1} MB" -f ($bytes / 1MB) }
    elseif ($bytes -ge 1KB) { return "{0:N1} KB" -f ($bytes / 1KB) }
    else { return "$bytes B" }
}

function Join-File {
    param([string[]]$Parts, [string]$DestPath)
    $destDir = [System.IO.Path]::GetDirectoryName($DestPath)
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }

    $dstStream = [System.IO.File]::Create($DestPath)
    try {
        $buffer = New-Object byte[] 8388608  # 8 MB
        foreach ($part in $Parts) {
            $srcStream = [System.IO.File]::OpenRead($part)
            try {
                while ($true) {
                    $read = $srcStream.Read($buffer, 0, $buffer.Length)
                    if ($read -eq 0) { break }
                    $dstStream.Write($buffer, 0, $read)
                }
            } finally { $srcStream.Close() }
        }
    } finally { $dstStream.Close() }
}

# ── Pre-flight ─────────────────────────────────────────────────────
if (-not (Test-Path $ExternalBase)) {
    Err "External drive tidak terdeteksi: $ExternalBase"
    Err "Mount flashdisk dulu, lalu jalankan ulang skrip ini."
    exit 1
}
if (-not (Test-Path $ProjectDir)) {
    Err "Project directory tidak ditemukan: $ProjectDir"
    Err "Set -ProjectDir jika path berbeda."
    exit 1
}

Log "Source:  $ExternalBase"
Log "Target:  $ProjectDir"
Log ""

# ── Restore loop ───────────────────────────────────────────────────
$restored = 0; $skipped = 0; $failed = 0

foreach ($item in $RESTORE_ITEMS) {
    $destAbs = Join-Path $ProjectDir $item.Dest
    $srcAbs = Join-Path $ExternalBase $item.Src

    if (-not (Test-Path $srcAbs)) {
        Warn "Skip (tidak ada di external): $($item.Src)"
        $skipped++; continue
    }

    # Check for split chunks (part.00, part.01, ...)
    $fileName = [System.IO.Path]::GetFileName($item.Dest)
    $partPrefix = "$fileName.part."
    $parts = Get-ChildItem -Path $srcAbs -Filter "$partPrefix*" -ErrorAction SilentlyContinue | Sort-Object Name

    if ($parts) {
        Log "Restoring (rejoin): $($item.Dest) <- $($item.Src)"
        try {
            $partPaths = $parts | ForEach-Object { $_.FullName }
            Join-File -Parts $partPaths -DestPath $destAbs
            $destSize = (Get-Item $destAbs).Length
            Ok "Restored: $($item.Dest) ($(Format-Size $destSize), $($parts.Count) chunks rejoined)"
            $restored++
        } catch {
            Err "Failed (rejoin): $($item.Dest) — $_"
            $failed++
        }
        continue
    }

    # Normal copy (file or directory)
    Log "Restoring: $($item.Dest) <- $($item.Src)"
    try {
        $destParent = [System.IO.Path]::GetDirectoryName($destAbs)
        if (-not (Test-Path $destParent)) { New-Item -ItemType Directory -Path $destParent -Force | Out-Null }

        if (Test-Path $srcAbs -PathType Leaf) {
            Copy-Item $srcAbs $destAbs -Force
        } else {
            # Directory: copy contents
            Copy-Item $srcAbs $destAbs -Recurse -Force
        }
        $destSize = if (Test-Path $destAbs -PathType Leaf) {
            (Get-Item $destAbs).Length
        } else {
            (Get-ChildItem $destAbs -Recurse -File | Measure-Object -Property Length -Sum).Sum
        }
        Ok "Restored: $($item.Dest) ($(Format-Size $destSize))"
        $restored++
    } catch {
        Err "Failed: $($item.Dest) — $_"
        $failed++
    }
}

# ── Summary ────────────────────────────────────────────────────────
Log ""
Log "========================================"
Log "  RINGKASAN RESTORE DATA"
Log "  Restored: $restored"
Log "  Skipped:  $skipped"
Log "  Failed:   $failed"
Log "  Source:   $ExternalBase"
Log "========================================"

if ($failed -gt 0) {
    Err "Ada $failed item yang gagal."
    exit 1
}
Ok "Selesai. Data restored ke $ProjectDir"
