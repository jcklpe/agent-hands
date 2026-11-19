#!/usr/bin/env python3
"""Prepare safe Task chat HTML and compare visible content plus link destinations."""
import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit

ALLOWED = {'p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'a'}
BLOCKS = {'p', 'div', 'br', 'li', 'blockquote', 'pre'}
LINK = re.compile(r'\[([^\]\n]+)\]\(([^\s)]+)\)')

def safe_url(value):
    if any(ord(c) < 32 or c.isspace() for c in value):
        raise ValueError('Link destinations cannot contain whitespace or control characters')
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Links require an absolute HTTP(S) URL without credentials')
    return value

class SafeHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.stack = [], []
    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            raise ValueError(f'Unsupported HTML tag: {tag}')
        allowed_attrs = {'href'} if tag == 'a' else set()
        if any(k not in allowed_attrs for k, _ in attrs) or len({k for k, _ in attrs}) != len(attrs):
            raise ValueError(f'Unsupported or repeated attribute on {tag}')
        if tag == 'a':
            href = dict(attrs).get('href')
            if not href or 'a' in self.stack:
                raise ValueError('Anchors require href and cannot be nested')
            self.parts.append(f'<a href="{escape(safe_url(href), quote=True)}">')
        else:
            self.parts.append(f'<{tag}>')
        if tag != 'br':
            self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        if tag != 'br':
            raise ValueError('Only br may be self-closing')
        self.handle_starttag(tag, attrs)
    def handle_endtag(self, tag):
        if tag == 'br':
            return
        if not self.stack or self.stack.pop() != tag:
            raise ValueError('HTML tags must be balanced')
        self.parts.append(f'</{tag}>')
    def handle_data(self, data):
        self.parts.append(escape(data, quote=False))
    def handle_decl(self, decl):
        raise ValueError('HTML declarations are not supported')
    def handle_comment(self, data):
        raise ValueError('HTML comments are not supported')

def prepare(text, fmt='markdown'):
    text = text.strip()
    if not text or len(text) > 10000:
        raise ValueError('Comment must contain 1–10000 characters')
    if fmt == 'html':
        parser = SafeHTML(); parser.feed(text); parser.close()
        if parser.stack:
            raise ValueError('HTML tags must be balanced')
        content = ''.join(parser.parts)
    else:
        def inline(value):
            if fmt == 'plain':
                return escape(value, quote=False)
            parts, end = [], 0
            for match in LINK.finditer(value):
                parts.append(escape(value[end:match.start()], quote=False))
                parts.append(f'<a href="{escape(safe_url(match[2]), quote=True)}">{escape(match[1], quote=False)}</a>')
                end = match.end()
            parts.append(escape(value[end:], quote=False))
            return ''.join(parts)
        content = ''.join('<p>' + inline(p).replace('\n', '<br>') + '</p>' for p in re.split(r'\n\s*\n', text))
    if len(content) > 10000:
        raise ValueError('Serialized HTML exceeds 10000 characters')
    signature = fingerprint(content)
    if not signature['text']:
        raise ValueError('Comment must have visible content')
    return {'content': content, 'fingerprint': signature, 'sha256': hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()}

class Signature(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.anchor = [], [], None
    def handle_starttag(self, tag, attrs):
        if tag in BLOCKS:
            self.text.append(' ')
        if tag == 'a':
            self.anchor = [dict(attrs).get('href', ''), []]
    def handle_endtag(self, tag):
        if tag in BLOCKS:
            self.text.append(' ')
        if tag == 'a' and self.anchor is not None:
            self.links.append({'label': ' '.join(''.join(self.anchor[1]).split()), 'href': self.anchor[0]})
            self.anchor = None
    def handle_data(self, text):
        self.text.append(text)
        if self.anchor is not None:
            self.anchor[1].append(text)

def fingerprint(content):
    p = Signature(); p.feed(content); p.close()
    return {'text': ' '.join(''.join(p.text).split()), 'links': p.links}

def body(post):
    if 'content' in post:
        return fingerprint(post['content'])
    old = post.get('body') or {}
    if old.get('contentType', 'text').lower() == 'html':
        return fingerprint(old.get('content', ''))
    return {'text': ' '.join(old.get('content', '').split()), 'links': []}

def active(message):
    return not (message.get('deletedTime') or message.get('deletedDateTime'))

def task_url(task, tenant=''):
    link = f"https://planner.cloud.microsoft/ui/web/plan/{quote(task['planId'], safe='')}/view/board/task/{quote(task['id'], safe='')}"
    if re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', tenant):
        link += '?tid=' + quote(tenant, safe='')
    return link

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'match', 'render', 'validate', 'task-url', 'hash'])
    parser.add_argument('value', nargs='?')
    parser.add_argument('format', nargs='?', choices=['markdown', 'html', 'plain'], default='markdown')
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(Path(args.value).read_text(), args.format)))
        return
    data = json.load(sys.stdin)
    if args.command == 'task-url':
        print(task_url(data, args.value or ''))
        return
    posts = data['value']
    if args.command == 'hash':
        post = next(p for p in posts if p['id'] == args.value)
        print(hashlib.sha256(post['content'].encode()).hexdigest())
        return
    if args.command == 'validate':
        if not isinstance(posts, list) or any(not isinstance(p, dict) or not isinstance(p.get('id'), str) or p.get('parentEntityId') != args.value or not isinstance(p.get('content'), str) for p in posts):
            raise ValueError('Task chat messages must identify the exact parent task')
        print(json.dumps(data))
    elif args.command == 'match':
        wanted = prepare(Path(args.value).read_text(), args.format)['fingerprint']
        print(json.dumps([p['id'] for p in posts if active(p) and body(p) == wanted]))
    else:
        for post in posts:
            if not active(post):
                continue
            sig = body(post)
            print(f"- {post['id']} | {post.get('createdDateTime', '')}\n{sig['text']}")
            for link in sig['links']:
                print(f"  [{link['label']}]({link['href']})")

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc))
