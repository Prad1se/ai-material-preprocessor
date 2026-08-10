# Public regression fixtures

All tracked fixtures are synthetic and contain no user documents, account names, private paths,
credentials, or real GPS history.

- `sample.html` is the minimal real MarkItDown input.
- `markdown/complex-source.md` exercises page markers, heading repair, tables, formulas, code,
  repeated headers, and image-risk reporting.
- `metadata/*.json` are synthetic ExifTool and ffprobe payloads.

Office and video integration tests generate deterministic temporary files from these public values.
Generated binaries and conversion outputs stay in pytest temporary directories and are never
committed.
