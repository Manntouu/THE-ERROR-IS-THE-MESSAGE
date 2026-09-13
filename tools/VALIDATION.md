# Live export validation

Source: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE
Bounty: https://github.com/attogram/THE-ERROR-IS-THE-MESSAGE/issues/60

The full local export finished at 2026-09-13 09:20:29 UTC:

- 60 issues, 4 pull requests, 167 conversation comments.
- 4 releases, 4 tags, plus the root README.
- 399 GitHub attachment URLs saved, with zero failed assets.
- 400 stored parts; 1,880,901,820 logical asset bytes.
- An independent streaming verification reconstructed every attachment and
  matched every part size, part SHA-256, original size and original SHA-256.
- 14 focused tests passed.
- The generated index was exercised in a real browser in both incomplete and
  complete states. Remote content remains escaped text.

The public repository had no review summaries or inline review comments in this
snapshot; those paths are covered by fixtures in the test suite.

The initial 1 GiB budget intentionally produced an incomplete report when
exhausted. A resumed export reused verified saved files and completed with the
2 GiB budget. A placeholder attachment URL inside a code example was distinguished
from a canonical uploaded file. Six root-README attachments were also preserved.

The mobile-triggered GitHub Actions workflow has not been run on a hosted runner.
The live export, independent checksum verification and browser check were local.
GitHub returned server errors while attempting to fork the source repository and
post a comment. No bounty acceptance, reward or payment is claimed.

Implementation and validation were AI-assisted by Codex, authorized for Manntouu.

