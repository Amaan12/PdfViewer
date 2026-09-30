"""
Unit tests for Private GitHub PDF & EPUB Viewer
"""

import unittest
import io
import zipfile
import os
from pathlib import Path
from viewer import app, parse_github_url, get_git_credentials, CACHE_DIR


class TestPdfViewer(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_git_credentials(self):
        token, user = get_git_credentials()
        self.assertIsNotNone(token, "GitHub token should be retrieved from Git Credential Manager")
        self.assertTrue(len(token) > 10, "Token should be non-empty")
        self.assertEqual(user, "Amaan12")

    def test_url_parser(self):
        # 1. Standard GitHub blob URL
        res = parse_github_url("https://github.com/Amaan12/my-repo/blob/main/docs/book.pdf")
        self.assertEqual(res, {
            "owner": "Amaan12",
            "repo": "my-repo",
            "ref": "main",
            "path": "docs/book.pdf"
        })

        # 2. GitHub raw URL
        res = parse_github_url("https://raw.githubusercontent.com/Amaan12/my-repo/v1.0/nested/path/sample.epub")
        self.assertEqual(res, {
            "owner": "Amaan12",
            "repo": "my-repo",
            "ref": "v1.0",
            "path": "nested/path/sample.epub"
        })

        # 3. Short format without protocol
        res = parse_github_url("github.com/Amaan12/books/blob/master/guide.pdf")
        self.assertEqual(res, {
            "owner": "Amaan12",
            "repo": "books",
            "ref": "master",
            "path": "guide.pdf"
        })

        # 4. Invalid URL
        self.assertIsNone(parse_github_url("https://google.com/search?q=pdf"))

    def test_routes_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GitHub PDF & EPUB Viewer", response.data)

    def test_api_user(self):
        response = self.client.get("/api/user")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("authenticated"))
        self.assertEqual(data.get("user"), "Amaan12")

    def test_api_repos(self):
        response = self.client.get("/api/repos")
        self.assertEqual(response.status_code, 200)
        repos = response.get_json()
        self.assertIsInstance(repos, list)
        self.assertTrue(len(repos) > 0)
        names = [r["full_name"] for r in repos]
        self.assertIn("Amaan12/Amaan12", names)

    def test_api_tree(self):
        response = self.client.get("/api/tree?repo=Amaan12/Amaan12&ref=main")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("files", data)

    def test_pdf_redirect_to_raw(self):
        # When a PDF is requested, /view redirects to /raw with clean path
        url = "https://github.com/Amaan12/sample/blob/main/test.pdf"
        response = self.client.get(f"/view?url={url}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/raw/Amaan12/sample/main/test.pdf", response.headers["Location"])

    def test_epub_native_reader_and_api(self):
        # Create a test epub in cache
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
            z.writestr("content.opf", """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Great Novel</dc:title></metadata>
  <manifest>
    <item id="c1" href="ch1.html" media-type="application/xhtml+xml"/>
    <item id="c2" href="ch2.html" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>""")
            z.writestr("ch1.html", "<html><body><h1>Chapter 1: Arrival</h1><p>Welcome to page one.</p></body></html>")
            z.writestr("ch2.html", "<html><body><h1>Chapter 2: Departure</h1><p>Continuing the journey.</p></body></html>")

        epub_cache_file = CACHE_DIR / "Amaan12_bookrepo_main_novel.epub"
        with open(epub_cache_file, "wb") as f:
            f.write(buf.getvalue())

        url = "https://github.com/Amaan12/bookrepo/blob/main/novel.epub"

        # 1. Test /view endpoint -> renders reader_view.html
        resp = self.client.get(f"/view?url={url}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Great Novel - EPUB Reader", resp.data)
        self.assertIn(b"Table of Contents", resp.data)

        # 2. Test /api/epub/info endpoint
        resp_info = self.client.get(f"/api/epub/info?url={url}")
        self.assertEqual(resp_info.status_code, 200)
        info = resp_info.get_json()
        self.assertEqual(info["title"], "Great Novel")
        self.assertEqual(info["total_chapters"], 2)

        # 3. Test /api/epub/chapter endpoint (chapter 0)
        resp_ch = self.client.get(f"/api/epub/chapter?url={url}&index=0")
        self.assertEqual(resp_ch.status_code, 200)
        ch_data = resp_ch.get_json()
        self.assertIn("Arrival", ch_data["title"])
        self.assertIn("Welcome to page one.", ch_data["content"])
        self.assertTrue(ch_data["has_next"])
        self.assertFalse(ch_data["has_prev"])

        # 4. Test chapter 1
        resp_ch1 = self.client.get(f"/api/epub/chapter?url={url}&index=1")
        self.assertEqual(resp_ch1.status_code, 200)
        ch1_data = resp_ch1.get_json()
        self.assertIn("Departure", ch1_data["title"])
        self.assertIn("Continuing the journey.", ch1_data["content"])
        self.assertFalse(ch1_data["has_next"])
        self.assertTrue(ch1_data["has_prev"])

        # 5. Test mode=pdf endpoint -> converts EPUB to PDF and streams application/pdf
        resp_pdf = self.client.get(f"/view?url={url}&mode=pdf")
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf.headers.get("Content-Type"), "application/pdf")
        self.assertGreater(len(resp_pdf.data), 1000)


if __name__ == "__main__":
    unittest.main()
