# Contributing

## Development setup

1. Use Windows with Python 3.11 or newer.
2. Run `run.ps1` once to create `.venv` and install dependencies.
3. Create a focused branch from `main`.
4. Add a failing test before changing behavior.
5. Run `scripts/check_quality.ps1` before committing.

Use Conventional Commits such as `fix(ui): keep combo items readable`. Keep conversion logic out
of Qt widgets and invoke external programs through the process adapter with argument arrays,
timeouts, cancellation, and readable errors.

Do not commit personal documents, private paths, credentials, generated outputs, build folders, or
large media. Tests should use synthetic public fixtures and temporary directories. Pull requests
must explain scope, tests, risks, and rollback.

Security vulnerabilities should follow [SECURITY.md](SECURITY.md), not a public issue.
