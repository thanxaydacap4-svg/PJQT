import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Client, ClaimError, Session, collect, earned_cycles, main, rewards_from


SESSION_DATA = {
    "user_id": "TEST1", "token": "a" * 40, "nkid": "123",
    "device_id": "test-device", "server_prefix": "TEST", "build_version": "29.0.0.867",
}
SESSION = Session.parse(json.dumps(SESSION_DATA))
NOW = 1_800_000_000


class FakeClient:
    session = SESSION

    def __init__(self, age=6600):
        self.calls = []
        self.record = {"user_id": "TEST1", "event_id": 11, "tier": 1, "last_claim_time": NOW - age}
        self.setting = {"event_id": 11, "tier": 1, "duration": 600, "max_explore_limit": 7200,
                        "reward_list": [{"asset_id": "4002251", "value": "4"}], "active": 1}
        self.event = {"event_id": "11", "active": "1"}
        self.claim_error = None

    def request(self, method, path, event_id=None):
        self.calls.append((method, path, event_id))
        if path.endswith("settings?version=0"):
            return {"sexual_dating_settings": [self.event], "explore_item_settings": [self.setting]}, NOW
        if path.endswith("/records"):
            return {"user_explore_item_record": self.record}, NOW
        if self.claim_error:
            raise self.claim_error
        return {"user_explore_item_record": dict(self.record, last_claim_time=NOW),
                "reward_list": [{"asset_id": "4002251", "value": "44"}]}, NOW


class CollectorTests(unittest.TestCase):
    def run_collect(self, client, claim=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            collect(client, 11, claim)
        return output.getvalue()

    def test_read_only_default(self):
        client = FakeClient()
        self.assertIn("DRY RUN", self.run_collect(client))
        self.assertEqual(len(client.calls), 2)

    def test_claim_once_with_event_id(self):
        client = FakeClient()
        self.assertIn("quantity 44", self.run_collect(client, True))
        self.assertEqual(client.calls[-1], ("POST", "sexual_dating/claimItemExplore", 11))
        self.assertEqual(len(client.calls), 3)

    def test_below_one_cycle_does_not_claim(self):
        client = FakeClient(age=599)
        self.assertIn("nothing has accrued", self.run_collect(client, True))
        self.assertEqual(len(client.calls), 2)

    def test_capacity_and_clock_boundaries(self):
        client = FakeClient(age=20_000)
        self.assertEqual(earned_cycles(client.record, client.setting, NOW), 12)
        client.record["last_claim_time"] = NOW + 2
        self.assertEqual(earned_cycles(client.record, client.setting, NOW), 0)

    def test_inactive_event_does_not_claim(self):
        client = FakeClient()
        client.event["active"] = "0"
        self.assertIn("inactive", self.run_collect(client, True))
        self.assertEqual(len(client.calls), 1)

    def test_mismatched_account_or_event_stops(self):
        for key, value in [("user_id", "ANOTHER"), ("event_id", 8)]:
            client = FakeClient()
            client.record[key] = value
            with self.assertRaises(ClaimError):
                self.run_collect(client, True)
            self.assertEqual(len(client.calls), 2)

    def test_missing_tier_stops(self):
        client = FakeClient()
        client.record["tier"] = 4
        with self.assertRaises(ClaimError):
            self.run_collect(client, True)
        self.assertEqual(len(client.calls), 2)

    def test_ambiguous_mutation_not_retried(self):
        client = FakeClient()
        client.claim_error = ClaimError("Network failure")
        with self.assertRaises(ClaimError):
            self.run_collect(client, True)
        self.assertEqual(len(client.calls), 3)

    def test_invalid_rewards_fail_closed(self):
        for rewards in [[], [None], [{"asset_id": 1, "value": -5}], [{"asset_id": 1, "value": "secret"}]]:
            with self.assertRaises(ClaimError):
                rewards_from(rewards)

    def test_invalid_session_cannot_inject_headers(self):
        for raw in ["", "[]", "null", "{}", json.dumps(dict(SESSION_DATA, device_id="bad\r\nheader"))]:
            with self.assertRaises(ClaimError):
                Session.parse(raw)

    def test_missing_secret_returns_failure(self):
        with patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--event-id", "11"]), 1)

    def test_wire_body_and_auth_failure_are_sanitized(self):
        client = Client(SESSION)
        response = io.BytesIO(json.dumps({"success": False, "error_code": 11009, "reason": "PRIVATE_TOKEN"}).encode())
        with patch.object(client.opener, "open", return_value=response) as send:
            with self.assertRaises(ClaimError) as caught:
                client.request("POST", "sexual_dating/records", 11)
        request = send.call_args.args[0]
        self.assertEqual(request.data, b"event_id=11")
        self.assertEqual(request.method, "POST")
        self.assertIn("REQUIRE_LOGIN", str(caught.exception))
        self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))

    def test_network_failure_not_retried(self):
        client = Client(SESSION)
        with patch.object(client.opener, "open", side_effect=urllib.error.URLError("PRIVATE")) as send:
            with self.assertRaises(ClaimError) as caught:
                client.request("POST", "sexual_dating/claimItemExplore", 11)
        self.assertEqual(send.call_count, 1)
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_redirect_does_not_forward_credentials(self):
        from main import NoRedirect
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_out_of_scope_endpoint_rejected(self):
        with self.assertRaises(ClaimError):
            Client(SESSION).request("POST", "sexual_dating/upgradeExploreItemTier", 11)


if __name__ == "__main__":
    unittest.main()
