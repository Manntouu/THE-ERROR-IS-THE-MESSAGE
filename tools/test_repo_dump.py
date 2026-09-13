import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request

spec = importlib.util.spec_from_file_location("repo_dump", Path(__file__).with_name("repo_dump.py"))
dump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dump)


class Response(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


class FixtureClient:
    def __init__(self, blobs=None):
        self.blobs = blobs or {}
        self.calls = []
        self.fail = False

    def open(self, url, binary=False):
        self.calls.append(url)
        value = self.blobs[url]
        if isinstance(value, Exception):
            raise value
        return Response(value, {"Content-Length": str(len(value)), "Content-Type": "image/png"})

    def one(self, path):
        if self.fail:
            raise dump.ArchiveError("fixture metadata failure")
        if "/issues/" in path:
            return {"id": 1, "number": 1, "body": "", "title": "Issue"}
        return {"full_name": "owner/repo"}

    def pages(self, path):
        if "/issues?state=all" in path:
            return [{"id": 1, "number": 1, "title": "<script>bad()</script>",
                     "body": "https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000001"},
                    {"id": 2, "number": 2, "body": "", "pull_request": {}}]
        if path.endswith("/issues/comments"):
            return [{"id": 11, "body": "full conversation", "user": None,
                     "issue_url": "https://api.github.com/repos/owner/repo/issues/2"}]
        if path.endswith("/pulls?state=all"):
            return [{"id": 2, "number": 2, "title": "PR", "body": "PR body"}]
        if path.endswith("/pulls/comments"):
            return [{"id": 12, "body": "inline comment", "path": "example.py",
                     "diff_hunk": "@@ -1 +1 @@", "pull_request_url": "https://api.github.com/repos/owner/repo/pulls/2"}]
        if path.endswith("/pulls/2/reviews"):
            return [{"id": 13, "body": "review summary", "state": "APPROVED"}]
        if path.endswith("/releases"):
            return [{"id": 3, "tag_name": "v1", "body": "release notes"}]
        if path.endswith("/releases/3/assets"):
            return [{"id": 4, "url": "https://api.github.com/repos/owner/repo/releases/assets/4",
                     "size": 3, "digest": "sha256:" + hashlib.sha256(b"zip").hexdigest()}]
        if path.endswith("/tags"):
            return [{"name": "v1", "commit": {"sha": "abc"}}]
        return []


class ArchiveTests(unittest.TestCase):
    def test_pagination_follows_next_not_first_page_length(self):
        client = dump.GitHub()
        calls = []
        def opening(url, binary=False):
            calls.append(url)
            if "page=2" in url:
                return Response(b'[{"id":2}]')
            return Response(b'[{"id":1}]', {"Link": '<https://api.github.com/test?page=2>; rel="next"'})
        client.open = opening
        self.assertEqual(client.pages("/test"), [{"id": 1}, {"id": 2}])
        self.assertEqual(len(calls), 2)

    def test_pagination_rejects_external_host_and_cycles(self):
        client = dump.GitHub()
        client.open = lambda *a, **kw: Response(b"[]", {"Link": '<https://example.com/steal>; rel="next"'})
        with self.assertRaises(dump.ArchiveError):
            client.pages("/test")
        client.open = lambda *a, **kw: Response(b"[]", {"Link": '<https://api.github.com/test?per_page=100>; rel="next"'})
        with self.assertRaises(dump.ArchiveError):
            client.pages("/test")

    def test_uploaded_assets_from_markdown_html_and_bare_urls(self):
        body = ('![x](https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000001)\n'
                '<img src="https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000002">\n'
                'https://github.com/owner/repo/files/123/file.pdf\n'
                'https://user-images.githubusercontent.com/1/a.png\n'
                'https://example.com/tracker.png https://github.com/org/repo/issues/1')
        urls = dump.attachment_urls(body)
        self.assertEqual(len(urls), 4)
        self.assertFalse(any("example.com" in u or "issues" in u for u in urls))

    def test_redirect_never_forwards_api_authorization(self):
        request = Request("https://api.github.com/release", headers={"Authorization": "Bearer TEST-ONLY"})
        redirect = dump.SafeRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/file")
        self.assertIsNone(redirect.get_header("Authorization"))
        with self.assertRaises(dump.ArchiveError):
            dump.SafeRedirect().redirect_request(request, None, 302, "Found", {}, "https://example.com/file")

    def test_rejects_insecure_and_credential_urls(self):
        for url in ["http://github.com/file", "https://api.github.com:444/file",
                    "https://token@github.com/file", "https://127.0.0.1/file"]:
            with self.subTest(url=url), self.assertRaises(dump.ArchiveError):
                dump.safe_url(url)

    def test_streamed_parts_restore_original_bytes_and_deduplicate_rerun(self):
        url = "https://github.com/user-attachments/assets/test"
        original = b"abcdefghij"
        client = FixtureClient({url: original})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = dump.Assets(client, root, part_bytes=4)
            assets.add(url, "first")
            assets.add(url, "second")
            entry = assets.final()[url]
            self.assertEqual(len(entry["parts"]), 3)
            self.assertEqual(b"".join((root / p["path"]).read_bytes() for p in entry["parts"]), original)
            self.assertEqual(entry["references"], ["first", "second"])
            dump.write_json(root / "manifest.json", {"assets": assets.final()})
            second = dump.Assets(client, root, part_bytes=4)
            second.add(url, "again")
            self.assertTrue(second.entries[url]["reused"])
            self.assertEqual(len(client.calls), 1)
            # A corrupted existing file must be downloaded again, not trusted.
            (root / entry["parts"][0]["path"]).write_bytes(b"oops")
            third = dump.Assets(client, root, part_bytes=4)
            third.add(url, "repair")
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(third.entries[url]["sha256"], hashlib.sha256(original).hexdigest())

    def test_size_digest_and_download_budget_errors_are_explicit(self):
        url = "https://github.com/user-attachments/assets/test"
        for expected, digest, limit in [(100, None, 1000), (3, "sha256:wrong", 1000), (None, None, 2)]:
            with self.subTest(expected=expected, digest=digest, limit=limit), tempfile.TemporaryDirectory() as folder:
                assets = dump.Assets(FixtureClient({url: b"abc"}), Path(folder), max_bytes=limit)
                assets.add(url, "fixture", expected, digest)
                self.assertEqual(assets.entries[url]["status"], "failed")
                self.assertFalse(list(Path(folder).glob(".download-*")))

    def test_complete_export_preserves_all_three_areas_and_escapes_remote_text(self):
        client = FixtureClient({
            "https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000001": b"image",
            "https://api.github.com/repos/owner/repo/releases/assets/4": b"zip"})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = dump.export("owner/repo", root, client)
            self.assertTrue(report["complete"])
            self.assertEqual(report["counts"]["assets"], 2)
            self.assertEqual(report["counts"]["reviews"], 1)
            self.assertEqual(report["counts"]["review_comments"], 1)
            self.assertEqual(report["counts"]["releases"], 1)
            self.assertEqual(report["counts"]["tags"], 1)
            issue = (root / "issues/1.html").read_text()
            self.assertIn("&lt;script&gt;", issue)
            self.assertNotIn("<script>", issue)
            pr = (root / "pulls/2.html").read_text()
            for text in ["full conversation", "inline comment", "review summary"]:
                self.assertIn(text, pr)

    def test_failed_asset_keeps_metadata_and_marks_archive_incomplete(self):
        client = FixtureClient({
            "https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000001": dump.ArchiveError("HTTP 404"),
            "https://api.github.com/repos/owner/repo/releases/assets/4": b"zip"})
        with tempfile.TemporaryDirectory() as folder:
            report = dump.export("owner/repo", folder, client)
            self.assertFalse(report["complete"])
            self.assertFalse(report["selected_scope_complete"])
            self.assertTrue((Path(folder) / "raw/snapshot.json").exists())
            self.assertIn("INCOMPLETE", (Path(folder) / "index.html").read_text())

    def test_metadata_failure_is_not_reported_as_empty_success(self):
        client = FixtureClient()
        client.fail = True
        with tempfile.TemporaryDirectory() as folder:
            report = dump.export("owner/repo", folder, client)
            self.assertFalse(report["complete"])
            self.assertIn("metadata_error", report)

    def test_one_issue_mode_cannot_claim_complete_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            report = dump.export("owner/repo", folder, FixtureClient(), issue_number=1)
            self.assertFalse(report["complete"])
            self.assertTrue(report["selected_scope_complete"])
            self.assertEqual(report["scope"], "single issue 1")

    def test_cached_manifest_cannot_escape_archive_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "archive"
            root.mkdir()
            external = Path(folder) / "private.txt"
            external.write_bytes(b"private")
            entry = {"status": "saved", "sha256": hashlib.sha256(b"private").hexdigest(),
                     "parts": [{"path": "../private.txt", "size": 7,
                                "sha256": hashlib.sha256(b"private").hexdigest()}]}
            self.assertFalse(dump.Assets(FixtureClient(), root).cached(entry))

    def test_code_quoted_asset_and_placeholder_are_distinguished(self):
        valid = "https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000001"
        self.assertEqual(dump.attachment_urls(chr(96) + valid + chr(96)), [valid])
        self.assertEqual(dump.attachment_urls(chr(96) + "https://github.com/user-attachments/assets/xxxx" + chr(96)), [])

    def test_readme_uploaded_media_is_included(self):
        import base64
        readme_url = "https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000003"
        client = FixtureClient({
            "https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000001": b"image",
            "https://api.github.com/repos/owner/repo/releases/assets/4": b"zip",
            readme_url: b"readme-media"})
        original = client.one
        client.one = lambda path: ({"encoding": "base64", "content": base64.b64encode(readme_url.encode()).decode()}
                                   if path.endswith("/readme") else original(path))
        with tempfile.TemporaryDirectory() as folder:
            report = dump.export("owner/repo", folder, client)
            self.assertTrue(report["complete"])
            self.assertEqual(report["counts"]["assets"], 3)
            self.assertTrue((Path(folder) / "readme.html").exists())


if __name__ == "__main__":
    unittest.main()
