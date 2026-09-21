import base64
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from export_session import export_har
from main import ClaimError, Session, digest


def entry(path, method, body, headers=None, encoded=False):
    text = json.dumps(body)
    content = {"text": base64.b64encode(text.encode()).decode() if encoded else text}
    if encoded:
        content["encoding"] = "base64"
    return {
        "request": {"url": "https://us.nkrpg.com/api/" + path, "method": method,
                    "headers": [{"name": k, "value": v} for k, v in (headers or {}).items()]},
        "response": {"content": content},
    }


class HarImportTests(unittest.TestCase):
    def entries(self, token="a" * 40):
        login = entry("auth/login/user", "POST", {
            "success": True, "response": {"user_id": "TEST1", "token": token}}, encoded=True)
        api = entry("sexual_dating/settings?version=0", "GET", {"success": True}, {
            "X-QOOKIA-USER": "TEST1", "X-QOOKIA-DIGEST": digest("GET", token),
            "X-QOOKIA-NKID": "123", "X-QOOKIA-DEVICE": "test-device",
            "X-QOOKIA-SERVER-PREFIX": "TEST", "X-QOOKIA-BUILD": "29.0.0.867",
        })
        return [login, api]

    def test_imports_latest_matching_session_without_printing_token(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "game.har"
            output = root / "session.json"
            source.write_text(json.dumps({"log": {"entries": self.entries() + self.entries("b" * 40)}}))
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                export_har(source, output)
            self.assertEqual(Session.parse(output.read_text()).token, "b" * 40)
            self.assertNotIn("b" * 40, log.getvalue())
            with self.assertRaises(FileExistsError):
                export_har(source, output)

    def test_rejects_missing_login_and_mismatched_session(self):
        for entries in [self.entries()[1:], [self.entries()[0], self.entries("b" * 40)[1]]]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / "game.har"
                output = root / "session.json"
                source.write_text(json.dumps({"log": {"entries": entries}}))
                with self.assertRaises(ClaimError):
                    export_har(source, output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
