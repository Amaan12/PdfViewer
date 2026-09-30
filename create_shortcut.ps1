# Creates a 1-click Desktop Shortcut with the custom Book Icon
# Compatible with Windows "Pin to taskbar" and "Pin to Start"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }

$icoPath = Join-Path $scriptDir "book.ico"
$viewerPath = Join-Path $scriptDir "viewer.py"
$desktopPath = [System.Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "GitHub PDF Viewer.lnk"

# Ensure icon exists
if (-not (Test-Path $icoPath)) {
    Write-Host "[*] Generating book icon..." -ForegroundColor Cyan
    python -c "from PIL import Image, ImageDraw; img = Image.new('RGBA', (256, 256), (0,0,0,0)); draw = ImageDraw.Draw(img); draw.ellipse([20,215,236,250], fill=(15,23,42,70)); draw.rounded_rectangle([28,25,228,222], radius=16, fill=(30,58,138,255)); draw.rounded_rectangle([45,35,218,212], radius=10, fill=(248,250,252,255)); draw.rounded_rectangle([28,25,190,222], radius=16, fill=(37,99,235,255)); draw.polygon([(135,30),(152,30),(152,238),(143.5,226),(135,238)], fill=(239,68,68,255)); img.save('$($icoPath -replace '\\', '\\\\')', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
}

# Create Windows Shortcut
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "C:\Windows\System32\cmd.exe"
$shortcut.Arguments = "/c start `"`" pythonw `"$viewerPath`""
$shortcut.WorkingDirectory = $scriptDir
$shortcut.IconLocation = "$icoPath,0"
$shortcut.Description = "GitHub PDF & EPUB Viewer - Stream & view private repo documents"
$shortcut.WindowStyle = 7 # Minimized
$shortcut.Save()

# Also create in Start Menu for instant Win key search
$startMenuDir = [System.IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs")
if (Test-Path $startMenuDir) {
    $startShortcut = $wsh.CreateShortcut((Join-Path $startMenuDir "GitHub PDF Viewer.lnk"))
    $startShortcut.TargetPath = "C:\Windows\System32\cmd.exe"
    $startShortcut.Arguments = "/c start `"`" pythonw `"$viewerPath`""
    $startShortcut.WorkingDirectory = $scriptDir
    $startShortcut.IconLocation = "$icoPath,0"
    $startShortcut.Description = "GitHub PDF & EPUB Viewer"
    $startShortcut.WindowStyle = 7
    $startShortcut.Save()
}

Write-Host "`n=======================================================" -ForegroundColor Green
Write-Host " [OK] 1-Click Shortcut Created Successfully!" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
Write-Host " Location: $shortcutPath" -ForegroundColor White
Write-Host " Icon:     $icoPath" -ForegroundColor White
Write-Host "`nTo pin it to your Taskbar:" -ForegroundColor Yellow
Write-Host "  1. Look at your Desktop for 'GitHub PDF Viewer' (book icon)."
Write-Host "  2. Right-click it and choose 'Pin to taskbar' (or 'Show more options' -> 'Pin to taskbar' on Win 11)."
Write-Host "  3. Now you can click it anytime from your taskbar in 1 second!`n"
