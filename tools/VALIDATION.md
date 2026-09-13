# Live export validation

Bounty: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/issues/60
PR: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/pull/66

## Final hosted execution passed

Run: https://github.com/Manntouu/THE-ERROR-IS-THE-MESSAGE/actions/runs/34751238107
Tested source commit: 8cba97a (the later change to this record is documentation only).

Archive:
https://github.com/Manntouu/THE-ERROR-IS-THE-MESSAGE/tree/18d5693c50c71db0d214389da6a2517c65831f76/repository-dump

The export ran on 2026-09-13 from 10:12:50 to 10:13:10 UTC. Tests, export,
archive commit and push all succeeded.

- 60 issues, 9 PRs, 172 conversation comments, 5 inline comments and 1 review.
- 4 releases, 4 tags and the root README.
- 407 downloads: 399 GitHub-uploaded attachment URLs and 8 generated release
  source archives (a ZIP and TAR for each release); zero failures.
- 408 part references resolve to 350 unique stored media files after deduplication.
- Logical asset bytes: 1,959,761,565; unique stored media bytes: 1,608,018,959.
- All 17 focused tests passed on the hosted runner.
- All 399 previous attachment sizes/SHA-256 hashes remained identical. All 342
  previously verified remote Git media blobs still match their local files.
- All 8 new source archives were independently downloaded from the published
  archive and matched their sizes and SHA-256 hashes. Each ZIP passed CRC checks;
  each gzip/TAR was decompressed and parsed without extracting or executing files.
- Issue #60's 53 uploaded attachments were checked against their source references.

The generated index and issue #60 were exercised in a real browser. The manual
workflow controls were opened and filled at a 390-pixel phone-sized viewport and
the Run workflow button was visibly usable. Actual dispatch used the desktop
browser; no physical handset test was performed. Final inline-comment and review
coverage is now exercised by real data as well as fixtures.

## Earlier checks and corrected gaps

The initial local export independently verified every referenced attachment and
part hash. Its first 1 GiB budget produced an explicit incomplete report; resuming
reused verified media and completed under the 2 GiB budget.

Hosted run 34750105125 preserved 399 uploaded URLs successfully, but a final
coverage comparison identified eight GitHub-generated release source archives
outside the release.assets array. The first follow-up (34751069097) correctly
reported HTTP 415 for those new downloads and kept the previous media intact.
The source-archive endpoints require GitHub JSON media negotiation before a
redirect, while uploaded release assets require octet-stream. That distinction
and credential stripping on codeload redirects now have focused tests; two real
API probes and the final full hosted run passed.

The earlier 400-part count represented manifest references, not 400 distinct
files. The final counts above distinguish references and unique files.

## Scope

Deleted/inaccessible content and full edit histories are unavailable from GitHub.
Separate Discussions, projects, wikis, Actions artifacts and Git history are
outside this exporter; generated release source archives are included. Snapshots
are non-atomic. Remote text is escaped and inert, and inaccessible assets make a
run incomplete rather than silently disappearing.

Implementation and validation were AI-assisted by Codex for Manntouu. No bounty
acceptance, reward or payment is claimed.
