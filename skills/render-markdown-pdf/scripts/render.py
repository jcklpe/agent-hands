#!/usr/bin/env python3
"""Render explicit Markdown and CSS inputs without loading a workspace or credentials."""

import argparse
import logging
import mimetypes
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit


THEMES = Path(__file__).resolve().parents[1] / "assets" / "themes"
ASSET_TYPES = {".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ttf", ".otf", ".woff", ".woff2"}


def strip_frontmatter(text):
    lines = text.lstrip("\ufeff").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "".join(lines)
    for index, line in enumerate(lines[1:], 1):
        if line.strip() in {"---", "..."}:
            return "".join(lines[index + 1:])
    raise ValueError("Unclosed YAML frontmatter; add its closing --- before rendering")


class RenderErrors(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.failed = False

    def emit(self, record):
        self.failed = True


def render(input_path, output_path, theme_path, asset_dirs, force=False):
    # uv-managed Python on macOS does not necessarily discover Homebrew's native libraries.
    if sys.platform == "darwin" and shutil.which("brew"):
        prefix = subprocess.run(["brew", "--prefix"], text=True, capture_output=True, timeout=15)
        library_dir = Path(prefix.stdout.strip()) / "lib"
        if prefix.returncode == 0 and library_dir.is_absolute() and library_dir.is_dir():
            existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(filter(None, [existing, str(library_dir)]))
    from weasyprint import CSS, HTML
    from weasyprint.urls import FatalURLFetchingError, URLFetcher, URLFetcherResponse

    roots = [directory.resolve(strict=True) for directory in asset_dirs]
    if any(not directory.is_dir() for directory in roots):
        raise ValueError("Every --asset-dir must be a directory containing only exportable assets")

    class AssetFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            parts = urlsplit(url)
            if parts.scheme == "data":
                return super().fetch(url, headers)
            if parts.scheme != "file" or parts.netloc not in {"", "localhost"}:
                raise FatalURLFetchingError("Remote resource fetching is disabled; supply a local asset instead")
            try:
                path = Path(unquote(parts.path)).resolve(strict=True)
                if not any(path.is_relative_to(root) for root in roots) or path.suffix.lower() not in ASSET_TYPES:
                    raise ValueError("Resource outside permitted assets; use --asset-dir for a dedicated asset directory")
                details = path.stat()
                if not stat.S_ISREG(details.st_mode) or details.st_size > 32 * 1024 * 1024:
                    raise ValueError("Assets must be regular files no larger than 32 MiB")
                return URLFetcherResponse(url=path.as_uri(), body=path.read_bytes(), headers={"Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream"})
            except (OSError, ValueError) as error:
                raise FatalURLFetchingError(str(error)) from error

    input_path = input_path.resolve(strict=True)
    theme_path = theme_path.resolve(strict=True)
    if theme_path.is_relative_to(THEMES):
        roots.append(THEMES)
    # Resolve the parent only: never follow an existing destination symlink when replacing output.
    output_path = output_path.parent.resolve(strict=True) / output_path.name
    if output_path.is_symlink() or (output_path.exists() and not output_path.is_file()):
        raise ValueError("Output must be a regular file, not a symlink or directory")
    if output_path in {input_path, theme_path} or (output_path.exists() and any(output_path.samefile(source) for source in (input_path, theme_path))):
        raise ValueError("Output must not replace an input or theme")
    if output_path.exists() and not force:
        raise ValueError("Output already exists; use --force to replace it after a successful render")
    if output_path.suffix.lower() != ".pdf":
        raise ValueError("Output must have a .pdf extension")
    if not shutil.which("pandoc"):
        raise ValueError("pandoc is required; see the skill's setup instructions")

    markdown = strip_frontmatter(input_path.read_text(encoding="utf-8-sig"))
    converted = subprocess.run(["pandoc", "--sandbox", "--from", "gfm", "--to", "html", "--wrap=none"], input=markdown, text=True, capture_output=True, timeout=60)
    if converted.returncode:
        raise ValueError("Pandoc conversion failed; check the Markdown and installed Pandoc version")

    fetcher = AssetFetcher(allowed_protocols={"data"})
    errors = RenderErrors()
    logger = logging.getLogger("weasyprint")
    logger.addHandler(errors)
    temporary_path = None
    try:
        stylesheet = CSS(string=theme_path.read_text(encoding="utf-8"), base_url=theme_path.as_uri(), url_fetcher=fetcher)
        html = '<!doctype html><html><head><meta charset="utf-8"></head><body class="typora-export"><div id="write" class="typora-export-content">' + converted.stdout + '</div></body></html>'
        document = HTML(string=html, base_url=input_path.as_uri(), url_fetcher=fetcher).render(stylesheets=[stylesheet])
        # A Markdown export is not a file bundle. Omit attachments and links that reveal local filesystem paths.
        document.metadata.attachments = []
        for page in document.pages:
            page.links[:] = [link for link in page.links if link[0] == "internal" or (link[0] == "external" and urlsplit(link[1]).scheme.lower() in {"https", "http", "mailto"})]
        if errors.failed:
            raise ValueError("Rendering reported an error; existing output was preserved")
        descriptor, temporary = tempfile.mkstemp(prefix=".markdown-pdf-", suffix=".pdf", dir=output_path.parent)
        temporary_path = Path(temporary)
        with os.fdopen(descriptor, "wb") as stream:
            document.write_pdf(stream)
        with temporary_path.open("rb") as stream:
            valid_header = stream.read(5) == b"%PDF-"
        if errors.failed or not valid_header:
            raise ValueError("Rendering did not produce a valid PDF; existing output was preserved")
        if force:
            os.replace(temporary_path, output_path)
        else:
            # An output created concurrently must not be silently overwritten.
            os.link(temporary_path, output_path)
        return output_path
    except FatalURLFetchingError as error:
        # WeasyPrint deliberately derives this from BaseException rather than Exception.
        raise ValueError(f"Resource refused: {error}") from error
    finally:
        logger.removeHandler(errors)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Markdown source; leading YAML frontmatter is omitted")
    parser.add_argument("--output", required=True, type=Path, help="PDF destination in an existing directory")
    parser.add_argument("--theme", required=True, help="plain, resume, compact, or a CSS file path")
    parser.add_argument("--asset-dir", action="append", default=[], type=Path, help="Allow local images/styles/fonts only beneath this directory (repeatable)")
    parser.add_argument("--force", action="store_true", help="Replace an existing PDF only after successful rendering")
    args = parser.parse_args()
    theme = THEMES / (args.theme + ".css") if args.theme in {"plain", "resume", "compact"} else Path(args.theme)
    try:
        output = render(args.input, args.output, theme, args.asset_dir, args.force)
    except (Exception, KeyboardInterrupt) as error:
        print(f"Render failed: {error}", file=sys.stderr)
        return 1
    print(f"Rendered: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
