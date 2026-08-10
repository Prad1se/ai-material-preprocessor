# 2.0 milestone trace

This file records the stable rollback point and GitHub review for every 2.0 milestone. It is updated
only after the milestone quality gate succeeds.

| Milestone | Branch | Commit | Draft PR | Verification | Status |
|---|---|---|---|---|---|
| M0 | `agent/architecture-baseline` | `c48be70..8a6d444` (merge `916467d`) | [#2](https://github.com/Prad1se/ai-material-preprocessor/pull/2) | 99 passed, 1 skipped; Ruff, mypy, privacy scan, PyInstaller build, packaged self-test, GUI smoke and both GitHub Actions runs passed | merged |
| M1 | `agent/task-center` | `ea28eb4` (merge `69693d2`) | [#3](https://github.com/Prad1se/ai-material-preprocessor/pull/3) | 132 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% GUI, PyInstaller build, packaged self-test and packaged GUI smoke passed; EXE SHA-256 `18A93CDD1DD3391DFC9368460185B528936D7AC2D2408A64BDD0488CD25758F8`; both GitHub Actions runs passed | merged |
| M2 | `agent/preview-quality` | `31b53fc` | [#4](https://github.com/Prad1se/ai-material-preprocessor/pull/4) | 142 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% preview UI, PyInstaller build, packaged self-test and packaged GUI smoke passed; EXE SHA-256 `890FA5FDEF3186A9ACD959346C338256B30BAD9DB468084979767ABFE26A3A5C`; CI pending | awaiting automatic merge |
| M3 | `agent/document-provenance` | pending | pending | pending | pending |
| M4 | `agent/video-management` | pending | pending | pending | pending |
| M5 | `agent/onboarding-settings` | pending | pending | pending | pending |
| M6 | `agent/release-pipeline` | pending | pending | pending | pending |

From the user's 2026-08-10 authorization onward, a milestone PR may be merged automatically only
after every local quality gate and required GitHub Actions check succeeds and the PR remains cleanly
mergeable. Account/credential changes, license risk, irreversible data operations, release publication,
product-direction changes, or any failed/ambiguous gate still require an explicit pause.
