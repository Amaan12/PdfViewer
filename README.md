# Private GitHub PDF & EPUB Viewer

A lightweight, zero-configuration local server that lets you view PDF and EPUB files stored in **private** GitHub repositories directly in your browser.

---

## Features

- **Zero-Setup Authentication**: Automatically retrieves your existing GitHub OAuth credentials via Windows **Git Credential Manager** (`git credential fill`). No manual Personal Access Token (PAT) required.
- **Native Browser PDF Viewing**: Streams PDFs with `inline` disposition so your browser's native PDF reader (Edge, Chrome, Firefox) opens with full zooming, searching, thumbnails, and annotation support.
- **Dedicated Reflowable EPUB Reader**: A clean, lightning-fast in-browser e-book reader designed specifically for reading novels, docs, and books:
  - **Sub-50ms Instant Chapter Loading**: Chapters are loaded on-demand via Python backend streaming instead of sluggish client-side zip decompression.
  - **Full Chapter Navigation**: Table of Contents sidebar with 1-click jump to any chapter, plus Previous/Next chapter buttons.
  - **Keyboard Hotkeys**: Arrow keys (`←` / `→`) or `p` / `n` for chapters, `t` for TOC, `d` for theme toggle, `+` / `-` for font sizing.
  - **Visual Customizations**: Selectable font families (Georgia Serif, System Sans, Monospace), live font scaling (`12px` - `34px`), and 4 reader themes (Light, Warm Sepia, Slate Dark, and OLED Black).
  - **Auto-Resume Progress**: Automatically remembers your last read chapter and position in `localStorage`.
- **1-Click Bookmarklet**: Drag the bookmarklet from the dashboard to your browser bookmarks bar. While viewing any private GitHub file on github.com, click the bookmarklet to open it in the viewer immediately.
- **Repository Explorer**: Browse your private repositories and automatically scan for all `.pdf` and `.epub` files with direct "View" buttons.
- **Local Caching**: Caches downloaded documents in `.cache/` so reopening large files is instant and offline-capable.
- **CLI Support**: Launch and open files directly from the command line.

---

## Quickstart

### ⚡ 1-Click Setup (Desktop Shortcut & Taskbar Icon)
Run this once in PowerShell:
```powershell
irm https://raw.githubusercontent.com/Amaan12/PdfViewer/main/setup.ps1 | iex
```
- **Creates a `GitHub PDF Viewer` shortcut on your Desktop with a custom book icon.**
- **Right-click the desktop shortcut -> "Pin to taskbar"** to launch the viewer anytime in 1 click!
- Automatically installs required dependencies and opens your browser immediately.

---

### Method 2: 1-Line Direct Launch (No Shortcut)
```powershell
irm https://raw.githubusercontent.com/Amaan12/PdfViewer/main/run.ps1 | iex
```

---

### Method 2: Local Launcher
Double-click `run.bat` or run:
```powershell
python viewer.py
```
This starts the local server at `http://127.0.0.1:5000` and opens your browser.

---

## Usage Modes

### 1. Web Dashboard
1. Open `http://localhost:5000`.
2. Paste any GitHub URL (e.g. `https://github.com/owner/repo/blob/main/doc.pdf`).
3. Click **Open Document**.

### 2. Browser Bookmarklet (Fastest on GitHub)
1. On the dashboard (`http://localhost:5000`), drag the button **`📖 Open in GitHub PDF`** to your browser's bookmarks bar.
2. When browsing any PDF or EPUB in a private GitHub repository, click your new bookmarklet. It opens the viewer tab instantly.

### 3. CLI Direct Open
Open any document directly from your terminal:
```powershell
python viewer.py https://github.com/owner/repo/blob/main/path/to/book.pdf
```
```powershell
python viewer.py https://github.com/owner/repo/blob/main/path/to/novel.epub
```

### 4. Direct URL Prefix
Just like public services, you can prefix the viewer address in your browser:
```
http://localhost:5000/view?url=https://github.com/owner/repo/blob/main/doc.pdf
```

---

## CLI Options

| Argument | Description | Default |
| :--- | :--- | :--- |
| `url` | (Optional) GitHub file URL to view immediately | None |
| `--port` | Port to run the local server on | `5000` |
| `--host` | Host address | `127.0.0.1` |
| `--no-browser` | Run server without opening the browser | `False` |
---

## Managing & Deleting Downloaded Books (Cache)

When you view a book, it is saved to a local `.cache/` folder so reopening it is instantaneous. If you want to delete all downloaded books from your computer:

### Option 1: 1-Click from the Web Dashboard (Easiest)
Click the **`🗑️ Clear Book Cache`** button in the top right of the dashboard. This immediately deletes downloaded PDFs and EPUBs from your disk while keeping your reading history intact.

### Option 2: If using `run.bat` or Local Folder
- **Via Command**: Run in terminal:
  ```powershell
  python viewer.py --clear-cache
  ```
- **Via File Explorer**: Simply delete the `.cache` folder inside the `PdfViewer` folder.

### Option 3: If using the 1-Line PowerShell Command
Run this in PowerShell to delete all downloaded books:
```powershell
Remove-Item "$env:LOCALAPPDATA\PdfViewerApp\.cache" -Recurse -Force -ErrorAction SilentlyContinue
```
*(To completely remove the app as well, delete the `$env:LOCALAPPDATA\PdfViewerApp` folder).*

> **Note**: Deleting the cache only removes the local copies from your machine. Your original books on GitHub remain 100% safe and untouched.

---

## Requirements

- Python 3.8+ (tested on Python 3.14)
- Packages: `flask`, `requests` (already installed)
- Git for Windows (with Git Credential Manager)
