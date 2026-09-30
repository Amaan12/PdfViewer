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

# 2. Setup temporary workspace
$appDir = Join-Path $env:LOCALAPPDATA "PdfViewerApp"
$zipPath = Join-Path $env:TEMP "PdfViewer.zip"
$extractTarget = Join-Path $env:TEMP "PdfViewer-Extract"

# Auto-update / download repository files
if (-not (Test-Path (Join-Path $appDir "viewer.py"))) {
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
