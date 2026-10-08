Check the committed pack. Read-only.

Steps:

1. Run `uv run reg-to-jdm verify --final`.
2. Run `uv run pytest`.
3. Print each failure, then PASS or FAIL. Exit non-zero on any failure, as `verify.yml` does in CI.

Do not edit files.
