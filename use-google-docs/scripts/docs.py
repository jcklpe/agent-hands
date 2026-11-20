#!/usr/bin/env python3
"""Read/edit existing Google Docs and list/add comments using provider-supplied authorization."""

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


DOCS_API = "https://docs.googleapis.com/v1/documents"


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def api_json(method, url, access_token, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Docs API returned HTTP {exc.code}: {detail}") from exc


def get_document(document_id, access_token):
    url = f"{DOCS_API}/{urllib.parse.quote(document_id)}?includeTabsContent=true&suggestionsViewMode=SUGGESTIONS_INLINE"
    return api_json("GET", url, access_token)


def structural_text(elements):
    chunks = []
    for element in elements or []:
        paragraph = element.get("paragraph")
        if paragraph:
            for paragraph_element in paragraph.get("elements", []):
                text_run = paragraph_element.get("textRun")
                if text_run:
                    chunks.append(text_run.get("content", ""))
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    chunks.append(structural_text(cell.get("content", [])))
        toc = element.get("tableOfContents")
        if toc:
            chunks.append(structural_text(toc.get("content", [])))
    return "".join(chunks)


def utf16_length(value):
    return len(value.encode("utf-16-le")) // 2


def structural_text_with_spans(elements):
    chunks = []
    spans = []
    for element in elements or []:
        paragraph = element.get("paragraph")
        if paragraph:
            for paragraph_element in paragraph.get("elements", []):
                text_run = paragraph_element.get("textRun")
                if not text_run:
                    continue
                content = text_run.get("content", "")
                index = paragraph_element.get("startIndex")
                if index is None:
                    raise ValueError("Google Docs text run is missing startIndex")
                chunks.append(content)
                for character in content:
                    next_index = index + utf16_length(character)
                    spans.append((index, next_index))
                    index = next_index
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    text, cell_spans = structural_text_with_spans(cell.get("content", []))
                    chunks.append(text)
                    spans.extend(cell_spans)
        toc = element.get("tableOfContents")
        if toc:
            text, toc_spans = structural_text_with_spans(toc.get("content", []))
            chunks.append(text)
            spans.extend(toc_spans)
    return "".join(chunks), spans


def structural_links(elements):
    links = []
    for element in elements or []:
        paragraph = element.get("paragraph")
        if paragraph:
            for paragraph_element in paragraph.get("elements", []):
                text_run = paragraph_element.get("textRun")
                link = (text_run or {}).get("textStyle", {}).get("link", {})
                if text_run and link.get("url"):
                    links.append({"text": text_run.get("content", ""), "url": link["url"]})
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    links.extend(structural_links(cell.get("content", [])))
        toc = element.get("tableOfContents")
        if toc:
            links.extend(structural_links(toc.get("content", [])))
    return links


def read_link_target(link):
    """Describe only a supplied destination; internal references are not invented URLs."""
    if link.get("url"):
        return link["url"]
    for kind in ("bookmark", "heading"):
        if kind in link:
            target = link[kind]
            return f"{kind}: {target.get('id') or '<unavailable>'}; tab: {target.get('tabId') or '<unavailable>'}"
        if link.get(kind + "Id"):
            return f"{kind}: {link[kind + 'Id']} (legacy reference)"
    if link.get("tabId"):
        return f"tab: {link['tabId']}"
    return "<target unavailable>"


def read_paragraph_element(element):
    """Return display text and supplied references without assigning editable indices."""
    if "textRun" in element:
        run = element["textRun"]
        text = run.get("content", "")
        link = run.get("textStyle", {}).get("link")
        links = [{"text": text, "target": read_link_target(link)}] if link is not None else []
        return text, links
    for field, properties, label_field, target_field, kind in (
        ("richLink", "richLinkProperties", "title", "uri", "link"),
        ("person", "personProperties", "name", "email", "person"),
    ):
        if field in element:
            values = element[field].get(properties, {})
            target = values.get(target_field)
            label = values.get(label_field) or (target if kind == "person" else None) or "label unavailable"
            display = f"[{kind}: {label}{'' if target else '; target unavailable'}]"
            destination = (f"email: {target}" if kind == "person" else target) if target else "<target unavailable>"
            return display, [{"text": label, "target": destination}]
    for field, properties, label_field, kind in (
        ("dateElement", "dateElementProperties", "displayText", "date"),
        ("dropdown", "dropdownProperties", "displayValue", "dropdown"),
    ):
        if field in element:
            label = element[field].get(properties, {}).get(label_field) or "label unavailable"
            return f"[{kind}: {label}]", []
    if "footnoteReference" in element:
        reference = element["footnoteReference"]
        label = f"footnote {reference.get('footnoteNumber') or '<number unavailable>'}"
        return f"[{label}; content not rendered]", [{"text": label, "target": f"footnote: {reference.get('footnoteId') or '<unavailable>'}"}]
    kinds = sorted(key for key in element if key not in {"startIndex", "endIndex"} and not key.startswith("suggested"))
    return f"[unsupported element: {', '.join(kinds)}]" if kinds else "[unavailable element]", []


def structural_read_view(elements):
    chunks, links = [], []
    for element in elements or []:
        if "paragraph" in element:
            for part in element["paragraph"].get("elements", []):
                text, references = read_paragraph_element(part)
                chunks.append(text)
                links.extend(references)
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    text, references = structural_read_view(cell.get("content", []))
                    chunks.append(text)
                    links.extend(references)
        elif "tableOfContents" in element:
            text, references = structural_read_view(element["tableOfContents"].get("content", []))
            chunks.append(text)
            links.extend(references)
        elif "sectionBreak" not in element:
            chunks.append("[unsupported document structure]\n")
    return "".join(chunks), links


def document_read_tabs(document, tab_ids):
    """Keep reference labels out of document_tabs, which owns mutation text and spans."""
    def view(tab_id, title, body):
        text, links = structural_read_view(body.get("content", []))
        return {"id": tab_id, "title": title, "text": text, "links": links}

    def visit(tabs):
        for tab in tabs or []:
            properties = tab.get("tabProperties", {})
            yield view(properties.get("tabId", ""), properties.get("title", "Untitled tab"), tab.get("documentTab", {}).get("body", {}))
            yield from visit(tab.get("childTabs", []))

    tabs = list(visit(document.get("tabs", [])))
    if not tabs:
        tabs = [view("", "Document", document.get("body", {}))]
    return select_tab_ids(tabs, tab_ids)


def walk_tabs(tabs):
    for tab in tabs or []:
        properties = tab.get("tabProperties", {})
        document_tab = tab.get("documentTab", {})
        body = document_tab.get("body", {})
        text, spans = structural_text_with_spans(body.get("content", []))
        yield {
            "id": properties.get("tabId", ""),
            "title": properties.get("title", "Untitled tab"),
            "text": text,
            "spans": spans,
            "links": structural_links(body.get("content", [])),
        }
        yield from walk_tabs(tab.get("childTabs", []))


def document_tabs(document):
    tabs = list(walk_tabs(document.get("tabs", [])))
    if tabs:
        return tabs
    text, spans = structural_text_with_spans(document.get("body", {}).get("content", []))
    body = document.get("body", {})
    return [{"id": "", "title": "Document", "text": text, "spans": spans, "links": structural_links(body.get("content", []))}]


def selected_tabs(document, tab_ids):
    return select_tab_ids(document_tabs(document), tab_ids)


def select_tab_ids(tabs, tab_ids):
    if not tab_ids:
        return tabs
    wanted = set(tab_ids)
    selected = [tab for tab in tabs if tab["id"] in wanted]
    missing = wanted - {tab["id"] for tab in selected}
    if missing:
        raise ValueError(f"Unknown tab ID(s): {', '.join(sorted(missing))}")
    return selected


def text_argument(value, path, label):
    if value is not None:
        return value
    if path is not None:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    raise ValueError(f"{label} text is required")


def document_id_from(args):
    document_id = (args.document_id or "").strip()
    if not document_id:
        raise ValueError("Provide --document-id")
    return document_id


def access_token():
    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()
    if not token:
        raise ValueError("GOOGLE_ACCESS_TOKEN is required (normally set by the Docs shell wrapper)")
    return token


def command_read(args):
    document_id = document_id_from(args)
    document = get_document(document_id, access_token())
    print(f"# {document.get('title', 'Untitled document')}")
    print(f"Document ID: {document_id}")
    print(f"Revision ID: {document.get('revisionId', '<missing>')}")
    for tab in document_read_tabs(document, args.tab_id):
        print(f"\n## {tab['title']} [{tab['id'] or 'first-tab'}]\n")
        print(tab["text"], end="" if tab["text"].endswith("\n") else "\n")
        if args.show_links:
            print("\nEmbedded links:")
            for link in tab["links"]:
                print(f"- {link['text']} -> {link['target']}")
    return 0


def count_matches(document, tab_ids, old_text):
    return sum(tab["text"].count(old_text) for tab in selected_tabs(document, tab_ids))


def exact_text_range(document, tab_ids, value):
    matches = []
    for tab in selected_tabs(document, tab_ids):
        position = tab["text"].find(value)
        while position >= 0:
            matches.append((tab, position))
            position = tab["text"].find(value, position + 1)
    if len(matches) != 1:
        raise ValueError(f"Exact text must occur once in the selected scope; found {len(matches)}")
    tab, position = matches[0]
    end_position = position + len(value)
    if not value or end_position > len(tab["spans"]):
        raise ValueError("Unable to resolve the exact text to Google Docs indices")
    matched_spans = tab["spans"][position:end_position]
    if any(left[1] != right[0] for left, right in zip(matched_spans, matched_spans[1:])):
        raise ValueError("Exact text crosses a native element or structural gap; select contiguous plain text")
    return {
        "tab_id": tab["id"],
        "start_index": tab["spans"][position][0],
        "end_index": tab["spans"][end_position - 1][1],
    }


def parse_link_specs(specs, new_text):
    links = []
    occupied = []
    for spec in specs or []:
        label, separator, url = spec.partition("=")
        label = label.strip()
        url = url.strip()
        if not separator or not label or not url:
            raise ValueError("Each --link must use the form 'visible text=https://example.com'")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Link URL must be HTTP(S): {url}")
        if new_text.count(label) != 1:
            raise ValueError(f"Link text must occur once in the replacement text: {label!r}")
        start = new_text.index(label)
        end = start + len(label)
        if any(start < other_end and other_start < end for other_start, other_end in occupied):
            raise ValueError(f"Link text overlaps another link: {label!r}")
        occupied.append((start, end))
        links.append({"label": label, "url": url, "start": start, "end": end})
    return links


def link_style_requests(old_range, new_text, links):
    requests = []
    for link in links:
        start_index = old_range["start_index"] + utf16_length(new_text[: link["start"]])
        end_index = old_range["start_index"] + utf16_length(new_text[: link["end"]])
        range_value = {"startIndex": start_index, "endIndex": end_index}
        if old_range["tab_id"]:
            range_value["tabId"] = old_range["tab_id"]
        requests.append(
            {
                "updateTextStyle": {
                    "range": range_value,
                    "textStyle": {"link": {"url": link["url"]}},
                    "fields": "link",
                }
            }
        )
    return requests


def print_replacement_plan(document, document_id, tab_ids, old_text, new_text, links):
    print("Google Docs exact replacement plan:")
    print(f"Document: {document.get('title', 'Untitled document')} ({document_id})")
    print(f"Revision read: {document.get('revisionId', '<missing>')}")
    print(f"Tabs: {', '.join(tab_ids) if tab_ids else '<all tabs>'}")
    print("--- current exact text ---")
    print(old_text)
    print("--- proposed replacement ---")
    print(new_text)
    if links:
        print("--- embedded links ---")
        for link in links:
            print(f"{link['label']} -> {link['url']}")
    print("--- end plan ---")


def suggestion_projection(document, suggestion_ids, accept):
    """Project only our new text suggestions; retain other collaborators' inline text."""
    projected = copy.deepcopy(document)

    def visit(node):
        if isinstance(node, dict):
            run = node.get("textRun")
            if run:
                field = "suggestedDeletionIds" if accept else "suggestedInsertionIds"
                if suggestion_ids.intersection(run.get(field, [])):
                    run["content"] = ""
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(projected)
    return {tab["id"]: tab["text"] for tab in document_tabs(projected)}


def check_suggestion_range(document, old_range, old_text):
    if old_range["end_index"] - old_range["start_index"] != utf16_length(old_text):
        raise ValueError("Suggestion target crosses a native element or structural gap; select contiguous plain text")
    _, target = get_target_tab(document, [old_range["tab_id"]] if old_range["tab_id"] else [])

    def visit(node):
        if isinstance(node, dict):
            start, end = node.get("startIndex"), node.get("endIndex")
            if start is not None and end is not None and start < old_range["end_index"] and end > old_range["start_index"]:
                owners = [node, node.get("textRun", {}), node.get("paragraph", {})]
                if any(value for owner in owners for key, value in owner.items() if key.startswith("suggested")):
                    raise ValueError("Target overlaps an existing suggestion; review it before proposing another replacement")
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(target)


def execute_suggestion(document_id, token, document, old_range, old_text, new_text):
    request = {"replaceText": new_text, "containsText": {"text": old_text, "matchCase": True, "searchByRegex": False}}
    if old_range["tab_id"]:
        request["tabsCriteria"] = {"tabIds": [old_range["tab_id"]]}
    payload = {"requests": [{"replaceAllText": request}], "writeControl": {"requiredRevisionId": document["revisionId"], "writeMode": "SUGGEST"}}
    try:
        result = api_json("POST", f"{DOCS_API}/{urllib.parse.quote(document_id)}:batchUpdate", token, payload)
    except Exception as exc:
        raise RuntimeError(f"Suggestion request failed or outcome is uncertain; inspect the document before retrying. No direct-edit fallback was attempted. {exc}") from exc
    ids = {sid for response in result.get("suggestionResponses", []) for sid in response.get("createdSuggestionIds", [])}
    print("Suggestion IDs: " + (", ".join(sorted(ids)) or "<not returned>"))
    if result.get("commentUpdateState") != "ALL_SAVED" or not ids:
        raise RuntimeError("PARTIAL: suggestion/model changes may have been saved, but thread persistence was not confirmed; inspect the document and do not resend automatically")
    try:
        saved = get_document(document_id, token)
        before = {tab["id"]: tab["text"] for tab in document_tabs(document)}
        expected = dict(before)
        expected[old_range["tab_id"]] = expected[old_range["tab_id"]].replace(old_text, new_text, 1)
        if suggestion_projection(saved, ids, False) != before or suggestion_projection(saved, ids, True) != expected:
            raise ValueError("pending insertion/deletion text or surrounding text differs from the approved replacement")
    except Exception as exc:
        raise RuntimeError(f"PARTIAL: suggestion submitted but readback failed; inspect the reported IDs, do not resend. {exc}") from exc
    print("Verified pending suggestion: original text preserved; accepting these IDs produces the exact replacement. No suggestion was accepted.")
    return 0


def command_replace_once(args):
    document_id = document_id_from(args)
    old_text = text_argument(args.old, args.old_file, "Old")
    new_text = text_argument(args.new, args.new_file, "New")
    if not old_text:
        raise ValueError("Old text must not be empty")
    suggest = getattr(args, "suggest", False)
    if suggest and (args.markdown or args.link or not new_text or old_text == new_text or any(c in old_text + new_text for c in "\r\n")):
        raise ValueError("--suggest supports a changed, nonempty single-paragraph plain-text replacement only; omit --markdown/--link and paragraph breaks")
    token = access_token()
    document = get_document(document_id, token)
    matches = count_matches(document, args.tab_id, old_text)
    if matches != 1:
        raise ValueError(f"Exact old text must occur once in the selected scope; found {matches}")
    if args.markdown and (old_text.endswith("\n") or old_text.startswith("\n")):
        raise ValueError("--markdown old text must not start or end with a newline (a file from grep or printf ends in one); deleting a paragraph break would merge the inserted text into the neighbouring paragraph")
    if args.markdown and args.link:
        raise ValueError("--markdown takes links as [text](url) in the Markdown; do not combine it with --link")
    links = [] if args.markdown else parse_link_specs(args.link, new_text)
    old_range = exact_text_range(document, args.tab_id, old_text)
    if suggest:
        check_suggestion_range(document, old_range, old_text)
    blocks = parse_markdown_blocks(new_text) if args.markdown else None
    if args.markdown and not blocks:
        raise ValueError("New Markdown is empty")
    print_replacement_plan(document, document_id, args.tab_id, old_text, new_text, links)
    if suggest:
        print("Mode: SUGGEST — pending tracked replacement, never a direct edit")
    if args.markdown:
        print(f"Formatting: Markdown ({len(blocks)} block(s): headings, bullets, nested bullets, bold, italic, links); the rest of the Doc is untouched.")
    if not args.execute:
        print("DRY RUN: no Google Doc was changed. Re-run with --execute after approval.")
        return 0

    live_document = get_document(document_id, token)
    live_matches = count_matches(live_document, args.tab_id, old_text)
    if live_matches != 1:
        raise ValueError(f"Document changed before execution; exact old text now occurs {live_matches} times")
    revision_id = live_document.get("revisionId")
    if not revision_id:
        raise ValueError("Google Docs response did not include a revisionId")
    live_old_range = exact_text_range(live_document, args.tab_id, old_text)
    if live_old_range != old_range:
        raise ValueError("Document changed before execution; exact text moved to a different range")
    if suggest:
        if revision_id != document.get("revisionId"):
            raise ValueError("Document changed after the suggestion preview; review a fresh preview")
        check_suggestion_range(live_document, live_old_range, old_text)
        return execute_suggestion(document_id, token, live_document, live_old_range, old_text, new_text)
    if args.markdown:
        requests, _ = build_markdown_replace_requests(live_old_range["tab_id"], live_old_range, blocks)
        payload = {"requests": requests, "writeControl": {"requiredRevisionId": revision_id}}
        url = f"{DOCS_API}/{urllib.parse.quote(document_id)}:batchUpdate"
        try:
            result = api_json("POST", url, token, payload)
        except RuntimeError as exc:
            message = str(exc)
            if "HTTP 403" in message or "PERMISSION_DENIED" in message or "insufficient" in message.lower():
                alias = os.environ.get("GOOGLE_DOCS_ALIAS", "").strip()
                hint = f"run: setup-google-services/scripts/authorize auth {alias} --docs-write" if alias else "authorize the Docs write scope: setup-google-services/scripts/authorize auth ALIAS --docs-write"
                raise RuntimeError(f"{message}\nHINT: editing needs the Google Docs write scope — {hint}") from exc
            raise
        print(f"Updated document at revision {result.get('writeControl', {}).get('requiredRevisionId', revision_id)}; replaced 1 match with {len(blocks)} formatted block(s)")
        return 0
    replace_request = {
        "replaceText": new_text,
        "containsText": {"text": old_text, "matchCase": True, "searchByRegex": False},
    }
    if args.tab_id:
        replace_request["tabsCriteria"] = {"tabIds": args.tab_id}
    requests = [{"replaceAllText": replace_request}]
    requests.extend(link_style_requests(live_old_range, new_text, links))
    payload = {
        "requests": requests,
        "writeControl": {"requiredRevisionId": revision_id},
    }
    url = f"{DOCS_API}/{urllib.parse.quote(document_id)}:batchUpdate"
    try:
        result = api_json("POST", url, token, payload)
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 403" in message or "PERMISSION_DENIED" in message or "insufficient" in message.lower():
            alias = os.environ.get("GOOGLE_DOCS_ALIAS", "").strip()
            hint = (
                f"run: setup-google-services/scripts/authorize auth {alias} --docs-write"
                if alias
                else "authorize the Docs write scope: setup-google-services/scripts/authorize auth ALIAS --docs-write"
            )
            raise RuntimeError(f"{message}\nHINT: editing needs the Google Docs write scope — {hint}") from exc
        raise
    responses = result.get("replies") or result.get("responses") or []
    changed = 0
    for response in responses:
        changed += response.get("replaceAllText", {}).get("occurrencesChanged", 0)
    if changed != 1:
        raise RuntimeError(f"Google reported {changed} replacements; expected exactly 1")
    print(f"Updated document at revision {result.get('writeControl', {}).get('requiredRevisionId', revision_id)}; replacements: {changed}")
    return 0



# ---- set-body: replace a document's entire body in place (preserves doc id/history/links) ----

def _flatten_tabs(tabs, out):
    for tab in tabs or []:
        props = tab.get("tabProperties", {})
        body = tab.get("documentTab", {}).get("body", {})
        out.append((props.get("tabId", ""), body))
        _flatten_tabs(tab.get("childTabs", []), out)


def get_target_tab(document, tab_ids):
    tabs = document.get("tabs")
    if tabs:
        flat = []
        _flatten_tabs(tabs, flat)
        if not flat:
            return None, document.get("body", {})
        if tab_ids:
            wanted = set(tab_ids)
            for tid, body in flat:
                if tid in wanted:
                    return tid, body
            raise ValueError(f"Unknown tab ID(s): {', '.join(tab_ids)}")
        return flat[0]
    return None, document.get("body", {})


def body_end_index(body):
    end = 1
    for element in body.get("content", []) or []:
        ei = element.get("endIndex")
        if ei is not None and ei > end:
            end = ei
    return end


_INLINE_TOKEN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*")


def parse_inline(text):
    """Return (plain_text, spans). Spans are code-point ranges into plain_text."""
    plain = ""
    spans = []
    pos = 0
    for match in _INLINE_TOKEN.finditer(text):
        plain += text[pos:match.start()]
        if match.group(1) is not None:
            label, url = match.group(1), match.group(2)
            start = len(plain); plain += label; end = len(plain)
            spans.append({"start": start, "end": end, "link": url})
        elif match.group(3) is not None:
            # Bold may wrap a link, as in **[label](url)**: parse the inside too and shift its spans.
            inner_plain, inner_spans = parse_inline(match.group(3))
            start = len(plain); plain += inner_plain; end = len(plain)
            spans.extend(dict(span, start=span["start"] + start, end=span["end"] + start) for span in inner_spans)
            spans.append({"start": start, "end": end, "bold": True})
        elif match.group(4) is not None:
            seg = match.group(4); start = len(plain); plain += seg; end = len(plain)
            spans.append({"start": start, "end": end, "italic": True})
        pos = match.end()
    plain += text[pos:]
    return plain, spans


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^([ \t]*)[-*]\s+(.*)$")


def parse_markdown_blocks(md):
    blocks = []
    for raw in md.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.strip() == "":
            blocks.append({"style": "NORMAL_TEXT", "bullet": False, "level": 0, "text": "", "spans": []})
            continue
        mh = _HEADING_RE.match(line)
        mb = _BULLET_RE.match(line)
        if mh:
            level = min(len(mh.group(1)), 6)
            plain, spans = parse_inline(mh.group(2).strip())
            blocks.append({"style": f"HEADING_{level}", "bullet": False, "level": 0, "text": plain, "spans": spans})
        elif mb:
            indent = mb.group(1).replace("\t", "  ")
            plain, spans = parse_inline(mb.group(2).strip())
            blocks.append({"style": "NORMAL_TEXT", "bullet": True, "level": len(indent) // 2, "text": plain, "spans": spans})
        else:
            plain, spans = parse_inline(line)
            blocks.append({"style": "NORMAL_TEXT", "bullet": False, "level": 0, "text": plain, "spans": spans})
    while blocks and blocks[-1]["text"] == "" and not blocks[-1]["bullet"]:
        blocks.pop()
    return blocks


def _range(tab_id, start, end):
    value = {"startIndex": start, "endIndex": end}
    if tab_id:
        value["tabId"] = tab_id
    return value


def _location(tab_id, index):
    value = {"index": index}
    if tab_id:
        value["tabId"] = tab_id
    return value


def build_setbody_requests(tab_id, insert_start, blocks):
    # Nested bullets get leading tabs: createParagraphBullets turns each leading tab into one nesting level and removes it. Bullet requests therefore run last, in reverse document order, so removing tabs never shifts an index another request still needs.
    final = ""
    metas = []
    for i, block in enumerate(blocks):
        cp_para = len(final)
        if block["bullet"]:
            final += "\t" * block["level"]
        cp_start = len(final)
        final += block["text"]
        cp_text_end = len(final)
        if i != len(blocks) - 1:
            final += "\n"
        metas.append((cp_para, cp_start, cp_text_end, block))

    def abs_idx(cp):
        return insert_start + utf16_length(final[:cp])

    requests = [{"insertText": {"location": _location(tab_id, insert_start), "text": final}}]
    runs = []
    for cp_para, cp_start, cp_text_end, block in metas:
        a = abs_idx(cp_para)
        z = abs_idx(cp_text_end)
        para_end = z if z > a else a + 1
        if block["style"].startswith("HEADING_"):
            requests.append({"updateParagraphStyle": {
                "range": _range(tab_id, a, para_end),
                "paragraphStyle": {"namedStyleType": block["style"]},
                "fields": "namedStyleType"}})
        if block["bullet"]:
            if runs and runs[-1]["open"]:
                runs[-1]["end"] = para_end
            else:
                runs.append({"start": a, "end": para_end, "open": True})
        elif runs:
            runs[-1]["open"] = False
        for span in block["spans"]:
            s = abs_idx(cp_start + span["start"])
            e = abs_idx(cp_start + span["end"])
            if e <= s:
                continue
            if span.get("link"):
                requests.append({"updateTextStyle": {
                    "range": _range(tab_id, s, e),
                    "textStyle": {"link": {"url": span["link"]}},
                    "fields": "link"}})
            style = {}
            fields = []
            if span.get("bold"):
                style["bold"] = True; fields.append("bold")
            if span.get("italic"):
                style["italic"] = True; fields.append("italic")
            if fields:
                requests.append({"updateTextStyle": {
                    "range": _range(tab_id, s, e),
                    "textStyle": style,
                    "fields": ",".join(fields)}})
    for run in reversed(runs):
        requests.append({"createParagraphBullets": {
            "range": _range(tab_id, run["start"], run["end"]),
            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})
    return requests, final


def build_markdown_replace_requests(tab_id, old_range, blocks):
    """Delete the matched text and insert formatted blocks in its place, leaving the rest of the Doc (chips, links, other paragraphs) untouched."""
    start, end = old_range["start_index"], old_range["end_index"]
    body_requests, final = build_setbody_requests(tab_id, start, blocks)
    inserted_end = start + utf16_length(final)
    requests = [{"deleteContentRange": {"range": _range(tab_id, start, end)}}, body_requests[0]]
    # Inserted paragraphs inherit the matched paragraph's style (often a bullet); reset them so only the Markdown decides the formatting.
    if inserted_end > start:
        requests.append({"deleteParagraphBullets": {"range": _range(tab_id, start, inserted_end)}})
        requests.append({"updateParagraphStyle": {
            "range": _range(tab_id, start, inserted_end),
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT",
                               "indentStart": {"magnitude": 0, "unit": "PT"},
                               "indentFirstLine": {"magnitude": 0, "unit": "PT"}},
            "fields": "namedStyleType,indentStart,indentFirstLine"}})
        requests.append({"updateTextStyle": {
            "range": _range(tab_id, start, inserted_end),
            "textStyle": {},
            "fields": "bold,italic,link"}})
    requests.extend(body_requests[1:])
    return requests, final


def command_set_body(args):
    document_id = document_id_from(args)
    md = text_argument(args.new, args.file, "Body")
    token = access_token()
    document = get_document(document_id, token)
    tab_id, body = get_target_tab(document, args.tab_id)
    end_index = body_end_index(body)
    blocks = parse_markdown_blocks(md)
    if not blocks:
        raise ValueError("Body content is empty")
    _, final = build_setbody_requests(tab_id, 1, blocks)
    print("Google Docs set-body plan:")
    print(f"Document: {document.get('title', 'Untitled document')} ({document_id})")
    print(f"Revision read: {document.get('revisionId', '<missing>')}")
    print(f"Target tab: {tab_id or '<first / legacy body>'}")
    print(f"Clears existing body [1, {end_index - 1}) and inserts {len(blocks)} block(s) in place (document identity retained; native chips and existing body formatting can be lost).")
    print("--- new body (plain preview) ---")
    print(final)
    print("--- end plan ---")
    if not args.execute:
        print("DRY RUN: no Google Doc was changed. Re-run with --execute after approval.")
        return 0

    live = get_document(document_id, token)
    revision_id = live.get("revisionId")
    if not revision_id:
        raise ValueError("Google Docs response did not include a revisionId")
    if revision_id != document.get("revisionId"):
        raise ValueError("Document changed after the body preview; read and review it again before replacing it")
    live_tab_id, live_body = get_target_tab(live, args.tab_id)
    live_end = body_end_index(live_body)
    requests = []
    if live_end > 2:
        requests.append({"deleteContentRange": {"range": _range(live_tab_id, 1, live_end - 1)}})
    body_requests, _ = build_setbody_requests(live_tab_id, 1, blocks)
    requests.extend(body_requests)
    payload = {"requests": requests, "writeControl": {"requiredRevisionId": revision_id}}
    url = f"{DOCS_API}/{urllib.parse.quote(document_id)}:batchUpdate"
    try:
        api_json("POST", url, token, payload)
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 403" in message or "PERMISSION_DENIED" in message or "insufficient" in message.lower():
            alias = os.environ.get("GOOGLE_DOCS_ALIAS", "").strip()
            hint = (f"run: setup-google-services/scripts/authorize auth {alias} --docs-write" if alias
                    else "authorize the Docs write scope: setup-google-services/scripts/authorize auth ALIAS --docs-write")
            raise RuntimeError(f"{message}\nHINT: editing needs the Google Docs write scope — {hint}") from exc
        raise
    print(f"Set body of document {document_id} in place ({len(blocks)} blocks).")
    return 0


# ---- comments: list and add Drive comments on a Doc ----

DRIVE_FILES_API = "https://www.googleapis.com/drive/v3/files"
COMMENT_FIELDS = "id,content,quotedFileContent,author(displayName),createdTime,resolved"


def comment_scope_hint(message):
    alias = os.environ.get("GOOGLE_DOCS_ALIAS", "").strip() or "ALIAS"
    return f"{message}\nHINT: commenting needs the full Drive scope — run: setup-google-services/scripts/authorize auth {alias} --docs-comment"


def build_comment_payload(document, tab_ids, quote, body):
    # Google Docs does not anchor API-created comments to a text range; the quote rides along as quotedFileContent and shows in the comment. Uniqueness is still required so the quote cannot point at the wrong passage.
    if not body or not body.strip():
        raise ValueError("Comment body must not be empty")
    payload = {"content": body}
    if quote is not None:
        if not quote:
            raise ValueError("Quote must not be empty; omit --quote for an unquoted comment")
        matches = count_matches(document, tab_ids, quote)
        if matches != 1:
            raise ValueError(f"Quoted text must occur once in the selected scope; found {matches}. Lengthen the quote until it is unique, or check punctuation against `use-google-docs/scripts/docs read`.")
        payload["quotedFileContent"] = {"mimeType": "text/plain", "value": quote}
    return payload


def command_comments(args):
    document_id = document_id_from(args)
    token = access_token()
    params = {"fields": f"comments({COMMENT_FIELDS}),nextPageToken", "pageSize": "100", "includeDeleted": "false"}
    comments = []
    while True:
        url = f"{DRIVE_FILES_API}/{urllib.parse.quote(document_id)}/comments?{urllib.parse.urlencode(params)}"
        try:
            result = api_json("GET", url, token)
        except RuntimeError as exc:
            if "HTTP 403" in str(exc):
                raise RuntimeError(comment_scope_hint(str(exc))) from exc
            raise
        comments.extend(result.get("comments", []))
        if not result.get("nextPageToken"):
            break
        params["pageToken"] = result["nextPageToken"]
    print(f"Document ID: {document_id}")
    print(f"Comments: {len(comments)}")
    for comment in comments:
        state = "resolved" if comment.get("resolved") else "open"
        author = comment.get("author", {}).get("displayName", "unknown")
        print(f"\n- [{state}] {author} · {comment.get('createdTime', '')} · id {comment.get('id', '')}")
        quoted = comment.get("quotedFileContent", {}).get("value")
        if quoted:
            print(f"  > {quoted}")
        print(f"  {comment.get('content', '')}")
    return 0


def command_comment(args):
    document_id = document_id_from(args)
    body = text_argument(args.body, args.body_file, "Comment")
    token = access_token()
    document = get_document(document_id, token)
    payload = build_comment_payload(document, args.tab_id, args.quote, body)
    print("Google Docs comment plan:")
    print(f"Document: {document.get('title', 'Untitled document')} ({document_id})")
    print(f"Revision read: {document.get('revisionId', '<missing>')}")
    print("--- quoted text ---")
    print(args.quote if args.quote is not None else "<none: unquoted comment>")
    print("--- comment ---")
    print(body)
    print("--- end plan ---")
    print("NOTE: Google Docs shows API comments with the quote but does not highlight it in the text.")
    if not args.execute:
        print("DRY RUN: no comment was posted. Re-run with --execute after approval.")
        return 0

    if args.quote is not None:
        live_document = get_document(document_id, token)
        payload = build_comment_payload(live_document, args.tab_id, args.quote, body)
    url = f"{DRIVE_FILES_API}/{urllib.parse.quote(document_id)}/comments?fields={urllib.parse.quote(COMMENT_FIELDS)}"
    try:
        result = api_json("POST", url, token, payload)
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 403" in message or "PERMISSION_DENIED" in message or "insufficient" in message.lower():
            raise RuntimeError(comment_scope_hint(message)) from exc
        raise
    if not result.get("id"):
        raise RuntimeError("Google did not return a comment id; the comment may not have been posted")
    print(f"Posted comment {result['id']} on document {document_id}")
    return 0


def image_tools():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("google_docs_images", Path(__file__).with_name("images.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command_images(args):
    return image_tools().command_images(args, globals())


def command_replace_images(args):
    return image_tools().command_replace(args, globals())


def build_parser():
    parser = argparse.ArgumentParser(description="Read Google Docs and perform one exact, revision-guarded replacement.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    read_parser = subparsers.add_parser("read", help="Render text and supplied reference labels; mark unavailable or unsupported content")
    read_parser.add_argument("--document-id")
    read_parser.add_argument("--tab-id", action="append", default=[])
    read_parser.add_argument("--show-links", action="store_true", help="List supplied URLs, emails and internal reference IDs per tab; never fetch linked resources")
    read_parser.set_defaults(func=command_read)

    replace_parser = subparsers.add_parser("replace-once", help="Replace one exact text occurrence; dry-run by default")
    replace_parser.add_argument("--document-id")
    old_group = replace_parser.add_mutually_exclusive_group(required=True)
    old_group.add_argument("--old")
    old_group.add_argument("--old-file")
    new_group = replace_parser.add_mutually_exclusive_group(required=True)
    new_group.add_argument("--new")
    new_group.add_argument("--new-file")
    replace_parser.add_argument("--tab-id", action="append", default=[])
    replace_parser.add_argument(
        "--link",
        action="append",
        default=[],
        metavar="TEXT=URL",
        help="Embed a link on uniquely occurring visible text in the replacement; repeatable",
    )
    replace_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Treat the replacement as Markdown (headings, bullets, nested bullets, bold, italic, links) and format it in place",
    )
    replace_parser.add_argument("--execute", action="store_true")
    replace_parser.add_argument("--suggest", action="store_true", help="Propose a pending tracked single-paragraph plain-text replacement; verify suggestion IDs and preserved original")
    replace_parser.set_defaults(func=command_replace_once)

    setbody_parser = subparsers.add_parser("set-body", help="Replace the document body in place with formatted content from markdown; dry-run by default")
    setbody_parser.add_argument("--document-id")
    body_group = setbody_parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--file", help="Path to a markdown source file")
    body_group.add_argument("--new", help="Inline markdown body")
    setbody_parser.add_argument("--tab-id", action="append", default=[])
    setbody_parser.add_argument("--execute", action="store_true")
    setbody_parser.set_defaults(func=command_set_body)

    comments_parser = subparsers.add_parser("comments", help="List the document's comments")
    comments_parser.add_argument("--document-id")
    comments_parser.set_defaults(func=command_comments)

    comment_parser = subparsers.add_parser("comment", help="Add one comment, optionally quoting uniquely occurring text; dry-run by default")
    comment_parser.add_argument("--document-id")
    comment_parser.add_argument("--quote", help="Exact document text the comment refers to; must occur once")
    comment_group = comment_parser.add_mutually_exclusive_group(required=True)
    comment_group.add_argument("--body")
    comment_group.add_argument("--body-file")
    comment_parser.add_argument("--tab-id", action="append", default=[])
    comment_parser.add_argument("--execute", action="store_true")
    comment_parser.set_defaults(func=command_comment)
    images_parser = subparsers.add_parser("images", help="Inspect existing inline images without printing signed content URIs")
    images_parser.add_argument("--document-id")
    images_parser.add_argument("--json", action="store_true")
    images_parser.add_argument("--out-dir", help="Save image bytes in a new/noncolliding local directory")
    images_parser.set_defaults(func=command_images)

    repair_parser = subparsers.add_parser("replace-images", help="Reinsert explicit inline images from local files; private import and revision/fingerprint guards")
    repair_parser.add_argument("--document-id")
    repair_parser.add_argument("--plan", required=True, help="JSON array of object_id, optional tab_id, image_file and width_pt")
    repair_parser.add_argument("--temporary-folder", required=True, help="Explicit writable Drive folder for the operation's private temporary import")
    repair_parser.add_argument("--expect", help="Exact preview fingerprint, required to execute")
    repair_parser.add_argument("--record", help="New private operation record path, required to execute")
    repair_parser.add_argument("--execute", action="store_true")
    repair_parser.set_defaults(func=command_replace_images)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
