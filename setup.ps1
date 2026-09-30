# 1-Click Setup & Desktop Shortcut Installer for GitHub PDF & EPUB Viewer
# Run in PowerShell:
# irm https://raw.githubusercontent.com/Amaan12/PdfViewer/main/setup.ps1 | iex

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Installing GitHub PDF & EPUB Viewer (1-Click Setup)...   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[!] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "    Please install Python from https://www.python.org/downloads/ and check 'Add Python to PATH'."
    return
}

# 2. Setup directory in AppData
$appDir = Join-Path $env:LOCALAPPDATA "PdfViewerApp"
$zipPath = Join-Path $env:TEMP "PdfViewer.zip"
$extractTarget = Join-Path $env:TEMP "PdfViewer-Extract"

Write-Host "[*] Fetching latest files from GitHub..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $appDir -Force | Out-Null

Invoke-RestMethod "https://github.com/Amaan12/PdfViewer/archive/refs/heads/main.zip" -OutFile $zipPath
Expand-Archive -Path $zipPath -DestinationPath $extractTarget -Force

$extractedFolder = Join-Path $extractTarget "PdfViewer-main"
Copy-Item -Path "$extractedFolder\*" -Destination $appDir -Recurse -Force

Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item -Path $extractTarget -Recurse -Force -ErrorAction SilentlyContinue

# 3. Ensure required packages
python -c "import flask, requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] Installing required packages (Flask & Requests)..." -ForegroundColor Yellow
    python -m pip install flask requests -q
}

# 4. Create Desktop Shortcut with Book Icon
$desktopPath = [System.Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktopPath "GitHub PDF Viewer.lnk"
$icoPath = Join-Path $appDir "book.ico"
$viewerPath = Join-Path $appDir "viewer.py"

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($desktopShortcutPath)
$sc.TargetPath = "C:\Windows\System32\cmd.exe"
$sc.Arguments = "/c start `"`" pythonw `"$viewerPath`""
$sc.WorkingDirectory = $appDir
if (Test-Path $icoPath) {
    $sc.IconLocation = "$icoPath,0"
}
$sc.Description = "GitHub PDF & EPUB Viewer"
$sc.WindowStyle = 7
$sc.Save()

# 5. Create Start Menu Shortcut (allows searching 'PDF' in Start Menu)
$startMenuDir = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs")
if (Test-Path $startMenuDir) {
    $startSc = $wsh.CreateShortcut((Join-Path $startMenuDir "GitHub PDF Viewer.lnk"))
    $startSc.TargetPath = "C:\Windows\System32\cmd.exe"
    $startSc.Arguments = "/c start `"`" pythonw `"$viewerPath`""
    $startSc.WorkingDirectory = $appDir
    if (Test-Path $icoPath) {
        $startSc.IconLocation = "$icoPath,0"
    }
    $startSc.Description = "GitHub PDF & EPUB Viewer"
    $startSc.WindowStyle = 7
    $startSc.Save()
}

Write-Host "`n[OK] Setup Completed Successfully!" -ForegroundColor Green
Write-Host " Shortcut Created: $desktopShortcutPath" -ForegroundColor White
Write-Host " Book Icon:        $icoPath" -ForegroundColor White
Write-Host "`nTo pin it to your Taskbar:" -ForegroundColor Yellow
Write-Host "  1. Right-click the 'GitHub PDF Viewer' icon on your Desktop."
Write-Host "  2. Select 'Pin to taskbar' (Win 11: 'Show more options' -> 'Pin to taskbar')."
Write-Host "  3. Now you can click it anytime from your taskbar in 1 second!`n"

# 6. Stop any older running instances and launch the fresh AppData viewer
Write-Host "[*] Launching GitHub PDF & EPUB Viewer..." -ForegroundColor Green
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' or Name = 'python.exe'" -ErrorAction SilentlyContinue | 
    Where-Object { $_.CommandLine -like "*viewer.py*" } | 
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 400

Start-Process "C:\Windows\System32\cmd.exe" -ArgumentList "/c start `"`" pythonw `"$viewerPath`"" -WindowStyle Hidden
