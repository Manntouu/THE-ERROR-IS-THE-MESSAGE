#!/usr/bin/env python3
"""Archive the three GitHub bounty areas without third-party dependencies."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

API = "https://api.github.com"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
URL_PATTERN = re.compile(r"https?://[^\s<>\"'\x00-\x20\x60]+")
MIB = 1024 * 1024


class ArchiveError(Exception):
    pass


def safe_url(url):
    p = urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise ArchiveError("Only ordinary HTTPS GitHub URLs are permitted")
    host = (p.hostname or "").lower()
    if host not in {"api.github.com", "github.com", "codeload.github.com", "user-images.githubusercontent.com",
                    "objects.githubusercontent.com", "release-assets.githubusercontent.com",
                    "github-production-user-asset-6210df.s3.amazonaws.com",
                    "github-production-repository-file-5c1aeb.s3.amazonaws.com"} and not host.endswith(".githubusercontent.com"):
        raise ArchiveError("Unapproved download host: " + host)
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            new.remove_header("Authorization")
        return new


class GitHub:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.opener = build_opener(SafeRedirect())

    def open(self, url, binary=False):
        safe_url(url)
        source_archive = urlsplit(url).hostname == "api.github.com" and bool(
            re.match(r"^/repos/[^/]+/[^/]+/(?:zipball|tarball)/", urlsplit(url).path))
        # Source archive endpoints negotiate JSON before redirecting to codeload.
        # Uploaded release-asset endpoints instead require octet-stream.
        headers = {"User-Agent": "repository-dump-tool",
                   "Accept": "application/octet-stream" if binary and not source_archive else "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token and urlsplit(url).hostname == "api.github.com":
            headers["Authorization"] = "Bearer " + self.token
        for attempt in range(3):
            try:
                return self.opener.open(Request(url, headers=headers), timeout=45)
            except HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    delay = min(30, int(e.headers.get("Retry-After", 2 ** attempt)))
                    time.sleep(delay)
                    continue
                # Never print signed redirect URLs, headers, or response bodies.
                raise ArchiveError("HTTP %s from %s" % (e.code, urlsplit(url).hostname)) from None
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise ArchiveError("Network request failed for " + urlsplit(url).hostname) from None

    def one(self, path):
        url = path if path.startswith("https://") else API + path
        with self.open(url) as response:
            return json.load(response)

    def pages(self, path):
        url = path if path.startswith("https://") else API + path
        if "per_page=" not in url:
            url += ("&" if "?" in url else "?") + "per_page=100"
        result, seen = [], set()
        while url:
            if url in seen:
                raise ArchiveError("Pagination cycle detected")
            if urlsplit(url).hostname != "api.github.com":
                raise ArchiveError("Pagination left the GitHub API")
            seen.add(url)
            with self.open(url) as response:
                values = json.load(response)
                if not isinstance(values, list):
                    raise ArchiveError("Expected a paginated JSON array")
                result.extend(values)
                links = response.headers.get("Link", "")
            match = re.search(r'<([^>]+)>;\s*rel="next"', links)
            url = match.group(1) if match else None
        return result


def attachment_urls(text):
    result = set()
    for raw in URL_PATTERN.findall(html.unescape(text or "")):
        url = raw.rstrip(".,;:!?)")
        try:
            p = urlsplit(url)
            host = (p.hostname or "").lower()
            uuid = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
            uploaded = host == "github.com" and bool(
                re.fullmatch(r"/user-attachments/assets/" + uuid, p.path)
                or re.match(r"^/user-attachments/files/\d+/[^/]+$", p.path)
                or re.match(r"^/[^/]+/[^/]+/files/\d+/[^/]+$", p.path)
                or re.fullmatch(r"/[^/]+/[^/]+/assets/\d+/" + uuid, p.path))
            if uploaded or host == "user-images.githubusercontent.com":
                safe_url(url)
                result.add(url)
        except (ArchiveError, ValueError):
            continue
    return sorted(result)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(MIB), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_extension(url, content_type):
    suffix = Path(unquote(urlsplit(url).path)).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix or ""):
        return suffix
    mime = content_type.partition(";")[0].strip()
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
            "video/mp4": ".mp4", "audio/mpeg": ".mp3", "audio/wav": ".wav",
            "application/pdf": ".pdf"}.get(mime, mimetypes.guess_extension(mime) or ".bin")


class Assets:
    def __init__(self, client, root, max_bytes=2048 * MIB, part_bytes=64 * MIB):
        self.client, self.root = client, root
        self.max_bytes, self.part_bytes = max_bytes, part_bytes
        self.used_bytes, self.entries, self.references = 0, {}, {}
        self.old = {}
        old_manifest = root / "manifest.json"
        if old_manifest.exists():
            try:
                self.old = json.loads(old_manifest.read_text(encoding="utf-8")).get("assets", {})
            except (ValueError, OSError):
                pass

    def cached(self, entry):
        if not entry or entry.get("status") != "saved":
            return False
        full = hashlib.sha256()
        try:
            for part in entry["parts"]:
                path = (self.root / part["path"]).resolve()
                if not path.is_relative_to(self.root.resolve()) or path.is_symlink():
                    return False
                if path.stat().st_size != part["size"] or sha256_file(path) != part["sha256"]:
                    return False
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(MIB), b""):
                        full.update(chunk)
            return full.hexdigest() == entry["sha256"]
        except (KeyError, OSError, ValueError):
            return False

    def add(self, url, source, expected_size=None, expected_digest=None):
        refs = self.references.setdefault(url, [])
        if source not in refs:
            refs.append(source)
        if url in self.entries:
            return
        old = self.old.get(url)
        if self.cached(old) and (expected_size is None or old["size"] == expected_size):
            if expected_digest and expected_digest != "sha256:" + old["sha256"]:
                old = None
            else:
                self.entries[url] = dict(old, reused=True)
                return
        try:
            self.entries[url] = self.download(url, expected_size, expected_digest)
        except (ArchiveError, OSError, ValueError) as error:
            self.entries[url] = {"status": "failed", "error": str(error)}
        write_json(self.root / "manifest.json", {"assets": self.final()})
        if len(self.entries) % 25 == 0:
            print("assets processed: %s" % len(self.entries), flush=True)

    def download(self, url, expected_size=None, expected_digest=None):
        if expected_size is not None and expected_size > self.max_bytes - self.used_bytes:
            raise ArchiveError("Download budget exceeded; increase --max-download-mib")
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=self.root) as temporary:
            staging = Path(temporary)
            parts, total, digest = [], 0, hashlib.sha256()
            with self.client.open(url, binary=True) as response:
                expected_header = response.headers.get("Content-Length")
                content_type = response.headers.get("Content-Type", "")
                suffix = asset_extension(url, content_type)
                if expected_header and int(expected_header) > self.max_bytes - self.used_bytes:
                    raise ArchiveError("Download budget exceeded; increase --max-download-mib")
                finished = False
                while not finished:
                    path = staging / ("%06d" % len(parts))
                    part_size, part_hash = 0, hashlib.sha256()
                    with path.open("wb") as stream:
                        while part_size < self.part_bytes:
                            block = response.read(min(MIB, self.part_bytes - part_size))
                            if not block:
                                finished = True
                                break
                            if self.used_bytes + len(block) > self.max_bytes:
                                raise ArchiveError("Download budget exceeded; increase --max-download-mib")
                            stream.write(block)
                            total += len(block)
                            self.used_bytes += len(block)
                            part_size += len(block)
                            digest.update(block)
                            part_hash.update(block)
                    if part_size or not parts:
                        parts.append((path, part_size, part_hash.hexdigest()))
                if expected_header is not None and total != int(expected_header):
                    raise ArchiveError("Truncated HTTP response")
            if expected_size is not None and total != expected_size:
                raise ArchiveError("Release asset size mismatch")
            checksum = digest.hexdigest()
            if expected_digest and expected_digest != "sha256:" + checksum:
                raise ArchiveError("Release asset digest mismatch")
            saved = []
            directory = self.root / "assets" / checksum
            directory.mkdir(parents=True, exist_ok=True)
            for index, (path, size, part_hash) in enumerate(parts):
                filename = "download" + suffix
                if len(parts) > 1:
                    filename += ".part%06d" % (index + 1)
                destination = directory / filename
                path.replace(destination)
                saved.append({"path": destination.relative_to(self.root).as_posix(),
                              "size": size, "sha256": part_hash})
            return {"status": "saved", "size": total, "sha256": checksum,
                    "content_type": content_type, "parts": saved, "reused": False}

    def final(self):
        return {url: dict(entry, references=self.references[url])
                for url, entry in sorted(self.entries.items())}


def page(title, content):
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>' + html.escape(title) + '</title><style>'
            'body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;line-height:1.5}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:1rem}'
            'li{margin:.4rem 0}a{overflow-wrap:anywhere} .failed{color:#a00}'
            '</style><body><h1>' + html.escape(title) + '</h1>' + content + '</body></html>')


def text_block(heading, body):
    # All remote text is inert. Do not render arbitrary embedded HTML or scripts.
    return "<h2>" + html.escape(heading) + "</h2><pre>" + html.escape(body or "") + "</pre>"


def collect(repo, client, issue_number=None):
    prefix = "/repos/" + repo
    data = {"repository": client.one(prefix)}
    if issue_number is not None:
        item = client.one(prefix + "/issues/" + str(issue_number))
        issues = [item]
        comments = client.pages(prefix + "/issues/%s/comments" % issue_number)
        pulls = [client.one(prefix + "/pulls/" + str(issue_number))] if "pull_request" in item else []
        reviews = {}
        inline = client.pages(prefix + "/pulls/%s/comments" % issue_number) if pulls else []
        releases, tags = [], []
    else:
        issues = client.pages(prefix + "/issues?state=all")
        comments = client.pages(prefix + "/issues/comments")
        pulls = client.pages(prefix + "/pulls?state=all")
        inline = client.pages(prefix + "/pulls/comments")
        releases = client.pages(prefix + "/releases")
        tags = client.pages(prefix + "/tags")
        reviews = {}
    for pull in pulls:
        number = int(pull["number"])
        reviews[str(number)] = client.pages(prefix + "/pulls/%s/reviews" % number)
    for release in releases:
        release["assets"] = client.pages(prefix + "/releases/%s/assets" % int(release["id"]))
    readme = None
    if issue_number is None:
        try:
            readme = client.one(prefix + "/readme")
            if readme.get("encoding") == "base64":
                readme["body"] = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
                readme["id"] = 0
            else:
                readme = None
        except ArchiveError as error:
            if not str(error).startswith("HTTP 404"):
                raise
    data["readme"] = readme
    data.update(issues=issues, comments=comments, pulls=pulls, review_comments=inline,
                reviews=reviews, releases=releases, tags=tags)
    return data


def export(repo, output, client, issue_number=None, max_bytes=2048 * MIB):
    if not REPOSITORY.fullmatch(repo):
        raise ArchiveError("Repository must be owner/name")
    root = Path(output).resolve()
    if ".git" in [part.lower() for part in root.parts]:
        raise ArchiveError("Output must not be inside .git")
    root.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_json(root / "report.json", {"repository": repo, "started_at": started,
                                      "complete": False, "status": "running"})
    assets = Assets(client, root, max_bytes=max_bytes)
    try:
        data = collect(repo, client, issue_number)
    except (ArchiveError, OSError, ValueError) as error:
        report = {"repository": repo, "started_at": started, "complete": False,
                  "metadata_error": str(error), "scope": "issue" if issue_number else "repository"}
        write_json(root / "report.json", report)
        (root / "index.html").write_text(page("Archive incomplete", text_block("Error", str(error))),
                                       encoding="utf-8", newline="\n")
        return report
    write_json(root / "raw" / "snapshot.json", data)
    groups = [("issues", data["issues"]), ("pulls", data["pulls"]),
              ("comments", data["comments"]), ("review-comments", data["review_comments"]),
              ("releases", data["releases"])]
    if data.get("readme"):
        groups.append(("readme", [data["readme"]]))
    for number, reviews in data["reviews"].items():
        groups.append(("reviews-" + number, reviews))
    for kind, records in groups:
        for record in records:
            identity = str(int(record.get("id", record.get("number", 0))))
            source = kind + "/" + identity
            write_json(root / "raw" / kind / (identity + ".json"), record)
            for url in attachment_urls(record.get("body")):
                assets.add(url, source)
            if kind == "releases":
                for asset in record["assets"]:
                    assets.add(asset["url"], source, asset.get("size"), asset.get("digest"))
                # GitHub-generated source archives are separate from uploaded assets.
                for field in ("zipball_url", "tarball_url"):
                    if record.get(field):
                        assets.add(record[field], source + "/" + field)
    records = assets.final()
    failures = [url for url, entry in records.items() if entry["status"] != "saved"]
    report = {"repository": repo, "started_at": started,
              "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "single issue %s" % issue_number if issue_number else "issues, pull requests, releases, tags, root README",
              "complete": not failures and issue_number is None,
              "selected_scope_complete": not failures,
              "counts": {"issues": sum("pull_request" not in i for i in data["issues"]),
                         "pull_requests": len(data["pulls"]), "conversation_comments": len(data["comments"]),
                         "review_comments": len(data["review_comments"]),
                         "reviews": sum(map(len, data["reviews"].values())),
                         "releases": len(data["releases"]), "tags": len(data["tags"]),
                         "assets": len(records), "failed_assets": len(failures)},
              "downloaded_bytes": assets.used_bytes,
              "limitations": ["Snapshot is not atomic; edits made during the run can appear at different times.",
                              "GitHub does not expose deleted/private-inaccessible content or complete edit histories.",
                              "Separate GitHub Discussions, projects, wikis, Actions artifacts and Git history are outside this export."]}
    write_json(root / "manifest.json", {"repository": repo, "assets": records})
    write_json(root / "report.json", report)
    body = '<p><strong>' + ("Selected scope saved" if not failures else "INCOMPLETE: missing assets") + '</strong></p>'
    body += "<p>Scope: " + html.escape(report["scope"]) + "</p>"
    body += '<p><a href="report.json">Machine-readable report</a> · <a href="manifest.json">Asset manifest</a> · <a href="raw/snapshot.json">Original JSON</a></p>'
    body += text_block("Counts", json.dumps(report["counts"], indent=2))
    if data.get("readme"):
        (root / "readme.html").write_text(
            page("Root README", '<p><a href="index.html">Archive index</a></p>' +
                 text_block("README text", data["readme"]["body"])), encoding="utf-8", newline="\n")
        body += '<p><a href="readme.html">Root README and its preserved text</a></p>'

    by_issue = {}
    for comment in data["comments"]:
        number = comment["issue_url"].rsplit("/", 1)[-1]
        by_issue.setdefault(number, []).append(comment)
    for kind, items in [("issues", [i for i in data["issues"] if "pull_request" not in i]),
                        ("pulls", data["pulls"]), ("releases", data["releases"])]:
        body += "<h2>" + kind.title() + "</h2><ul>"
        for item in items:
            number = str(int(item.get("number", item["id"])))
            title = item.get("title") or item.get("name") or item.get("tag_name") or number
            relative = kind + "/" + number + ".html"
            content = '<p><a href="../index.html">Archive index</a></p>'
            content += text_block("Description", item.get("body"))
            if kind != "releases":
                for comment in by_issue.get(number, []):
                    content += text_block("Comment by " + (comment.get("user") or {}).get("login", "[deleted]"), comment.get("body"))
            if kind == "pulls":
                for review in data["reviews"].get(number, []):
                    content += text_block("Review: " + review.get("state", ""), review.get("body"))
                for comment in data["review_comments"]:
                    if comment["pull_request_url"].endswith("/" + number):
                        content += text_block("Inline review: " + comment.get("path", ""), comment.get("body"))
                        content += text_block("Diff context", comment.get("diff_hunk"))
            out = root / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page(str(title), content), encoding="utf-8", newline="\n")
            body += '<li><a href="' + relative + '">' + html.escape(str(title)) + "</a></li>"
        body += "</ul>"
    body += "<h2>Preserved attachments</h2><ul>"
    for url, entry in records.items():
        body += "<li>" + html.escape(url) + ": "
        if entry["status"] == "saved":
            for part in entry["parts"]:
                body += '<a href="' + html.escape(part["path"], quote=True) + '">' + html.escape(Path(part["path"]).name) + "</a> "
        else:
            body += '<strong class="failed">' + html.escape(entry["error"]) + "</strong>"
        body += "</li>"
    body += "</ul>" + text_block("Scope limits", "\n".join(report["limitations"]))
    (root / "index.html").write_text(page("Repository archive: " + repo, body), encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--output", required=True, help="Directory to hold archive files")
    parser.add_argument("--issue", type=int, help="Explicit partial demonstration of one issue/PR")
    parser.add_argument("--max-download-mib", type=int, default=2048, help="Download budget; failures are reported")
    args = parser.parse_args()
    if args.max_download_mib <= 0 or (args.issue is not None and args.issue <= 0):
        parser.error("Limits and issue numbers must be positive")
    try:
        report = export(args.repo, args.output, GitHub(), args.issue, args.max_download_mib * MIB)
        return 0 if report.get("selected_scope_complete") else 1
    except (ArchiveError, OSError, ValueError) as error:
        print("Archive failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
