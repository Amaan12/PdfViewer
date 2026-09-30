"""
Private GitHub PDF & EPUB Viewer
A lightweight local server for viewing PDFs and EPUBs from private GitHub repositories.
Uses Git Credential Manager for zero-configuration authentication.
Fully supports Git LFS (Large File Storage) pointers, streaming authentic binaries from media.githubusercontent.com.
Includes a lightning-fast native EPUB reflowable reader and browser PDF viewer.
"""

import os
import sys
import re
import time
import argparse
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path
from flask import Flask, render_template, request, Response, jsonify, send_file, redirect, abort
import requests

from epub_reader import get_epub_metadata_and_spine, extract_chapter_html, read_epub_asset
from epub_converter import convert_epub_to_pdf

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

app = Flask(__name__, template_folder=str(APP_DIR / "templates"), static_folder=str(APP_DIR / "static"))

# In-memory cache for user repos to avoid rate-limiting
_REPOS_CACHE = {"timestamp": 0, "data": []}
_TOKEN_CACHE = {"token": None, "username": None}


def get_git_credentials():
    """Extract GitHub OAuth token and username using Git Credential Manager."""
    if _TOKEN_CACHE["token"]:
        return _TOKEN_CACHE["token"], _TOKEN_CACHE["username"]

    # Check env var fallback
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        _TOKEN_CACHE["token"] = env_token
        _TOKEN_CACHE["username"] = os.environ.get("GITHUB_USER", "env_user")
        return _TOKEN_CACHE["token"], _TOKEN_CACHE["username"]

    try:
        proc = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, _ = proc.communicate("protocol=https\nhost=github.com\n\n", timeout=5)
        creds = {}
        for line in stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()

        token = creds.get("password")
        username = creds.get("username", "Authenticated User")
        if token:
            _TOKEN_CACHE["token"] = token
            _TOKEN_CACHE["username"] = username
            return token, username
    except Exception as e:
        print(f"[Warning] Failed to retrieve git credentials: {e}", file=sys.stderr)

    return None, None


def parse_github_url(url: str):
    """
    Parse a GitHub file URL into owner, repo, ref, and file path.
    Supports formats:
      - https://github.com/owner/repo/blob/ref/path/to/file.ext
      - https://github.com/owner/repo/raw/ref/path/to/file.ext
      - https://raw.githubusercontent.com/owner/repo/ref/path/to/file.ext
      - owner/repo/blob/ref/path/to/file.ext
      - owner/repo/ref/path/to/file.ext
    """
    url = url.strip()
    url = urllib.parse.unquote(url)
    url = re.sub(r'^(?:https?://)?(?:www\.)?', '', url)

    # 1. github.com/owner/repo/blob|raw/ref/path
    m = re.match(r'^github\.com/([^/]+)/([^/]+)/(?:blob|raw)/([^/]+)/(.+)$', url)
    if m:
        return {
            "owner": m.group(1),
            "repo": m.group(2),
            "ref": m.group(3),
            "path": m.group(4)
        }

    # 2. raw.githubusercontent.com/owner/repo/ref/path
    m_raw = re.match(r'^raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$', url)
    if m_raw:
        return {
            "owner": m_raw.group(1),
            "repo": m_raw.group(2),
            "ref": m_raw.group(3),
            "path": m_raw.group(4)
        }

    # 3. Direct short format: owner/repo/ref/path
    m_short = re.match(r'^([^/]+)/([^/]+)/([^/]+)/(.+)$', url)
    if m_short:
        return {
            "owner": m_short.group(1),
            "repo": m_short.group(2),
            "ref": m_short.group(3),
            "path": m_short.group(4)
        }

    return None


