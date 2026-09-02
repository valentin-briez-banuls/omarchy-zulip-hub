import unittest

from zulip_hub.limits import (
    MAX_COLLECTION,
    MAX_TEXT,
    bounded_list,
    bounded_text,
    clamped_number,
)


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
