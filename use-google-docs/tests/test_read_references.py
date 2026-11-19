"""Synthetic fixtures follow Google's documented ParagraphElement and Link schemas."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("docs", Path(__file__).parents[1] / "scripts/docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def paragraph(parts, start=1):
    elements = []
    for part in parts:
        width = docs.utf16_length(part["textRun"].get("content", "")) if "textRun" in part else 1
        elements.append({"startIndex": start, "endIndex": start + width, **part})
        start += width
    return {"paragraph": {"elements": elements}}


def text(value, link=None):
    run = {"content": value}
    if link is not None:
        run["textStyle"] = {"link": link}
    return {"textRun": run}


def resource(title="Synthetic report", uri="https://example.com/report"):
    return {"richLink": {"richLinkProperties": {"title": title, "uri": uri}}}


def document(content):
    return {"title": "Synthetic document", "revisionId": "revision-one", "body": {"content": content}}


class ReferenceReads(unittest.TestCase):
    def read(self, value, *options):
        args = docs.build_parser().parse_args(["read", "--document-id", "synthetic-document", *options])
        original = copy.deepcopy(value)
        output = io.StringIO()
        with patch.object(docs, "access_token", return_value="synthetic-access"), patch.object(docs, "api_json", return_value=value) as api, contextlib.redirect_stdout(output):
            self.assertEqual(args.func(args), 0)
        api.assert_called_once()
        self.assertEqual(api.call_args.args[0], "GET")
        self.assertIn("includeTabsContent=true", api.call_args.args[1])
        self.assertIn("suggestionsViewMode=SUGGESTIONS_INLINE", api.call_args.args[1])
        self.assertEqual(value, original)
        return output.getvalue()

    def test_resources_people_and_plain_links_remain_in_order(self):
        value = document([paragraph([
            text("Read ", {"url": "https://example.com/plain"}), resource(), text(" with "),
            {"person": {"personProperties": {"name": "Example Person", "email": "person@example.com"}}}, text(".\n"),
        ])])
        rendered = self.read(value, "--show-links")
        self.assertIn("Read [link: Synthetic report] with [person: Example Person].\n", rendered)
        self.assertIn("Read  -> https://example.com/plain", rendered)
        self.assertIn("Synthetic report -> https://example.com/report", rendered)
        self.assertIn("Example Person -> email: person@example.com", rendered)
        self.assertLess(rendered.index("Read  ->"), rendered.index("Synthetic report ->"))
        self.assertLess(rendered.index("Synthetic report ->"), rendered.index("Example Person ->"))
        without_links = self.read(value)
        self.assertNotIn("https://", without_links)
        self.assertNotIn("person@example.com", without_links)

    def test_missing_targets_labels_unknown_elements_and_empty_text_are_distinct(self):
        value = document([paragraph([
            resource("Missing target", ""), resource("", "https://example.com/known"), {"richLink": {}},
            {"person": {"personProperties": {"email": "fallback@example.com"}}},
            {"person": {"personProperties": {"name": "Name only"}}},
            {"futureReference": {"secretUrl": "https://example.com/not-a-supported-target"}}, {}, text(""),
        ])])
        rendered = self.read(value, "--show-links")
        self.assertIn("[link: Missing target; target unavailable]", rendered)
        self.assertIn("label unavailable -> https://example.com/known", rendered)
        self.assertIn("[person: fallback@example.com]", rendered)
        self.assertIn("Name only -> <target unavailable>", rendered)
        self.assertIn("[unsupported element: futureReference][unavailable element]", rendered)
        self.assertNotIn("not-a-supported-target", rendered)
        self.assertEqual(docs.structural_read_view([paragraph([text("")])]), ("", []))

    def test_internal_references_are_ids_not_guessed_urls(self):
        value = document([paragraph([
            text("Heading", {"heading": {"id": "heading-one", "tabId": "tab-two"}}),
            text("Bookmark", {"bookmark": {"id": "bookmark-one", "tabId": "tab-two"}}),
            text("Tab", {"tabId": "tab-two"}), text("Legacy", {"headingId": "old-heading"}),
            text("Legacy bookmark", {"bookmarkId": "old-bookmark"}), text("Unknown", {}),
        ])])
        rendered = self.read(value, "--show-links")
        self.assertIn("Heading -> heading: heading-one; tab: tab-two", rendered)
        self.assertIn("Bookmark -> bookmark: bookmark-one; tab: tab-two", rendered)
        self.assertIn("Tab -> tab: tab-two", rendered)
        self.assertIn("Legacy -> heading: old-heading (legacy reference)", rendered)
        self.assertIn("Legacy bookmark -> bookmark: old-bookmark (legacy reference)", rendered)
        self.assertIn("Unknown -> <target unavailable>", rendered)
        self.assertNotIn("https://", rendered)

    def test_nested_tabs_tables_and_contents_keep_context(self):
        def tab(tab_id, content, children=()):
            return {"tabProperties": {"tabId": tab_id, "title": tab_id}, "documentTab": {"body": {"content": content}}, "childTabs": list(children)}
        table = {"table": {"tableRows": [{"tableCells": [{"content": [paragraph([text("Cell "), resource("Cell report")])]}]}]}}
        toc = {"tableOfContents": {"content": [paragraph([text("Contents "), resource("Contents report")])]}}
        value = {"tabs": [tab("parent", [paragraph([text("Parent only\n")])], [tab("child", [table, toc])]), tab("other", [paragraph([text("Other only\n")])])]}
        rendered = self.read(value, "--tab-id", "child", "--show-links")
        self.assertIn("## child [child]", rendered)
        self.assertIn("Cell [link: Cell report]Contents [link: Contents report]", rendered)
        self.assertNotIn("Parent only", rendered)
        self.assertNotIn("Other only", rendered)
        all_tabs = self.read(value)
        self.assertLess(all_tabs.index("Parent only"), all_tabs.index("Cell [link:"))
        self.assertLess(all_tabs.index("Cell [link:"), all_tabs.index("Other only"))
        with self.assertRaisesRegex(ValueError, "Unknown tab ID"):
            docs.document_read_tabs(value, ["missing"])

    def test_other_native_elements_are_visible_without_inventing_content(self):
        value = document([paragraph([
            {"dateElement": {"dateElementProperties": {"displayText": "Jan 2, 2030"}}},
            {"dropdown": {"dropdownProperties": {"displayValue": "In review"}}},
            {"dateElement": {}}, {"dropdown": {}},
            {"footnoteReference": {"footnoteId": "footnote-one", "footnoteNumber": "1"}},
            {"inlineObjectElement": {"inlineObjectId": "image-one"}}, {"equation": {}},
        ]), {"futureStructure": {}}])
        rendered = self.read(value, "--show-links")
        for expected in ("[date: Jan 2, 2030]", "[dropdown: In review]", "[date: label unavailable]", "[dropdown: label unavailable]", "[footnote 1; content not rendered]", "footnote 1 -> footnote: footnote-one", "[unsupported element: inlineObjectElement]", "[unsupported element: equation]", "[unsupported document structure]"):
            self.assertIn(expected, rendered)

    def test_display_labels_do_not_change_mutation_text_or_utf16_spans(self):
        value = document([paragraph([text("😀 left"), resource(), text("right\n")])])
        before = docs.document_tabs(value)
        self.read(value, "--show-links")
        self.assertEqual(docs.document_tabs(value), before)
        self.assertEqual(before[0]["text"], "😀 leftright\n")
        self.assertEqual(docs.count_matches(value, [], "Synthetic report"), 0)
        self.assertEqual(docs.exact_text_range(value, [], "right"), {"tab_id": "", "start_index": 9, "end_index": 14})

    def test_all_replacement_modes_refuse_crossing_a_native_element(self):
        value = document([paragraph([text("left"), resource(), text("right\n")])])
        for mode in ([], ["--markdown"], ["--suggest"]):
            args = docs.build_parser().parse_args(["replace-once", "--document-id", "synthetic", "--old", "leftright", "--new", "replacement", "--execute", *mode])
            with patch.object(docs, "access_token", return_value="synthetic-access"), patch.object(docs, "get_document", return_value=value), patch.object(docs, "api_json") as api:
                with self.assertRaisesRegex(ValueError, "native element or structural gap"):
                    args.func(args)
                api.assert_not_called()

    def test_contiguous_runs_preserve_ordinary_link_output_and_range(self):
        value = document([paragraph([text("first "), text("second", {"url": "https://example.com/plain"}), text("\n")])])
        rendered = self.read(value, "--show-links")
        self.assertIn("first second\n", rendered)
        self.assertIn("- second -> https://example.com/plain", rendered)
        self.assertEqual(docs.exact_text_range(value, [], "first second"), {"tab_id": "", "start_index": 1, "end_index": 13})


if __name__ == "__main__":
    unittest.main()
