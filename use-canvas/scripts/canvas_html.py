"""Pinned body conversion and explicit external-content/image discovery; never fetches URLs."""
import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup, NavigableString
from markdown_it import MarkdownIt
from markdownify import markdownify

from canvas_auth import CanvasError

SENSITIVE_QUERY = {"verifier", "token", "access_token", "download_frd", "download", "signature", "expires", "awsaccesskeyid"}


def public_link(url, origin):
    absolute = urljoin(origin + "/", url)
    parts = urlsplit(absolute)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in SENSITIVE_QUERY and not k.lower().startswith("x-amz-")]
    path = re.sub(r"(/files/\d+)/download/?$", r"\1", parts.path)
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def file_reference(url, origin, context, context_id):
    parts = urlsplit(urljoin(origin + "/", url))
    if parts.scheme != "https" or parts.netloc != urlsplit(origin).netloc:
        return None
    match = re.match(r"^/(?:api/v1/)?(?:(courses|groups)/(\d+)/)?files/(\d+)(?:/|$)", parts.path)
    if not match:
        return None
    if match[1] and (match[1] != context or match[2] != context_id):
        return None
    return match[3]


def informational_image(tag):
    if tag.get("alt") == "" or tag.get("role") == "presentation":
        return False
    sizes = []
    for dimension in ("width", "height"):
        match = re.fullmatch(r"\s*(\d+)(?:px)?\s*", str(tag.get(dimension, "")))
        sizes.append(int(match[1]) if match else None)
    return not all(n is not None and n <= 32 for n in sizes)


def analyse(html, origin, context, context_id, include_html=False):
    if not isinstance(html, str):
        raise CanvasError("malformed", "Canvas returned a non-text body")
    soup = BeautifulSoup(html, "html.parser")
    gaps, images, references = [], [], set()
    keep_html = include_html
    for tag in soup.find_all(True):
        for attribute in ("href", "src", "data-api-endpoint"):
            value = tag.get(attribute)
            if not isinstance(value, str):
                continue
            fid = file_reference(value, origin, context, context_id)
            if fid:
                references.add(fid)
                tag[attribute] = f"{origin}/{context}/{context_id}/files/{fid}"
            else:
                tag[attribute] = public_link(value, origin)
        if tag.name == "img":
            src = tag.get("src", "")
            meaningful = informational_image(tag)
            keep_html = keep_html or meaningful
            fid = file_reference(src, origin, context, context_id)
            if meaningful:
                if fid:
                    images.append({"file_id": fid, "src": src})
                else:
                    gaps.append({"kind": "external_image", "url": src})
        if tag.name == "a" and "/external_tools/" in tag.get("href", ""):
            gaps.append({"kind": "external_tool", "url": tag["href"]})
    raw_html = str(soup)
    for tag in list(soup.find_all(["iframe", "video", "audio", "object", "embed"])):
        if tag.parent is None:
            continue
        link = tag.get("src") or tag.get("data") or next((x.get("src") for x in tag.find_all("source") if x.get("src")), "")
        gap = {"kind": "iframe" if tag.name == "iframe" else "media", "url": link}
        gaps.append(gap)
        tag.replace_with(NavigableString(f"\n[External content: {gap['kind']} — {link or 'no link provided'}]\n"))
    markdown = markdownify(str(soup), heading_style="ATX", bullets="-", escape_underscores=True).strip() + "\n"
    result = {"markdown": markdown, "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest()}
    if keep_html:
        result["html"] = raw_html
    unique = lambda rows: sorted({tuple(sorted(x.items())) for x in rows})
    return result, [dict(x) for x in unique(gaps)], [dict(x) for x in unique(images)], sorted(references, key=lambda x: (len(x), x))


def markdown_to_html(markdown):
    return MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"]).render(markdown)


def body_file(path):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise CanvasError("body_invalid", "Body file must be readable UTF-8 text") from None
    if path.suffix.lower() == ".md":
        return markdown_to_html(text)
    if path.suffix.lower() == ".html":
        return text
    raise CanvasError("body_invalid", "Body file must end in .md or .html")
