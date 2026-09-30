"""
High-performance EPUB to PDF & Web Reader Converter
Extracts EPUB chapters, inlines images, and uses Microsoft Edge/Chromium headless
to generate publication-quality PDFs in under 1 second.
"""

import os
import re
import sys
import time
import base64
import posixpath
import tempfile
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def find_browser_binary():
    """Locate Microsoft Edge or Google Chrome executable on Windows."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # Fallback to PATH search
    for name in ["msedge.exe", "msedge", "chrome.exe", "chrome"]:
        import shutil
        found = shutil.which(name)
        if found:
            return found

    return None


def _resolve_zip_path(base_dir: str, rel_path: str) -> str:
    """Resolve a relative asset path inside the zip archive cleanly."""
    clean_rel = rel_path.split("?")[0].split("#")[0].strip()
    if not clean_rel:
        return ""
    joined = posixpath.join(base_dir, clean_rel) if base_dir else clean_rel
    return posixpath.normpath(joined).lstrip("/")


def epub_to_master_html(epub_path: str) -> tuple[str, str]:
    """
    Parse an EPUB file, extract all spine chapters, inline all images as data URIs,
    and return (book_title, complete_self_contained_html).
    """
    with zipfile.ZipFile(epub_path, "r") as z:
        # 1. Locate rootfile from META-INF/container.xml
        try:
            container_xml = z.read("META-INF/container.xml")
            root = ET.fromstring(container_xml)
            rootfile = root.find(".//{*}rootfile")
            opf_path = rootfile.attrib["full-path"]
        except Exception as e:
            raise ValueError(f"Invalid EPUB format (container.xml missing or invalid): {e}")

        opf_dir = posixpath.dirname(opf_path)

        # 2. Parse OPF
        opf_xml = z.read(opf_path)
        opf = ET.fromstring(opf_xml)

        manifest = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            manifest[item.attrib["id"]] = {
                "href": item.attrib["href"],
                "type": item.attrib.get("media-type", "")
            }

        spine_hrefs = []
        for itemref in opf.findall(".//{*}spine/{*}itemref"):
            idref = itemref.attrib.get("idref")
            if idref and idref in manifest:
                spine_hrefs.append(manifest[idref]["href"])

        # Extract title
        title_el = opf.find(".//{*}metadata/{*}title")
        book_title = title_el.text if title_el is not None and title_el.text else Path(epub_path).stem

        # Extract author
        author_el = opf.find(".//{*}metadata/{*}creator")
        author = author_el.text if author_el is not None and author_el.text else ""

        # Pre-cache all image assets into base64 data URIs
        image_map = {}
        for item_info in manifest.values():
            mtype = item_info["type"].lower()
            href = item_info["href"]
            if mtype.startswith("image/"):
                zip_path = _resolve_zip_path(opf_dir, href)
                try:
                    raw_bytes = z.read(zip_path)
                    b64 = base64.b64encode(raw_bytes).decode("ascii")
                    data_uri = f"data:{mtype};base64,{b64}"
                    image_map[zip_path] = data_uri
                    image_map[href] = data_uri
                    image_map[posixpath.basename(href)] = data_uri
                except Exception:
                    pass

        # 3. Assemble all spine chapters in order
        assembled_chapters = []
        for ch_idx, href in enumerate(spine_hrefs):
            ch_zip_path = _resolve_zip_path(opf_dir, href)
            ch_dir = posixpath.dirname(ch_zip_path)

            try:
                ch_bytes = z.read(ch_zip_path)
                ch_text = ch_bytes.decode("utf-8", errors="ignore")

                # Extract <body>...</body> content
                body_match = re.search(r"<body[^>]*>(.*?)</body>", ch_text, re.DOTALL | re.IGNORECASE)
                content = body_match.group(1) if body_match else ch_text

                # Replace image tags (src, xlink:href, etc.) with inlined data URIs
                def replace_img_src(match):
                    attr = match.group(1)
                    src_val = match.group(2).strip()
                    resolved = _resolve_zip_path(ch_dir, src_val)
                    basename = posixpath.basename(src_val)

                    if resolved in image_map:
                        return f'{attr}="{image_map[resolved]}"'
                    if src_val in image_map:
                        return f'{attr}="{image_map[src_val]}"'
                    if basename in image_map:
                        return f'{attr}="{image_map[basename]}"'
                    return match.group(0)

                # Match src="..." or xlink:href="..."
                content = re.sub(
                    r'(src|xlink:href)=["\']([^"\']+)["\']',
                    replace_img_src,
                    content,
                    flags=re.IGNORECASE
                )

                # Strip harmful fixed heights or overflow that breaks pagination
                content = re.sub(r'height\s*:\s*100vh', 'height: auto', content, flags=re.IGNORECASE)
                content = re.sub(r'overflow\s*:\s*hidden', 'overflow: visible', content, flags=re.IGNORECASE)

                page_break = "page-break-before: always;" if ch_idx > 0 else ""
                assembled_chapters.append(
                    f'<article class="book-chapter" style="{page_break}">\n{content}\n</article>'
                )
            except Exception as e:
                print(f"[Warning] Could not extract chapter {href}: {e}", file=sys.stderr)

        # 4. Master HTML template
        master_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{book_title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    @page {{
      size: A4;
      margin: 2cm 1.8cm;
    }}
    @media print {{
      body {{
        background: #ffffff !important;
        color: #000000 !important;
      }}
      .no-print {{
        display: none !important;
      }}
      .book-chapter {{
        page-break-after: auto;
      }}
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      font-family: "Georgia", "Cambria", "Times New Roman", Times, serif;
      font-size: 11pt;
      line-height: 1.65;
      color: #1f2937;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }}
    .book-chapter {{
      margin-bottom: 2.5rem;
    }}
    h1, h2, h3, h4, h5, h6 {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-weight: 700;
      color: #111827;
      page-break-after: avoid;
      break-after: avoid;
      margin-top: 1.5em;
      margin-bottom: 0.6em;
      line-height: 1.25;
    }}
    h1 {{
      font-size: 20pt;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 0.3em;
      margin-top: 1em;
    }}
    h2 {{ font-size: 16pt; }}
    h3 {{ font-size: 13pt; }}
    p {{
      margin-top: 0;
      margin-bottom: 0.9em;
      text-align: justify;
      hyphens: auto;
    }}
    img, svg {{
      max-width: 100% !important;
      height: auto !important;
      display: block;
      margin: 1.5em auto;
      page-break-inside: avoid;
      break-inside: avoid;
    }}
    pre, code {{
      font-family: "Consolas", "Courier New", monospace;
      font-size: 9.5pt;
      background: #f3f4f6;
      border-radius: 4px;
    }}
    pre {{
      padding: 12px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-wrap: break-word;
      page-break-inside: avoid;
      border: 1px solid #e5e7eb;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      page-break-inside: avoid;
      margin: 1.5em 0;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 6px 10px;
      font-size: 10pt;
      text-align: left;
    }}
    th {{
      background: #f9fafb;
    }}
    blockquote {{
      margin: 1.2em 1.5em;
      padding-left: 1em;
      border-left: 3px solid #3b82f6;
      color: #4b5563;
      font-style: italic;
    }}
  </style>
</head>
<body>
{"".join(assembled_chapters)}
</body>
</html>"""

        return book_title, master_html


