# 2.0 milestone trace

This file records the stable rollback point and GitHub review for every 2.0 milestone. It is updated
only after the milestone quality gate succeeds.

| Milestone | Branch | Commit | Draft PR | Verification | Status |
|---|---|---|---|---|---|
| M0 | `agent/architecture-baseline` | `c48be70..8a6d444` (merge `916467d`) | [#2](https://github.com/Prad1se/ai-material-preprocessor/pull/2) | 99 passed, 1 skipped; Ruff, mypy, privacy scan, PyInstaller build, packaged self-test, GUI smoke and both GitHub Actions runs passed | merged |
| M1 | `agent/task-center` | `ea28eb4` (merge `69693d2`) | [#3](https://github.com/Prad1se/ai-material-preprocessor/pull/3) | 132 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% GUI, PyInstaller build, packaged self-test and packaged GUI smoke passed; EXE SHA-256 `18A93CDD1DD3391DFC9368460185B528936D7AC2D2408A64BDD0488CD25758F8`; both GitHub Actions runs passed | merged |
| M2 | `agent/preview-quality` | `31b53fc` (merge `9b9ccb9`) | [#4](https://github.com/Prad1se/ai-material-preprocessor/pull/4) | 142 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% preview UI, PyInstaller build, packaged self-test and packaged GUI smoke passed; EXE SHA-256 `890FA5FDEF3186A9ACD959346C338256B30BAD9DB468084979767ABFE26A3A5C`; both GitHub Actions runs passed | merged |
| M3 | `agent/document-provenance` | `ab28146` (merge `6e21988`) | [#5](https://github.com/Prad1se/ai-material-preprocessor/pull/5) | 151 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% provenance report UI, PyInstaller build, packaged self-test and repeated packaged GUI smoke passed; EXE SHA-256 `175453223234B05B10059D0F3778B44478EB43C18F23D1E5055AE8B584545FE8`; both GitHub Actions runs passed | merged |
| M4 | `agent/video-management` | `9031c27..dbd9a5f` (merge `af5d4de`) | [#6](https://github.com/Prad1se/ai-material-preprocessor/pull/6) | 162 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native 100%/150% video metadata UI, PyInstaller build, packaged self-test and packaged GUI smoke passed; EXE SHA-256 `445A51F502E99C2A7FC2ED99F980CB1061CA0F2FEE123B3DF0EAC1A27F073259`; both GitHub Actions runs passed | merged |
| M5 | `agent/onboarding-settings` | `972ce98` | [#7](https://github.com/Prad1se/ai-material-preprocessor/pull/7) | 183 passed, 1 skipped locally; Ruff, mypy, diff, privacy, native light/dark 100%/150% GUI, PyInstaller build, packaged self-test, packaged GUI smoke and isolated first-run onboarding passed; EXE SHA-256 `D46739F07C7268FBC3D3196BA053E9E29E1D28C392B6E9C3CB8661811ABE4FEF`; GitHub Actions pending | checking |
| M6 | `agent/release-pipeline` | pending | pending | pending | pending |

From the user's 2026-08-10 authorization onward, a milestone PR may be merged automatically only
after every local quality gate and required GitHub Actions check succeeds and the PR remains cleanly
mergeable. Account/credential changes, license risk, irreversible data operations, release publication,
product-direction changes, or any failed/ambiguous gate still require an explicit pause.
