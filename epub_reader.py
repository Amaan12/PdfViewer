"""
Clean, blazing-fast EPUB Reader Engine
Parses EPUB structures, extracts chapters, rewrites asset URLs,
and delivers instantaneous, reflowable, full-book reading without heavy client-side libraries.
"""

import os
import re
import sys
import posixpath
import zipfile
import mimetypes
import xml.etree.ElementTree as ET
from pathlib import Path


def _resolve_zip_path(base_dir: str, rel_path: str) -> str:
    clean_rel = rel_path.split("?")[0].split("#")[0].strip()
    if not clean_rel:
        return ""
    joined = posixpath.join(base_dir, clean_rel) if base_dir else clean_rel
    return posixpath.normpath(joined).lstrip("/")


def get_epub_metadata_and_spine(epub_path: str):
    """
    Extracts book metadata, ordered chapters from spine, and Table of Contents (TOC).
    Returns (metadata, chapters_list, opf_dir, asset_manifest).
    """
    with zipfile.ZipFile(epub_path, "r") as z:
        # 1. Locate rootfile from META-INF/container.xml
        container_xml = z.read("META-INF/container.xml")
        root = ET.fromstring(container_xml)
        rootfile = root.find(".//{*}rootfile")
        if rootfile is None:
            raise ValueError("Invalid EPUB: rootfile not found in container.xml")
        opf_path = rootfile.attrib["full-path"]
        opf_dir = posixpath.dirname(opf_path)

        # 2. Parse OPF
        opf_xml = z.read(opf_path)
        opf = ET.fromstring(opf_xml)

        manifest = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            manifest[item.attrib["id"]] = {
                "href": item.attrib["href"],
                "type": item.attrib.get("media-type", ""),
                "properties": item.attrib.get("properties", "")
            }

        spine_ids = [
            itemref.attrib["idref"]
            for itemref in opf.findall(".//{*}spine/{*}itemref")
            if "idref" in itemref.attrib
        ]

        # Extract Metadata
        title_el = opf.find(".//{*}metadata/{*}title")
        book_title = title_el.text.strip() if title_el is not None and title_el.text else Path(epub_path).stem

        author_el = opf.find(".//{*}metadata/{*}creator")
        book_author = author_el.text.strip() if author_el is not None and author_el.text else ""

        # Try to parse Table of Contents (NCX or EPUB3 nav)
        toc_entries = []

        # Check for EPUB 3 nav
        nav_href = None
        for item in manifest.values():
            if "nav" in item.get("properties", "").split():
                nav_href = item["href"]
                break

        if nav_href:
            try:
                nav_zip = _resolve_zip_path(opf_dir, nav_href)
                nav_bytes = z.read(nav_zip)
                nav_tree = ET.fromstring(nav_bytes)
                for a_tag in nav_tree.findall(".//{*}nav[@{*}type='toc']//{*}a"):
                    text = "".join(a_tag.itertext()).strip()
                    href = a_tag.attrib.get("href", "")
                    if text and href:
                        toc_entries.append({"title": text, "href": href})
            except Exception:
                pass

        # Check for EPUB 2 NCX
        if not toc_entries:
            ncx_href = None
            for item in manifest.values():
                if item.get("type") == "application/x-dtbncx+xml":
                    ncx_href = item["href"]
                    break

            if ncx_href:
                try:
                    ncx_zip = _resolve_zip_path(opf_dir, ncx_href)
                    ncx_bytes = z.read(ncx_zip)
                    ncx_tree = ET.fromstring(ncx_bytes)
                    for np in ncx_tree.findall(".//{*}navPoint"):
                        text_el = np.find(".//{*}navLabel/{*}text")
                        content_el = np.find(".//{*}content")
                        if text_el is not None and text_el.text and content_el is not None:
                            toc_entries.append({
                                "title": text_el.text.strip(),
                                "href": content_el.attrib.get("src", "")
                            })
                except Exception:
                    pass

        # Build ordered spine chapters
        chapters = []
        for idx, sid in enumerate(spine_ids):
            if sid in manifest:
                href = manifest[sid]["href"]
                zip_path = _resolve_zip_path(opf_dir, href)

                # Try to find a human-friendly title
                ch_title = f"Section {idx + 1}"
                for t in toc_entries:
                    if t["href"].split("#")[0] == href:
                        ch_title = t["title"]
                        break

                chapters.append({
                    "index": idx,
                    "id": sid,
                    "href": href,
                    "zip_path": zip_path,
                    "title": ch_title
                })

        # If TOC was empty, construct it from spine
        if not toc_entries:
            toc_entries = [{"title": ch["title"], "href": ch["href"]} for ch in chapters]

        metadata = {
            "title": book_title,
            "author": book_author,
            "total_chapters": len(chapters),
            "toc": toc_entries
        }

        return metadata, chapters, opf_dir, manifest


