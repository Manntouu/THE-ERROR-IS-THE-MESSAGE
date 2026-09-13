# Live export validation

Bounty: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/issues/60
PR: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/pull/66

## Hosted execution passed

The manually triggered GitHub Actions run completed successfully:
https://github.com/Manntouu/THE-ERROR-IS-THE-MESSAGE/actions/runs/34750105125

Its export ran from 2026-09-13 09:43:44 to 09:50:27 UTC, then committed and pushed
the complete archive back to the fork. The tested source commit was 7195e89.

Archive:
https://github.com/Manntouu/THE-ERROR-IS-THE-MESSAGE/tree/39c82de8ca56deb8d78a7d0e944513d802f126e1/repository-dump

- 60 issues, 6 pull requests, 168 conversation comments.
- 4 releases, 4 tags, plus the root README.
- 399 attachment URLs saved; zero failed assets.
- 400 part references resolve to 342 unique stored media files after deduplication.
- Logical asset size: 1,880,901,820 bytes; unique media stored: 1,529,159,214 bytes.
- The workflow's 14 focused tests passed.
- Every hosted attachment's size and SHA-256 matches the independently verified
  local export. All 342 remote Git media-blob IDs also match the verified local
  files; no new or unmatched asset URLs were present in the hosted snapshot.

The first local complete export finished at 09:20:29 UTC with 60 issues, 4 PRs,
167 comments and the same media. All 400 part references were reconstructed and
checked for part size/hash and original size/hash. Earlier references to 400 parts
counted those manifest references, not 400 distinct files on disk.

The generated index and issue #60 page were exercised in a real browser. The
manual workflow form was opened and filled at a 390-pixel phone-sized viewport,
with its Run workflow button visibly usable. The actual dispatch used the desktop
browser; no physical handset test was performed.

## Scope and failure behavior

The public snapshot contained no review summaries or inline review comments;
those paths are covered by fixtures. An initial 1 GiB download budget produced an
explicit incomplete report; resuming reused verified media and completed under
the 2 GiB budget. Invalid placeholder URLs in code examples are distinguished
from canonical uploaded attachments. Remote text remains escaped and inert.

Deleted/inaccessible content and complete edit histories are unavailable from
GitHub. Separate Discussions, projects, wikis, Actions artifacts and Git history
are outside this exporter. The snapshot is not atomic.

Initial GitHub website submission errors were resolved using fresh normal pages.
Implementation and validation were AI-assisted by Codex, authorized for Manntouu.
No bounty acceptance, reward or payment is claimed.
