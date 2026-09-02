import base64
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

from urllib.request import Request

from zulip_hub.api import SameOriginRedirect, ZulipAPIError, ZulipClient


class RedirectTests(unittest.TestCase):
    """urllib recopie les en-tetes vers la cible d une redirection en ne
    retirant que content-length et content-type. Sans garde, la cle API part
    donc vers l hote choisi par le serveur."""

    def setUp(self):
        self.handler = SameOriginRedirect()
        self.request = Request(
            "https://chat.example.com/api/v1/users/me",
            headers={"Authorization": "Basic c2VjcmV0"},
        )

    def _redirect(self, target):
        return self.handler.redirect_request(
            self.request, BytesIO(b""), 302, "Found", {}, target,
        )

    def test_a_redirect_to_another_host_is_refused(self):
        with self.assertRaises(HTTPError):
            self._redirect("https://evil.example/collect")

    def test_a_redirect_to_another_port_is_refused(self):
        with self.assertRaises(HTTPError):
            self._redirect("https://chat.example.com:8443/api/v1/users/me")

    def test_a_downgrade_to_plain_http_is_refused(self):
        with self.assertRaises(HTTPError):
            self._redirect("http://chat.example.com/api/v1/users/me")

    def test_a_redirect_within_the_same_origin_is_followed(self):
        followed = self._redirect("https://chat.example.com/api/v1/users/me/")
        self.assertIsNotNone(followed)
        self.assertEqual(followed.full_url, "https://chat.example.com/api/v1/users/me/")


class SiteTests(unittest.TestCase):
    def test_a_plain_http_server_is_refused(self):
        with self.assertRaises(ZulipAPIError):
            ZulipClient("http://chat.example.com", "me@example.com", "top-secret")

    def test_credentials_embedded_in_the_address_are_refused(self):
        with self.assertRaises(ZulipAPIError):
            ZulipClient("https://user:pass@chat.example.com", "me@example.com", "k")

    def test_the_address_is_canonicalised_before_the_credential_is_built(self):
        client = ZulipClient("https://Chat.Example.COM:443/", "me@example.com", "k")
        self.assertEqual(client.site, "https://chat.example.com")


class APITests(unittest.TestCase):
    def test_an_oversized_response_is_refused_before_being_parsed(self):
        from zulip_hub.limits import MAX_RESPONSE_BYTES
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_opener") as opener:
            reader = opener.open.return_value.__enter__.return_value
            reader.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
            with self.assertRaisesRegex(ZulipAPIError, "volumineuse"):
                client.test_connection()

    def test_an_oversized_error_body_is_refused(self):
        from zulip_hub.limits import MAX_RESPONSE_BYTES
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        refusal = HTTPError(
            "https://chat.example.com/api/v1/users/me", 500, "Server Error",
            {}, BytesIO(b"x" * (MAX_RESPONSE_BYTES + 1)),
        )
        with patch.object(client, "_opener") as opener:
            opener.open.side_effect = refusal
            with self.assertRaises(ZulipAPIError):
                client.test_connection()

    def test_requests_never_use_the_process_wide_opener(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_opener") as opener:
            opener.open.return_value.__enter__.return_value.read.return_value = b"{}"
            client.test_connection()
        opener.open.assert_called_once()

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
        with patch.object(client, "_opener") as opener:
            opener.open.side_effect = refusal
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
        with patch.object(client, "_opener") as opener:
            opener.open.side_effect = refusal
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
        with patch.object(client, "_opener") as opener:
            response = opener.open.return_value.__enter__.return_value
            response.read.return_value = b'{"result":"success","queue_id":"q"}'
            client.register()
        request = opener.open.call_args.args[0]
        parameters = parse_qs(request.data.decode())
        self.assertEqual(parameters["apply_markdown"], ["false"])

    def test_users_returns_only_member_objects(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"members": [{"user_id": 7}, "bad"]}) as request:
            result = client.users()
        request.assert_called_once_with("GET", "users", {"client_gravatar": True})
        self.assertEqual(result, [{"user_id": 7}])

    def test_fetching_one_message_asks_for_unrendered_content(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        payload = {"message": {"id": 42, "content": "Bonjour **équipe**"}}
        with patch.object(client, "_request", return_value=payload) as request:
            result = client.message(42)
        request.assert_called_once_with("GET", "messages/42", {"apply_markdown": False})
        self.assertEqual(result["content"], "Bonjour **équipe**")

    def test_fetching_one_message_accepts_the_older_raw_content_shape(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"raw_content": "Bonjour"}):
            result = client.message(42)
        self.assertEqual(result, {"id": 42, "content": "Bonjour"})

    def test_a_message_response_without_content_is_refused(self):
        client = ZulipClient("https://chat.example.com", "me@example.com", "top-secret")
        with patch.object(client, "_request", return_value={"message": {"id": 42}}):
            with self.assertRaises(ZulipAPIError):
                client.message(42)

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
