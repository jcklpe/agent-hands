"""Synthetic, stateful Canvas responses with configurable paging, role and failures."""
import base64
import copy
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-canvas" / "scripts"))
import canvas_auth as auth
from canvas_read import Reader

TOKEN = "synthetic-canvas-token"
ORIGIN = "https://example.instructure.com"
IMAGE = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAALQAAAA8CAIAAABATAfQAAABQ0lEQVR4nO3SMU4DMRiE0ZyEGomOc3E4bhh6xCR/4c0Y631y6WJ3/G53KXRrf4D2DQ7F4FAMDsXgUAwOxeBQDA7F4FAMDsXgUCzi+Pj6/l/nlas9rj7FqungWF99CjjggAMOOODYcDo41lefAg444IADDjg2nA6OaW/vn8Ob9SngKOAY+qhPAUcHx8RHfQo4ajie+qhPAUcTx2Mf9SngKON44KM+BRx9HMlHfQo4nvzhn295xTlvOjgu9FGfAo6NcPzyUZ8Cjo1wHDYdHFfJOGC683EsbyjjpOngmDaUcdJ0cEwbyjhpOjimDWWcNB0c04YyTpoOjmlDGSdNB8e0oYz7QdPBsb76FHDAAQcccMCx4XRwrK8+BRxwwAEHHHBsOB0c66tPcTkOCQ7F4FAMDsXgUAwOxeBQDA7F4FAMDsXgUOwHtsaY6OJ4N2oAAAAASUVORK5CYII=")


class CanvasFixture:
    def __init__(self, page_size=100, reverse=False, staff=False):
        self.data = json.loads((Path(__file__).parent / "fixtures" / "course.json").read_text())
        self.page_size, self.reverse, self.staff = page_size, reverse, staff
        self.failures, self.sent, self.downloads = {}, [], []
        self.course_ids = ["123"]
        self.permissions = {"manage_assignments_edit": staff, "manage_wiki_update": staff, "post_to_forum": True}
        if staff:
            self.data["course"]["enrollments"][0]["type"] = "teacher"
            self.data["assignments"][0]["overrides"] = [{"id":"60","title":"Section B","due_at":"2026-11-01T07:30:00Z","course_section_id":"88"},{"id":"61","title":"Section C","due_at":"2026-11-02T07:30:00Z","course_section_id":"89"}]
        self.opener = None

    def client(self):
        with patch.dict(os.environ, {"CANVAS_TOKEN_EXAMPLE": TOKEN}):
            account = auth.Account("example", ORIGIN, "1001", "CANVAS_TOKEN_EXAMPLE", None, tuple(self.course_ids))
            return auth.Client(account, transport=self, sleep=lambda _: None)

    def reader(self, **options):
        reader = Reader(self.client(), **options)
        reader.identity()
        return reader

    def send(self, method, url, headers, body=None, token=None):
        assert method == "GET", "Slice 2 must never write to Canvas"
        assert token == TOKEN
        parts = urlsplit(url)
        assert parts.netloc == urlsplit(ORIGIN).netloc
        path, params = parts.path, parse_qs(parts.query)
        self.sent.append((path, params))
        fault = self.failures.get(path)
        if fault:
            if isinstance(fault, Exception):
                raise fault
            status, data = fault
        else:
            status, data = 200, self.route(path, params)
        data = copy.deepcopy(data)
        response_headers = {"content-type": "application/json"}
        if isinstance(data, list):
            if self.reverse:
                data.reverse()
            page = int(params.get("page", ["1"])[0])
            start = (page - 1) * self.page_size
            items = data[start:start + self.page_size]
            if start + self.page_size < len(data):
                params["page"] = [str(page + 1)]
                response_headers["link"] = f'<{ORIGIN}{path}?{urlencode(params, doseq=True)}>; rel="next"'
            data = items
        return auth.Response(status, response_headers, json.dumps(data).encode())

    def route(self, path, params):
        if path == "/api/v1/users/self":
            return {"id":"1001","name":"Example User"}
        if path == "/api/v1/users/self/profile":
            return {"time_zone":"America/New_York"}
        if path == "/api/v1/users/self/groups":
            return self.data["groups"]
        if path == "/api/v1/courses":
            return [dict(self.data["course"], id=cid) for cid in self.course_ids]
        if path == "/api/v1/calendar_events":
            assert params.get("all_events") == ["true"]
            assert len(params["context_codes[]"]) <= 10
            return [e for e in self.data["calendar_events"] if e["context_code"] in params["context_codes[]"]]
        bits = path.split("/")
        if len(bits) >= 5 and bits[3] in {"courses", "groups"}:
            context, cid = bits[3:5]
            tail = "/".join(bits[5:])
            if not tail:
                return dict(self.data["course"], id=cid)
            if tail == "permissions":
                return self.permissions
            if tail == "modules/10/items":
                return self.data["items"]
            if tail.startswith("pages/"):
                pid = tail.split("page_id:")[-1]
                return next(p for p in self.data["pages"] + self.data["group_pages"] if p["page_id"] == pid)
            if tail.startswith("files/"):
                return next(f for f in self.data["files"] if f["id"] == tail.split("/")[-1])
            if context == "groups":
                return self.data["group_pages"] if tail == "pages" else []
            if tail == "discussion_topics":
                return self.data["announcements"] if params.get("only_announcements") == ["true"] else self.data["discussions"]
            return self.data[tail]
        raise AssertionError("Unexpected endpoint: " + path)

    def download(self, client, metadata, output, **kwargs):
        self.downloads.append(metadata["id"])
        Path(output).write_bytes(IMAGE)
        return {"bytes": len(IMAGE), "sha256": hashlib.sha256(IMAGE).hexdigest()}


class FileResponse(io.BytesIO):
    def __init__(self, body=b"", status=200, headers=None):
        super().__init__(body)
        self.status, self.headers = status, headers or {}


class FileOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []

    def open(self, request, timeout):
        self.sent.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
