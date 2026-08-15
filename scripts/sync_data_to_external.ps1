<#
.SYNOPSIS
    Sync data besar ke external drive (Windows padanan sync_data_to_external.sh).
    Menyalin SQLite DB, dataset CSV, dan Parquet ke E:\projects\market\.
    File DB > 2GB akan di-split menjadi parts 2GB untuk kompatibilitas FAT32.

.DESCRIPTION
    Windows equivalent of scripts/sync_data_to_external.sh.
    Uses Copy-Item for normal files and custom .NET stream split for DB > 2GB.

.PARAMETER Move
    Hapus source setelah copy berhasil (default: false = copy only).

.PARAMETER ProjectDir
    Project directory (default: C:\xampp\htdocs\market).

.PARAMETER ExternalBase
    External drive backup path (default: E:\projects\market).

.EXAMPLE
    .\sync_data_to_external.ps1
    .\sync_data_to_external.ps1 -Move
    .\sync_data_to_external.ps1 -ProjectDir D:\market -ExternalBase F:\backup

.NOTES
    Cross-platform: see also sync_data_to_external.sh for Linux.
    References: AGENTS.md §7 (Cross-Platform OS Awareness).
#>
[CmdletBinding()]
param(
    [switch]$Move,
    [string]$ProjectDir = "C:\xampp\htdocs\market",
    [string]$ExternalBase = "E:\projects\market",
    [int]$ChunkSizeMB = 2048
)

$ErrorActionPreference = 'Stop'

# ── Config ──────────────────────────────────────────────────────────
$MODE = if ($Move) { "move" } else { "copy" }

# Items to sync: source path (relative to project) -> destination subfolder
$SYNC_ITEMS = @(
    # SQLite legacy DBs (market_research.db & market_paper.db sudah tidak ada)
    @{ Src = "data\market_live.db";            Dest = "database" }
    @{ Src = "data\dataset-saham-idx";         Dest = "dataset-saham-idx" }
    @{ Src = "data\backups";                   Dest = "database\backups" }
    @{ Src = "data\parquet_export";            Dest = "parquet\export" }
    @{ Src = "data\parquet_seeds";             Dest = "parquet\seeds" }
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

function Split-File {
    param([string]$Source, [string]$DestDir, [int64]$ChunkSize)
    $fileName = [System.IO.Path]::GetFileName($Source)
    $fileSize = (Get-Item $Source).Length
    $numChunks = [math]::Ceiling([double]$fileSize / $ChunkSize)
    $partPrefix = "$fileName.part."

    # Remove old parts
    Get-ChildItem -Path $DestDir -Filter "$partPrefix*" -ErrorAction SilentlyContinue | Remove-Item -Force

    $srcStream = [System.IO.File]::OpenRead($Source)
    try {
        $buffer = New-Object byte[] 8388608  # 8 MB
        for ($i = 0; $i -lt $numChunks; $i++) {
            $partName = "{0}{1:D2}" -f $partPrefix, $i
            $partPath = Join-Path $DestDir $partName
            $partSize = if ($i -eq ($numChunks - 1)) { $fileSize - ($i * $ChunkSize) } else { $ChunkSize }
            Log "  Writing $partName ($(Format-Size $partSize))..."
            $dstStream = [System.IO.File]::Create($partPath)
            try {
                $remaining = $partSize
                while ($remaining -gt 0) {
                    $toRead = [math]::Min([int64]$buffer.Length, [int64]$remaining)
                    $read = $srcStream.Read($buffer, 0, $toRead)
                    if ($read -eq 0) { break }
                    $dstStream.Write($buffer, 0, $read)
                    $remaining -= $read
                }
            } finally { $dstStream.Close() }
        }
    } finally { $srcStream.Close() }
    return $numChunks
}

# ── Pre-flight checks ──────────────────────────────────────────────
if (-not (Test-Path $ExternalBase)) {
    Err "External drive tidak terdeteksi: $ExternalBase"
    Err "Pastikan flashdisk sudah di-mount."
    exit 1
}
if (-not (Test-Path $ProjectDir)) {
    Err "Project directory tidak ditemukan: $ProjectDir"
    exit 1
}

Log "Mode:   $MODE"
Log "Source: $ProjectDir"
Log "Target: $ExternalBase"
Log ""

# ── Sync loop ──────────────────────────────────────────────────────
$synced = 0; $skipped = 0; $failed = 0
$chunkSize = [int64]($ChunkSizeMB * 1MB)

foreach ($item in $SYNC_ITEMS) {
    $srcAbs = Join-Path $ProjectDir $item.Src
    $destAbs = Join-Path $ExternalBase $item.Dest

    if (-not (Test-Path $srcAbs)) {
        Warn "Skip (tidak ada): $($item.Src)"
        $skipped++; continue
    }

    # Get size
    $size = if (Test-Path $srcAbs -PathType Leaf) {
        (Get-Item $srcAbs).Length
    } else {
        (Get-ChildItem $srcAbs -Recurse -File | Measure-Object -Property Length -Sum).Sum
    }
    Log "Syncing: $($item.Src) ($(Format-Size $size)) -> $($item.Dest)"

    # Create destination parent
    New-Item -ItemType Directory -Path $destAbs -Force | Out-Null

    # Check if file > 2GB and should be split (FAT32 safety)
    if ((Test-Path $srcAbs -PathType Leaf) -and $size -gt $chunkSize) {
        Log "  File > 2GB — splitting into $(Format-Size $chunkSize) chunks..."
        try {
            $numChunks = Split-File -Source $srcAbs -DestDir $destAbs -ChunkSize $chunkSize
            Ok "Synced (split): $($item.Src) -> $numChunks chunks"
            $synced++
            if ($Move) {
                Remove-Item $srcAbs -Force
                Log "Removed source: $($item.Src)"
            }
        } catch {
            Err "Failed (split): $($item.Src) — $_"
            $failed++
        }
        continue
    }

    # Normal copy (file or directory)
    try {
        if (Test-Path $srcAbs -PathType Leaf) {
            Copy-Item $srcAbs $destAbs -Force
        } else {
            # Directory: copy contents, preserve structure
            Copy-Item $srcAbs $destAbs -Recurse -Force
        }
        Ok "Synced: $($item.Src)"
        $synced++
        if ($Move) {
            Remove-Item $srcAbs -Recurse -Force
            Log "Removed source: $($item.Src)"
        }
    } catch {
        Err "Failed: $($item.Src) — $_"
        $failed++
    }
}

# ── Summary ────────────────────────────────────────────────────────
Log ""
Log "========================================"
Log "  RINGKASAN SYNC DATA"
Log "  Synced:  $synced"
Log "  Skipped: $skipped"
Log "  Failed:  $failed"
Log "  Mode:    $MODE"
Log "  Target:  $ExternalBase"
Log "========================================"

if ($failed -gt 0) {
    Err "Ada $failed item yang gagal. Cek log di atas."
    exit 1
}
Ok "Selesai. Data tersimpan di $ExternalBase"
