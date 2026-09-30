# One-line launcher for GitHub PDF & EPUB Viewer
# Usage in PowerShell:
# irm https://raw.githubusercontent.com/Amaan12/PdfViewer/main/run.ps1 | iex

$ErrorActionPreference = "Stop"

# 1. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[!] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "    Please install Python from https://www.python.org/downloads/ and check 'Add Python to PATH'."
    return
}

# 2. Setup temporary workspace & auto-update
$appDir = Join-Path $env:LOCALAPPDATA "PdfViewerApp"
$zipPath = Join-Path $env:TEMP "PdfViewer.zip"
$extractTarget = Join-Path $env:TEMP "PdfViewer-Extract"
$localVersionFile = Join-Path $appDir "version.json"

$needUpdate = $false
if (-not (Test-Path (Join-Path $appDir "viewer.py"))) {
    $needUpdate = $true
} else {
    try {
        # Check remote version from GitHub raw (fast ~150ms check)
        $remoteJson = Invoke-RestMethod "https://raw.githubusercontent.com/Amaan12/PdfViewer/main/version.json" -UseBasicParsing -TimeoutSec 3
        $remoteVer = $remoteJson.version
        $localVer = if (Test-Path $localVersionFile) { ((Get-Content $localVersionFile -Raw) | ConvertFrom-Json).version } else { "1.0.0" }
        if ($remoteVer -and ($remoteVer -ne $localVer)) {
            Write-Host "[*] New version detected (v$remoteVer vs local v$localVer). Updating..." -ForegroundColor Cyan
            $needUpdate = $true
        }
    } catch {
        # Offline or check timed out: proceed with existing local copy
        $needUpdate = $false
    }
}

if ($needUpdate) {
    Write-Host "[*] Fetching latest PdfViewer from GitHub..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null
    
    Invoke-RestMethod "https://github.com/Amaan12/PdfViewer/archive/refs/heads/main.zip" -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $extractTarget -Force
    
    $extractedFolder = Join-Path $extractTarget "PdfViewer-main"
    Copy-Item -Path "$extractedFolder\*" -Destination $appDir -Recurse -Force
    
    Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $extractTarget -Recurse -Force -ErrorAction SilentlyContinue
}

# 3. Ensure required packages (instant check)
python -c "import flask, requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] Installing required packages (Flask & Requests)..." -ForegroundColor Yellow
    python -m pip install flask requests -q
}

# 4. Run the viewer
Write-Host "[*] Launching GitHub PDF & EPUB Viewer..." -ForegroundColor Green
python (Join-Path $appDir "viewer.py") $args