def fetch_github_file(owner: str, repo: str, ref: str, file_path: str, use_cache: bool = True):
    """
    Fetch file bytes from private GitHub repository with local disk caching.
    Automatically detects Git LFS pointers and fetches the authentic binary from media.githubusercontent.com.
    Returns (Path to cached file, error string).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{owner}_{repo}_{ref}_{file_path.replace('/', '_').replace('\\', '_')}"
    cached_file = CACHE_DIR / safe_name

    # Check existing cache
    if use_cache and cached_file.exists() and cached_file.stat().st_size > 0:
        # If small, verify it's not a leftover Git LFS pointer text file
        if cached_file.stat().st_size < 500:
            try:
                with open(cached_file, "rb") as f:
                    head = f.read(100)
                if head.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    cached_file.unlink(missing_ok=True)
                else:
                    return cached_file, None
            except Exception:
                pass
        else:
            return cached_file, None

    token, _ = get_git_credentials()
    headers = {"User-Agent": "GitHub-PdfViewer/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"

    encoded_path = urllib.parse.quote(file_path, safe="/")
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{encoded_path}"
    media_url = f"https://media.githubusercontent.com/media/{owner}/{repo}/{ref}/{encoded_path}"

    # Method 1: Try raw.githubusercontent.com, detect LFS pointer
    try:
        with requests.get(raw_url, headers=headers, stream=True, timeout=60) as r:
            if r.status_code == 200:
                first_chunk = next(r.iter_content(chunk_size=1024), b"")
                # If Git LFS pointer text file, stream from media.githubusercontent.com
                if first_chunk.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    print(f"[*] Detected Git LFS pointer for {file_path}. Downloading from media.githubusercontent.com...")
                    with requests.get(media_url, headers=headers, stream=True, timeout=90) as r_media:
                        if r_media.status_code == 200:
                            with open(cached_file, "wb") as f:
                                for chunk in r_media.iter_content(chunk_size=65536):
                                    if chunk:
                                        f.write(chunk)
                            return cached_file, None
                        else:
                            print(f"[Warning] media.githubusercontent.com returned HTTP {r_media.status_code}")
                else:
                    # Regular non-LFS file
                    with open(cached_file, "wb") as f:
                        f.write(first_chunk)
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    return cached_file, None
    except Exception as e:
        print(f"[Info] raw.githubusercontent.com failed ({e}), checking media...")

    # Method 2: Try media.githubusercontent.com directly
    try:
        with requests.get(media_url, headers=headers, stream=True, timeout=90) as r_media:
            if r_media.status_code == 200:
                first_chunk = next(r_media.iter_content(chunk_size=1024), b"")
                if not first_chunk.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    with open(cached_file, "wb") as f:
                        f.write(first_chunk)
                        for chunk in r_media.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    return cached_file, None
    except Exception as e:
        print(f"[Info] media.githubusercontent.com failed ({e}), checking API...")

    # Method 3: GitHub API contents endpoint
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}?ref={ref}"
    api_headers = dict(headers)
    api_headers["Accept"] = "application/vnd.github.v3.raw"
    try:
        with requests.get(api_url, headers=api_headers, stream=True, timeout=60) as r:
            if r.status_code == 200:
                first_chunk = next(r.iter_content(chunk_size=1024), b"")
                if not first_chunk.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    with open(cached_file, "wb") as f:
                        f.write(first_chunk)
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                    return cached_file, None
            return None, f"GitHub returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, f"Network error fetching file: {e}"


# ===================== Routes =====================

@app.route("/")
def index():
    """Main dashboard page."""
    port = request.host.split(":")[-1] if ":" in request.host else 5000
    return render_template("index.html", port=port)


@app.route("/api/user")
def api_user():
    """Check current authentication status."""
    token, user = get_git_credentials()
    if token:
        return jsonify({"authenticated": True, "user": user})
    return jsonify({"authenticated": False, "error": "No GitHub credentials found in Git Credential Manager."})


@app.route("/api/cache-info")
def api_cache_info():
    """Return disk cache file count and total size in MB."""
    count = 0
    total_bytes = 0
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("*"):
            if p.is_file():
                count += 1
                total_bytes += p.stat().st_size
    return jsonify({
        "count": count,
        "size_bytes": total_bytes,
        "size_mb": round(total_bytes / (1024 * 1024), 2)
    })


@app.route("/api/clear-cache", methods=["GET", "POST"])
def api_clear_cache():
    """Clear downloaded and converted book files from the local disk cache."""
    cleared_count = 0
    freed_bytes = 0
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("*"):
            if p.is_file():
                try:
                    size = p.stat().st_size
                    p.unlink(missing_ok=True)
                    freed_bytes += size
                    cleared_count += 1
                except Exception as e:
                    print(f"[Warning] Failed to delete {p}: {e}", file=sys.stderr)

    return jsonify({
        "success": True,
        "cleared_count": cleared_count,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2)
    })


@app.route("/api/repos")
def api_repos():
    """List user repositories (cached for 5 minutes)."""
    now = time.time()
    refresh = request.args.get("refresh") == "1"

    if not refresh and _REPOS_CACHE["data"] and (now - _REPOS_CACHE["timestamp"] < 300):
        return jsonify(_REPOS_CACHE["data"])

    token, _ = get_git_credentials()
    if not token:
        return jsonify({"error": "Not authenticated"}), 401

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-PdfViewer/1.0"
    }

    try:
        r = requests.get(
            "https://api.github.com/user/repos?type=all&sort=updated&per_page=100",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200:
            repos = [
                {
                    "full_name": item["full_name"],
                    "private": item["private"],
                    "default_branch": item.get("default_branch", "main")
                }
                for item in r.json()
            ]
            _REPOS_CACHE["data"] = repos
            _REPOS_CACHE["timestamp"] = now
            return jsonify(repos)
        return jsonify({"error": f"GitHub API error {r.status_code}"}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tree")
def api_tree():
    """Scan a repository for all PDF and EPUB files using the recursive git trees API."""
    repo = request.args.get("repo")
    ref = request.args.get("ref", "main")

    if not repo:
        return jsonify({"error": "Missing repo parameter"}), 400

    token, _ = get_git_credentials()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-PdfViewer/1.0"
    }

    url = f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            doc_files = [
                {
                    "path": item["path"],
                    "size": item.get("size", 0),
                    "type": "epub" if item["path"].lower().endswith(".epub") else "pdf"
                }
                for item in tree
                if item.get("type") == "blob" and item["path"].lower().endswith((".pdf", ".epub"))
            ]
            return jsonify({"files": doc_files})
        return jsonify({"error": f"Failed to fetch tree: HTTP {r.status_code}"}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/raw")
@app.route("/raw/<owner>/<repo>/<ref>/<path:filepath>")
def raw_content(owner=None, repo=None, ref=None, filepath=None):
    """Stream raw file bytes directly with appropriate MIME type, range support, and disk caching."""
    url = request.args.get("url")
    if url:
        parsed = parse_github_url(url)
        if not parsed:
            return "Invalid GitHub file URL", 400
        owner, repo, ref, filepath = parsed["owner"], parsed["repo"], parsed["ref"], parsed["path"]

    if not (owner and repo and ref and filepath):
        return "Missing repository or path parameter", 400

    refresh = request.args.get("refresh") == "1"
    cached_file, err = fetch_github_file(owner, repo, ref, filepath, use_cache=not refresh)
    if err:
        return f"Error loading file: {err}", 404

    filename = filepath.split("/")[-1]
    is_epub = filename.lower().endswith(".epub")
    mime_type = "application/epub+zip" if is_epub else "application/pdf"
    as_attachment = (request.args.get("download") == "1")

    return send_file(
        cached_file,
        mimetype=mime_type,
        as_attachment=as_attachment,
        download_name=filename,
        conditional=True
    )


@app.route("/view")
@app.route("/view/<owner>/<repo>/<ref>/<path:filepath>")
def view_document(owner=None, repo=None, ref=None, filepath=None):
    """
    Main viewing handler.
    - For PDF: streams directly with application/pdf inline to open the browser's native PDF reader.
    - For EPUB: opens the high-speed reflowable EPUB reader (templates/reader_view.html) with
      chapter navigation, font controls, theme toggles, and instant rendering.
    """
    url = request.args.get("url")
    if url:
        parsed = parse_github_url(url)
        if not parsed:
            return "Invalid GitHub file URL format. Expected github.com/owner/repo/blob/branch/path", 400
        owner, repo, ref, filepath = parsed["owner"], parsed["repo"], parsed["ref"], parsed["path"]

    if not (owner and repo and ref and filepath):
        return "Missing file path parameters", 400

    filename = filepath.split("/")[-1]
    is_epub = filename.lower().endswith(".epub")

    if is_epub:
        refresh = request.args.get("refresh") == "1"
        mode = request.args.get("mode") or request.args.get("format")

        cached_epub, err = fetch_github_file(owner, repo, ref, filepath, use_cache=not refresh)
        if err:
            return f"Error loading EPUB: {err}", 404

        # If mode == "pdf", convert EPUB to PDF and stream inline to native browser PDF viewer
        if mode == "pdf":
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            pdf_cache_name = f"{owner}_{repo}_{ref}_{filepath.replace('/', '_').replace('\\', '_')}.pdf"
            cached_pdf = CACHE_DIR / pdf_cache_name

            if refresh or not cached_pdf.exists() or cached_pdf.stat().st_size == 0:
                try:
                    convert_epub_to_pdf(str(cached_epub), str(cached_pdf))
                except Exception as conv_err:
                    return f"Failed to convert EPUB to PDF: {conv_err}", 500

            pdf_title = f"{Path(filename).stem}.pdf"
            return send_file(
                cached_pdf,
                mimetype="application/pdf",
                as_attachment=False,
                download_name=pdf_title,
                conditional=True
            )

        # Default / Web mode: Render the reflowable e-book web reader
        try:
            meta, _, _, _ = get_epub_metadata_and_spine(str(cached_epub))
            book_title = meta.get("title", filename)
        except Exception:
            book_title = filename

        book_url = f"https://github.com/{owner}/{repo}/blob/{ref}/{filepath}"
        raw_url = f"/raw/{owner}/{repo}/{ref}/{filepath}"
        return render_template(
            "reader_view.html",
            book_title=book_title,
            book_url=book_url,
            raw_file_url=raw_url
        )

    # For PDF files: redirect to raw endpoint which streams application/pdf inline
    raw_path = f"/raw/{owner}/{repo}/{ref}/{filepath}"
    return redirect(raw_path)


# ===================== EPUB Reader API Endpoints =====================

@app.route("/api/epub/info")
def api_epub_info():
    """Return EPUB metadata and chapters list."""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing url"}), 400

    parsed = parse_github_url(url)
    if not parsed:
        return jsonify({"error": "Invalid GitHub URL"}), 400

    cached_epub, err = fetch_github_file(parsed["owner"], parsed["repo"], parsed["ref"], parsed["path"])
    if err:
        return jsonify({"error": err}), 404

    try:
        metadata, chapters, _, _ = get_epub_metadata_and_spine(str(cached_epub))
        return jsonify({
            "title": metadata["title"],
            "author": metadata["author"],
            "total_chapters": len(chapters),
            "chapters": [{"index": ch["index"], "title": ch["title"]} for ch in chapters]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/epub/chapter")
def api_epub_chapter():
    """Return a single chapter's HTML content with asset URLs rewritten."""
    url = request.args.get("url")
    index = request.args.get("index", type=int, default=0)

    if not url:
        return jsonify({"error": "Missing url"}), 400

    parsed = parse_github_url(url)
    if not parsed:
        return jsonify({"error": "Invalid GitHub URL"}), 400

    cached_epub, err = fetch_github_file(parsed["owner"], parsed["repo"], parsed["ref"], parsed["path"])
    if err:
        return jsonify({"error": err}), 404

    try:
        asset_prefix = f"/epub-asset/{parsed['owner']}/{parsed['repo']}/{parsed['ref']}/{parsed['path']}"
        data = extract_chapter_html(str(cached_epub), index, asset_prefix)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/epub-asset/<owner>/<repo>/<ref>/<path:filepath>")
