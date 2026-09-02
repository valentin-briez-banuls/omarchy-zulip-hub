import unittest

import json

from zulip_hub.limits import (
    MAX_COLLECTION,
    MAX_DEPTH,
    MAX_PAYLOAD_BYTES,
    MAX_TEXT,
    bounded_list,
    bounded_text,
    clamped_number,
    encoded_response,
    exceeds_depth,
)


class ResponseTests(unittest.TestCase):
    """Ce qui part vers l’interface doit tenir un budget, quoi qu’il contienne."""

    def test_an_ordinary_response_is_encoded_as_is(self):
        line = encoded_response({"ok": True, "valeur": "bonjour"})
        self.assertEqual(json.loads(line), {"ok": True, "valeur": "bonjour"})
        self.assertTrue(line.endswith("\n"))

    def test_an_oversized_response_is_replaced_by_an_error(self):
        line = encoded_response({"ok": True, "corps": "X" * (MAX_PAYLOAD_BYTES * 2)})
        answer = json.loads(line)
        self.assertFalse(answer["ok"])
        self.assertLessEqual(len(line.encode("utf-8")), MAX_PAYLOAD_BYTES)


class DepthTests(unittest.TestCase):
    """Une charge peu volumineuse peut être arbitrairement imbriquée : la
    borne en octets ne dit rien de la profondeur, et l’analyseur JSON entre
    en récursion."""

    def test_an_ordinary_payload_passes(self):
        self.assertFalse(exceeds_depth(b'{"a": [1, 2, {"b": []}]}'))

    def test_a_deeply_nested_payload_is_detected(self):
        self.assertTrue(exceeds_depth(b"[" * (MAX_DEPTH + 5) + b"]" * (MAX_DEPTH + 5)))

    def test_brackets_inside_strings_do_not_count(self):
        self.assertFalse(exceeds_depth(b'{"a": "[[[[[[[[[[[[[[[[[[[[[[[["}'))

    def test_an_escaped_quote_does_not_end_the_string(self):
        self.assertFalse(exceeds_depth(b'{"a": "\\\"[[[[[[[[[[[[[[[[[[[[[[["}'))

    def test_the_depth_limit_stays_modest(self):
        self.assertLessEqual(MAX_DEPTH, 128)


class LimitTests(unittest.TestCase):
    def test_text_from_the_server_is_truncated_and_coerced(self):
        self.assertEqual(bounded_text("bonjour"), "bonjour")
        self.assertEqual(bounded_text(None), "")
        self.assertEqual(bounded_text(12345), "12345")
        self.assertEqual(len(bounded_text("x" * (MAX_TEXT * 2))), MAX_TEXT)

    def test_text_can_take_a_tighter_limit(self):
        self.assertEqual(bounded_text("abcdef", 3), "abc")

    def test_a_list_from_the_server_is_truncated_and_coerced(self):
        self.assertEqual(bounded_list([1, 2, 3]), [1, 2, 3])
        self.assertEqual(bounded_list("pas une liste"), [])
        self.assertEqual(bounded_list(None), [])
        self.assertEqual(len(bounded_list(list(range(MAX_COLLECTION * 2)))), MAX_COLLECTION)

    def test_a_number_from_the_server_is_clamped_and_never_infinite(self):
        self.assertEqual(clamped_number(50, default=10, minimum=1, maximum=100), 50)
        self.assertEqual(clamped_number(500, default=10, minimum=1, maximum=100), 100)
        self.assertEqual(clamped_number(0, default=10, minimum=1, maximum=100), 1)

    def test_a_number_that_is_not_one_falls_back_to_the_default(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, "12", None, [1]):
            with self.subTest(value=value):
                self.assertEqual(
                    clamped_number(value, default=10, minimum=1, maximum=100), 10,
                )


if __name__ == "__main__":
    unittest.main()
