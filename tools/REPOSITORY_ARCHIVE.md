# Repository archive tool

Python 3.10+, standard library only. Exports the three areas requested in bounty
#60: issues, pull requests, and releases. Existing repository content stays intact.

## Run from a phone

Once these files are on your repository's default branch:

1. Open **Actions → Archive repository → Run workflow** in GitHub.
2. Leave the source field empty for this repository, or enter a public
   owner/repository such as attogram/THE-ERROR-IS-THE-MESSAGE.
3. Open the run summary. Follow its link to the **repository-archive** branch
   and **repository-dump** folder. Read **report.json** for counts and failures.
4. Download that branch as a ZIP, then open **repository-dump/index.html** to
   browse the archive offline.

New forks may require **I understand my workflows, go ahead and enable them** on
the Actions page first. This workflow is manual only. It writes the archive to a
dedicated branch of the repository where it runs, even when the public source
is another repository. It does not separately push changes to that source.

A failed run still commits its available archive and failure report when possible.
It remains failed: missing files are never counted as a complete backup.

## What is saved

- Every page of open/closed issues and their complete conversation comments.
- Every page of open/closed PRs, conversation comments, review summaries/states,
  inline review comments, and diff context.
- Release descriptions, tags, and every page of release assets.
- The root README and its GitHub-uploaded attachments.
- GitHub-uploaded images, PDFs, audio, video, and files linked in descriptions,
  comments, and review bodies, including HTML image tags and bare URLs.
- Original JSON, readable HTML pages, a URL-to-file manifest, source references,
  byte counts, content types, and SHA-256 checksums.
- Available release-asset size and digest metadata are checked against downloads.

Code examples containing placeholder attachment IDs are not treated as uploaded files.
Actual uploads use GitHub's canonical UUID or numeric-file URLs.

Remote text is escaped as inert text, with a restrictive Content Security Policy.
No JavaScript or external network connection is needed to browse the saved index.

This is the listed export scope, not a full account backup. Separate GitHub
Discussions, project boards, wikis, Actions artifacts, and Git history are outside
this exporter. Deleted/inaccessible content and full historical body edits are
not exposed by these API endpoints. A snapshot is not atomic: concurrent activity
can be captured at different times. External website embeds are not copied.

## Local execution

    python3 tools/repo_dump.py --repo OWNER/REPO --output ./repository-dump

Public exports can run without authentication but may hit GitHub's API limits.
For an authorized repository, set GH_TOKEN through your normal secret-management
mechanism. Never commit it or paste it into an issue. The workflow supplies its
own short-lived GitHub token automatically.

For the first acceptance test against issue #60:

    python3 tools/repo_dump.py --repo attogram/THE-ERROR-IS-THE-MESSAGE --issue 60 --output ./issue-60-demo

Single-issue mode explicitly reports a partial scope and cannot claim a complete
repository. Any selected metadata or attachment failure produces a nonzero exit.

## Reruns and storage

Reruns reuse assets only after checking each part's size and checksum. Failed or
corrupted downloads are retried. Metadata is refreshed and earlier saved files
are retained rather than silently deleted when an upstream item disappears.

Downloads stream to disk and deduplicate by content hash. Files larger than
64 MiB are split into parts below GitHub's per-file limit. Concatenate the parts
in manifest order using binary mode and check the final SHA-256 to restore the
original. Single-part assets remain ordinary files.

The default new-download budget is 2 GiB per run; the workflow timeout is one
hour. Exceeding the budget is an explicit incomplete export. Review storage and
repository limits before increasing --max-download-mib. The tool retries transient
errors, restricts downloads to GitHub-controlled HTTPS hosts, strips API
authorization on cross-host redirects, and does not log signed CDN redirect URLs.

## Tests and acceptance

    python3 -m unittest discover -s tools -p test_repo_dump.py

Tests cover pagination, review conversations, release files, hostile HTML text,
attachment extraction, redirect credential handling, checksums, multipart
restoration, rerun reuse/repair, failures, partial scope, and cache path traversal.
A live export and the resulting branch must also be checked before claiming that
a particular repository has been saved.