def convert_epub_to_pdf(epub_path: str, output_pdf_path: str) -> bool:
    """
    Converts an EPUB into a PDF file using Microsoft Edge / Chromium headless.
    Outputs directly to output_pdf_path. Returns True on success.
    """
    browser_bin = find_browser_binary()
    if not browser_bin:
        raise RuntimeError("No Chromium/Edge browser found for PDF generation.")

    t0 = time.time()
    _, master_html = epub_to_master_html(epub_path)

    # Use a temporary HTML file with file:/// URL
    tmp_fd, tmp_html_path = tempfile.mkstemp(suffix=".html", prefix="epub_conv_")
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
        f.write(master_html)

    abs_output = os.path.abspath(output_pdf_path)
    file_url = "file:///" + os.path.abspath(tmp_html_path).replace("\\", "/")

    cmd = [
        browser_bin,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={abs_output}",
        file_url
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=45)
        if res.returncode != 0:
            err = res.stderr.decode(errors="ignore")
            raise RuntimeError(f"Browser PDF printing failed (code {res.returncode}): {err}")
    finally:
        if os.path.exists(tmp_html_path):
            try:
                os.remove(tmp_html_path)
            except Exception:
                pass

    if not os.path.exists(abs_output) or os.path.getsize(abs_output) == 0:
        raise RuntimeError("PDF generation failed: output file was not created.")

    t1 = time.time()
    print(f"[*] EPUB converted to PDF in {round(t1 - t0, 2)}s -> {abs_output} ({os.path.getsize(abs_output)} bytes)")
    return True
