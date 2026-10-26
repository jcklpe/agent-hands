---
name: render-markdown-pdf
description: "Render an explicit Markdown file to PDF with a bundled or supplied CSS theme. Use for headless document export, including general reports and resumes, when the source, output destination, and theme are known."
---

# Render Markdown PDF
Convert Markdown with Pandoc and render it with WeasyPrint. This skill owns rendering and public themes, not document content, résumé conventions, source selection, or publication. It requires no other skill, provider account, credentials, or private workspace.

## Setup
Use this skill's `pyproject.toml` and `uv.lock`, not a shared provider environment. It requires Python 3.11+, uv, Pandoc with `--sandbox` support, native Pango libraries, and installed fonts. uv can supply Python; it does not install Pandoc or Pango. Follow [uv installation](https://docs.astral.sh/uv/getting-started/installation/), [Pandoc installation](https://pandoc.org/installing.html), and [WeasyPrint 69 prerequisites](https://doc.courtbouillon.org/weasyprint/v69.0/first_steps.html#installation) for the actual platform. Preserve existing toolchains. On macOS with Homebrew, missing native prerequisites can be installed with `brew install pandoc pango` within the user's setup scope; the script discovers Homebrew's library directory for uv-managed Python.

From this skill directory:

```sh
uv sync --locked --python 3.12
uv run --locked python scripts/render.py --help
uv run --locked python scripts/render.py /path/to/report.md --theme plain --output /path/to/report.pdf
```

When called elsewhere, use `uv run --project /path/to/render-markdown-pdf --locked python /path/to/render-markdown-pdf/scripts/render.py ...`. macOS with Pandoc 3.7.0.2 and the locked WeasyPrint 69.0 is locally verified. Fresh Linux/WSL/native Windows setup remains unverified; consult the platform prerequisites rather than claiming that uv alone supplies native libraries.

## Inputs and themes
Choose `--theme plain`, `--theme resume`, `--theme compact`, or an explicit CSS path. The destination directory must already exist. The [theme source record](assets/themes/SOURCE.md) identifies provenance and limits. The plain theme supports headings, prose, tables, lists, code, and pagination; the résumé theme preserves the existing Typora-shaped `#write` container, including inline `<span class="date">` markup. Compact retains the existing 0.6-inch-margin variant. The résumé themes prefer Merriweather headings and Arial body text, with fallbacks. Do not promise identical pagination across font installations. No formal academic theme is selected here.

Leading YAML frontmatter is omitted entirely; an unclosed block is an error. It does not become PDF title/author metadata. GFM and inline HTML are supported; this is not a browser, LaTeX, or Quarto execution engine. Code blocks display code without executing it.

Relative images resolve from the Markdown directory; CSS resources resolve from their stylesheet. Grant a dedicated asset directory explicitly with repeatable `--asset-dir /path/to/images`. Only regular CSS/image/font files beneath those resolved roots are eligible; symlink escapes and files larger than 32 MiB are refused. Bundled themes can also import resources within their own theme directory. Do not grant a workspace or home directory containing private material. Data URLs are supported. HTTP and other network resource fetches are refused; ordinary web/mail links remain clickable. PDF attachments and local-file hyperlinks are omitted. No `.env` is loaded.

Use reviewed Markdown/CSS and asset directories. These resource restrictions are not an OS sandbox or a memory/CPU limit for hostile documents. See [WeasyPrint's security guidance](https://doc.courtbouillon.org/weasyprint/v69.0/first_steps.html#security) before processing untrusted HTML/CSS/SVG.

## Export and verify
Existing output is refused unless `--force` is explicit. Successful rendering publishes a complete PDF atomically; conversion, resource, and rendering errors leave the previous destination untouched. Temporary output is private and removed on failure. Files publish with owner-only permissions. Output may not replace the input/theme or follow a destination symlink. CSS warnings can be nonfatal; actual renderer errors fail the export.

Inspect the resulting PDF, not just the exit code. Check extracted text and metadata with `pdftotext`/`pdfinfo`, render every page with `pdftoppm -png`, and view the images for clipping, missing glyphs, awkward breaks, and table/code overflow. Use synthetic inputs for package checks. A successful export is not authorization to publish or upload the document.

Run `uv run --locked python tests/test_render.py` for output-preservation and resource-boundary checks. `tests/fixtures/report.md` and `tests/fixtures/resume.md` are synthetic visual-review inputs; pass the report's `images/` directory as its asset grant. Write review PDFs outside the source collection or to its ignored `exports/` directory.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 render-markdown-pdf/scripts/link-skills.py --client codex
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
