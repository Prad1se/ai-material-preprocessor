# Examples

Small synthetic examples that show the project's core workflow: **raw input → AI Context Pack → traceable sources**.

| Example | Input | Output to explore |
| --- | --- | --- |
| [research-paper](research-paper/) | `input/sample-paper.pdf` (2-page synthetic PDF) | `sample-context-pack/` with PDF page provenance |
| [course-material](course-material/) | `input/sample-lecture.docx` (synthetic DOCX) | `sample-context-pack/` with document-level fallback |

Every `sample-context-pack/` is a real output of the app's own pipeline and contains:

- `START_HERE.md` — how to read and upload the pack
- `content.md` — the complete processed content archive
- `manifest.json` — machine-readable inventory (blocks, sources, provenance, integrity)
- `context-report.json` — the Context Report (budget, tokens, warnings, integrity)
- `packs/` — numbered context packs in the recommended upload order
- `sources/` — one folder per source with its processed content

No personal data, no real copyrighted documents, and no absolute paths are included.

## Try it

1. Open the app and add an `input/` file.
2. Choose **AI Context Pack** (or a preset such as *Research Paper*).
3. Generate the pack, then **Copy for AI**.
4. Use **View Source Map** to trace each block back to its page.
