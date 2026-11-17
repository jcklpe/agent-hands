import copy
import unittest
from inspect_pptx import compare


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {"slide_size": {"cx": "100", "cy": "60"}, "shapes": {name: {"id": str(i), "text": name + " original", "geometry": {"off": {"x": "10", "y": str(i * 10)}}, "styles": ['{"b":"1"}']} for i, name in enumerate(["Title", "Description", "ALPHA", "BETA", "Preservation"])}}

    def test_expected_two_editor_texts_are_preserved(self):
        actual = copy.deepcopy(self.baseline)
        actual["shapes"]["ALPHA"]["text"] = "Agent edit"
        actual["shapes"]["BETA"]["text"] = "Browser edit"
        self.assertEqual(compare(self.baseline, actual, "Agent edit", "Browser edit"), [])

    def test_wrong_text_format_position_or_identity_is_detected(self):
        for field, value in [("text", "Mixed text"), ("styles", []), ("geometry", {}), ("id", "other")]:
            actual = copy.deepcopy(self.baseline)
            actual["shapes"]["Preservation"][field] = value
            with self.subTest(field=field):
                self.assertIn("Preservation." + field, compare(self.baseline, actual))


if __name__ == "__main__":
    unittest.main()