def extract_chapter_html(epub_path: str, chapter_index: int, asset_url_prefix: str) -> dict:
    """
    Extracts a single chapter's HTML content from the EPUB archive.
    Rewrites relative image and media links to point to asset_url_prefix.
    Returns { 'title': ..., 'content': ..., 'index': ..., 'total': ... }.
    """
    metadata, chapters, opf_dir, manifest = get_epub_metadata_and_spine(epub_path)

    if chapter_index < 0 or chapter_index >= len(chapters):
        raise IndexError(f"Chapter index {chapter_index} out of range (0-{len(chapters)-1})")

    target_chapter = chapters[chapter_index]
    ch_zip_path = target_chapter["zip_path"]
    ch_dir = posixpath.dirname(ch_zip_path)

    with zipfile.ZipFile(epub_path, "r") as z:
        raw_bytes = z.read(ch_zip_path)
        raw_text = raw_bytes.decode("utf-8", errors="ignore")

        # Extract content inside <body>...</body>
        body_match = re.search(r"<body[^>]*>(.*?)</body>", raw_text, re.DOTALL | re.IGNORECASE)
        body = body_match.group(1) if body_match else raw_text

        # Rewrite image and asset references to point to our streaming endpoint
        def rewrite_src(match):
            attr = match.group(1)
            src_val = match.group(2).strip()
            # If already external or data URI, keep as is
            if src_val.startswith(("http://", "https://", "data:")):
                return match.group(0)

            clean_src = src_val.split("?")[0].split("#")[0]
            resolved = _resolve_zip_path(ch_dir, clean_src)
            return f'{attr}="{asset_url_prefix}?asset={resolved}"'

        body = re.sub(
            r'(src|xlink:href)=["\']([^"\']+)["\']',
            rewrite_src,
            body,
            flags=re.IGNORECASE
        )

        # Clean up any fixed heights or overflow properties that break scrolling
        body = re.sub(r'height\s*:\s*100vh', 'height: auto', body, flags=re.IGNORECASE)
        body = re.sub(r'overflow\s*:\s*hidden', 'overflow: visible', body, flags=re.IGNORECASE)

        # Detect chapter title from first <h1>/<h2> if section title is generic
        if target_chapter["title"].startswith("Section "):
            h_match = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", body, re.DOTALL | re.IGNORECASE)
            if h_match:
                clean_h = re.sub(r"<[^>]+>", "", h_match.group(1)).strip()
                if clean_h and len(clean_h) < 100:
                    target_chapter["title"] = clean_h

        return {
            "title": target_chapter["title"],
            "index": chapter_index,
            "total": len(chapters),
            "content": body,
            "has_prev": chapter_index > 0,
            "has_next": chapter_index < len(chapters) - 1,
            "metadata": metadata,
            "chapters_list": [{"index": ch["index"], "title": ch["title"]} for ch in chapters]
        }


def read_epub_asset(epub_path: str, asset_zip_path: str):
    """Read a raw asset (image, font, css) from the EPUB archive with MIME type."""
    with zipfile.ZipFile(epub_path, "r") as z:
        asset_zip_path = asset_zip_path.lstrip("/")
        # Try direct
        if asset_zip_path in z.namelist():
            raw = z.read(asset_zip_path)
            mime, _ = mimetypes.guess_type(asset_zip_path)
            return raw, mime or "application/octet-stream"

        # Try case-insensitive lookup
        lower_map = {name.lower(): name for name in z.namelist()}
        if asset_zip_path.lower() in lower_map:
            real_name = lower_map[asset_zip_path.lower()]
            raw = z.read(real_name)
            mime, _ = mimetypes.guess_type(real_name)
            return raw, mime or "application/octet-stream"

        raise FileNotFoundError(f"Asset '{asset_zip_path}' not found in EPUB")