def epub_asset(owner, repo, ref, filepath):
    """Stream an internal asset (image, font, css) from the EPUB archive."""
    asset_path = request.args.get("asset")
    if not asset_path:
        return "Missing asset path", 400

    cached_epub, err = fetch_github_file(owner, repo, ref, filepath)
    if err:
        return "EPUB not found", 404

    try:
        data, mime = read_epub_asset(str(cached_epub), asset_path)
        resp = Response(data, mimetype=mime)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    except Exception as e:
        return f"Asset error: {e}", 404


# ===================== CLI Runner =====================

def main():
    parser = argparse.ArgumentParser(description="Private GitHub PDF & EPUB Viewer")
    parser.add_argument("url", nargs="?", help="GitHub file URL to view immediately in browser")
    parser.add_argument("--port", type=int, default=5000, help="Port to run server on (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    parser.add_argument("--clear-cache", action="store_true", help="Clear downloaded file cache")

    args = parser.parse_args()

    if args.clear_cache:
        count = 0
        for f in CACHE_DIR.glob("*"):
            if f.is_file():
                f.unlink()
                count += 1
        print(f"Cleared {count} cached files from {CACHE_DIR}")
        return

    token, user = get_git_credentials()
    if token:
        print(f"[*] Git Credential Manager: Authenticated as @{user}")
    else:
        print("[!] Warning: Could not retrieve GitHub credentials from Git Credential Manager.")

    base_url = f"http://{args.host}:{args.port}"
    target_url = base_url
    if args.url:
        target_url = f"{base_url}/view?url={urllib.parse.quote(args.url)}"

    # Check if server is already running on this port
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    is_running = False
    try:
        sock.connect((args.host, args.port))
        is_running = True
        sock.close()
    except OSError:
        pass

    if is_running:
        print(f"[*] PdfViewer is already running on {base_url}. Opening browser...")
        if not args.no_browser:
            webbrowser.open(target_url)
        return

    if not args.no_browser:
        import threading
        def open_browser():
            time.sleep(0.8)
            print(f"[*] Opening browser: {target_url}")
            webbrowser.open(target_url)

        threading.Thread(target=open_browser, daemon=True).start()

    print(f"[*] Server running on {base_url}")
    print("    Press Ctrl+C to stop.")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
