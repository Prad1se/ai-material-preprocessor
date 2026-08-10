# 2.0 milestone trace

This file records the stable rollback point and GitHub review for every 2.0 milestone. It is updated
only after the milestone quality gate succeeds.

| Milestone | Branch | Commit | Draft PR | Verification | Status |
|---|---|---|---|---|---|
| M0 | `agent/architecture-baseline` | `c48be70..8a6d444` (merge `916467d`) | [#2](https://github.com/Prad1se/ai-material-preprocessor/pull/2) | 99 passed, 1 skipped; Ruff, mypy, privacy scan, PyInstaller build, packaged self-test, GUI smoke and both GitHub Actions runs passed | merged |
| M1 | `agent/task-center` | `ea28eb4` | [#3](https://github.com/Prad1se/ai-material-preprocessor/pull/3) | 132 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% GUI, PyInstaller build, packaged self-test and packaged GUI smoke passed; EXE SHA-256 `18A93CDD1DD3391DFC9368460185B528936D7AC2D2408A64BDD0488CD25758F8`; both GitHub Actions runs passed | awaiting merge |
| M2/M3 | `agent/document-provenance` | pending | pending | pending | pending |
| M4 | `agent/video-management` | pending | pending | pending | pending |
| M5 | `agent/onboarding-settings` | pending | pending | pending | pending |
| M6 | `agent/release-pipeline` | pending | pending | pending | pending |
