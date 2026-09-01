import unittest

from zulip_hub.links import LinkError, encode_hash_component, message_url, summary_url


class LinkTests(unittest.TestCase):
    def test_zulip_hash_encoding_matches_canonical_format(self):
        self.assertEqual(encode_hash_component("Release 2.0 (final)"), "Release.202.2E0.20.28final.29")

    def test_stream_message_url(self):
        url = message_url("https://chat.example.com", {
            "id": 214,
            "type": "stream",
            "stream_id": 9,
            "display_recipient": "Zulip updates",
            "subject": "Release 2.0",
        })
        self.assertEqual(
            url,
            "https://chat.example.com/#narrow/channel/9-Zulip-updates/topic/Release.202.2E0/near/214",
        )

    def test_direct_message_url(self):
        url = message_url("https://chat.example.com", {
            "id": 99, "type": "private",
            "display_recipient": [{"id": 23}, {"id": 9}, {"id": 13}],
        })
        self.assertEqual(url, "https://chat.example.com/#narrow/dm/9,13,23-group/near/99")

    def test_summary_url(self):
        self.assertEqual(
            summary_url("https://chat.example.com", {
                "id": 8, "type": "private", "recipient_ids": [5, 2]
            }),
            "https://chat.example.com/#narrow/dm/2,5/near/8",
        )

    def test_rejects_non_https_site(self):
        with self.assertRaises(LinkError):
            message_url("http://chat.example.com", {"id": 1, "type": "private", "display_recipient": [{"id": 2}]})

