"""Shared Graph text cleanup for bounded Microsoft exports."""
import html
import re
from html.parser import HTMLParser


class HtmlCleaner(HTMLParser):
    block_tags = {"br", "div", "li", "p", "tr", "table", "ul", "ol", "blockquote", "h1", "h2", "h3", "h4"}
    # Content inside these tags is never message text.
    skip_tags = {"style", "script", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []
        self.skip_depth = 0

    def newline(self):
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        values = dict(attrs)
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if tag in self.block_tags:
            self.newline()
        if tag == "li":
            self.parts.append("- ")
        if tag == "a":
            self.links.append((values.get("href") or "", len(self.parts)))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.skip_tags:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag == "a" and self.links:
            href, start = self.links.pop()
            text = "".join(self.parts[start:]).strip()
            if href and href not in text:
                self.parts.append(f" ({href})" if text else href)
        if tag in self.block_tags and tag != "br":
            self.newline()

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def clean_text(value, content_type="text"):
    text = value or ""
    if (content_type or "").lower() == "html" or re.search(r"<[^>]+>", text):
        cleaner = HtmlCleaner()
        cleaner.feed(text)
        cleaner.close()
        text = cleaner.text()
    text = html.unescape(text).replace("\r", "").replace("\xa0", " ")
    lines = []
    blank = False
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            if lines and not blank:
                lines.append("")
            blank = True
            continue
        lines.append(line)
        blank = False
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def truncate(text, limit):
    if len(text) <= limit:
        return text
    clipped = text[:limit].rstrip()
    split_at = max(clipped.rfind("\n"), clipped.rfind(" "))
    if split_at > limit * 0.7:
        clipped = clipped[:split_at].rstrip()
    return f"{clipped}\n\n[content truncated]"


def quote(text):
    return "\n".join(f"    > {line}" for line in text.split("\n"))


def address(item):
    value = (item or {}).get("emailAddress") or item or {}
    name = value.get("name") or ""
    email = value.get("address") or ""
    if name and email and name.lower() != email.lower():
        return f"{name} <{email}>"
    return email or name
