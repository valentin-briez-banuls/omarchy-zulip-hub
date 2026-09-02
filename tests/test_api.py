import base64
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

from zulip_hub.api import ZulipAPIError, ZulipClient


class APITests(unittest.TestCase):
    def test_api_credentials_are_only_in_authorization_header(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        self.assertEqual(client.site, "https://chat.example.com")
        self.assertEqual(
            client.headers["Authorization"],
            "Basic " + base64.b64encode(b"me@example.com:top-secret").decode(),
        )

    def test_a_rate_limited_response_carries_the_delay_the_server_asked_for(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        body = b'{"result":"error","msg":"limite","code":"RATE_LIMIT_HIT","retry-after":12.5}'
        refusal = HTTPError(
            "https://chat.example.com/api/v1/events", 429, "Too Many Requests",
            {}, BytesIO(body),
        )
        with patch("zulip_hub.api.urlopen", side_effect=refusal):
            with self.assertRaises(ZulipAPIError) as raised:
                client.test_connection()
        self.assertEqual(raised.exception.code, "RATE_LIMIT_HIT")
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.retry_after, 12.5)

    def test_an_ordinary_failure_carries_no_retry_delay(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        refusal = HTTPError(
            "https://chat.example.com/api/v1/events", 400, "Bad Request",
            {}, BytesIO(b'{"result":"error","msg":"non","code":"BAD_REQUEST"}'),
        )
        with patch("zulip_hub.api.urlopen", side_effect=refusal):
            with self.assertRaises(ZulipAPIError) as raised:
                client.test_connection()
        self.assertIsNone(raised.exception.retry_after)

    def test_mark_read_uses_personal_message_flags_endpoint(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={}) as request:
            client.mark_read([42, 43])
        request.assert_called_once_with(
            "POST", "messages/flags",
            {"messages": [42, 43], "op": "add", "flag": "read"},
        )

    def test_registration_requests_followed_topic_state(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={}) as request:
            client.register()
        params = request.call_args.args[2]
        self.assertIn("user_topic", params["event_types"])
        self.assertIn("user_topic", params["fetch_event_types"])

    def test_connection_uses_authenticated_user_endpoint(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"email": "me@example.com"}) as request:
            result = client.test_connection()
        request.assert_called_once_with("GET", "users/me", {})
        self.assertEqual(result["email"], "me@example.com")

    def test_boolean_api_parameters_are_encoded_as_json(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch("zulip_hub.api.urlopen") as open_url:
            response = open_url.return_value.__enter__.return_value
            response.__iter__.return_value = iter([b'{"result":"success","queue_id":"q"}'])
            response.read.return_value = b'{"result":"success","queue_id":"q"}'
            client.register()
        request = open_url.call_args.args[0]
        parameters = parse_qs(request.data.decode())
        self.assertEqual(parameters["apply_markdown"], ["false"])

    def test_users_returns_only_member_objects(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"members": [{"user_id": 7}, "bad"]}) as request:
            result = client.users()
        request.assert_called_once_with("GET", "users", {"client_gravatar": True})
        self.assertEqual(result, [{"user_id": 7}])

    def test_send_direct_uses_user_ids_and_returns_message_id(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"id": 99}) as request:
            result = client.send_direct([7, 8], "Bonjour **équipe**")
        request.assert_called_once_with("POST", "messages", {
            "type": "direct", "to": [7, 8], "content": "Bonjour **équipe**",
        })
        self.assertEqual(result, 99)

    def test_send_direct_falls_back_only_when_modern_type_is_rejected(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        rejected = ZulipAPIError("Invalid message type direct", code="BAD_REQUEST", retryable=False)
        with patch.object(client, "_request", side_effect=[rejected, {"id": 100}]) as request:
            self.assertEqual(client.send_direct([7], "Bonjour"), 100)
        self.assertEqual(request.call_args_list[1].args[2]["type"], "private")

    def test_send_stream_targets_the_channel_by_id_and_topic(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"id": 77}) as request:
            result = client.send_stream(9, "deployment", "C’est reparti")
        request.assert_called_once_with("POST", "messages", {
            "type": "stream", "to": 9, "topic": "deployment", "content": "C’est reparti",
        })
        self.assertEqual(result, 77)

    def test_send_stream_falls_back_only_when_the_modern_topic_field_is_rejected(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        rejected = ZulipAPIError("Invalid parameter topic", code="BAD_REQUEST", retryable=False)
        with patch.object(client, "_request", side_effect=[rejected, {"id": 78}]) as request:
            self.assertEqual(client.send_stream(9, "deployment", "Bonjour"), 78)
        legacy = request.call_args_list[1].args[2]
        self.assertNotIn("topic", legacy)
        self.assertEqual(legacy["subject"], "deployment")

    def test_send_stream_does_not_retry_an_ambiguous_failure(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        failure = ZulipAPIError("serveur inaccessible", retryable=True)
        with patch.object(client, "_request", side_effect=failure) as request:
            with self.assertRaises(ZulipAPIError):
                client.send_stream(9, "deployment", "Bonjour")
        request.assert_called_once()

    def test_send_direct_does_not_retry_an_ambiguous_failure(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        failure = ZulipAPIError("serveur inaccessible", retryable=True)
        with patch.object(client, "_request", side_effect=failure) as request:
            with self.assertRaises(ZulipAPIError):
                client.send_direct([7], "Bonjour")
        request.assert_called_once()
