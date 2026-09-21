"""Export a private session from successful capture files or a browser HAR."""

import argparse
import base64
import json
from pathlib import Path
import sys

from main import ClaimError, Session, digest


def export(login_file, request_file, output):
    login = json.loads(login_file.read_text(encoding="utf-8-sig"))
    capture = json.loads(request_file.read_text(encoding="utf-8-sig"))
    write_session(login, capture, output)


def write_session(login, capture, output):
    if login["request"]["url"].split("?")[0] != "https://us.nkrpg.com/api/auth/login/user":
        raise ClaimError("Select the real auth/login/user response capture.")
    if login["response_json"].get("success") is not True or capture["response_json"].get("success") is not True:
        raise ClaimError("Both captures must have successful server responses.")
    if not capture["request"]["url"].startswith("https://us.nkrpg.com/api/"):
        raise ClaimError("Select a successful real game API request capture.")
    user = login["response_json"]["response"]
    headers = {k.lower(): v for k, v in capture["request"]["headers"].items()}
    if headers["x-qookia-user"] != user["user_id"]:
        raise ClaimError("The two captures belong to different accounts.")
    values = {
        "user_id": user["user_id"], "token": user["token"],
        "nkid": headers["x-qookia-nkid"], "device_id": headers["x-qookia-device"],
        "server_prefix": headers["x-qookia-server-prefix"],
        "build_version": headers["x-qookia-build"], "channel": "Qookia",
    }
    session = Session.parse(json.dumps(values))
    if digest(capture["request"]["method"], session.token) != headers["x-qookia-digest"]:
        raise ClaimError("The request and login captures do not use the same session.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse silent replacement of a previously exported session.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(values, stream, indent=2)
    print("Private session exported. Put its JSON in the PJQT_SESSION Actions secret; do not commit it.")


def export_har(har_file, output):
    har = json.loads(har_file.read_text(encoding="utf-8-sig"))
    captures = []
    for entry in har["log"]["entries"]:
        request = entry["request"]
        if not request["url"].startswith("https://us.nkrpg.com/api/"):
            continue
        content = entry.get("response", {}).get("content", {})
        body = content.get("text", "")
        try:
            if content.get("encoding") == "base64":
                body = base64.b64decode(body, validate=True).decode("utf-8")
            result = json.loads(body)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(result, dict) or result.get("success") is not True:
            continue
        captures.append({
            "request": {
                "url": request["url"], "method": request["method"],
                "headers": {h["name"].lower(): h["value"] for h in request.get("headers", [])},
            },
            "response_json": result,
        })
    logins = [c for c in captures
              if c["request"]["method"] == "POST"
              and c["request"]["url"].split("?")[0] == "https://us.nkrpg.com/api/auth/login/user"]
    if not logins:
        raise ClaimError("HAR has no successful game login response. Enable Network capture before reloading the game, then export HAR with response content.")
    login = logins[-1]
    user = login["response_json"]["response"]
    for capture in reversed(captures):
        headers = capture["request"]["headers"]
        if (headers.get("x-qookia-user") == user["user_id"]
                and digest(capture["request"]["method"], user["token"]) == headers.get("x-qookia-digest")):
            write_session(login, capture, output)
            return
    raise ClaimError("HAR has no successful authenticated API request matching the latest login. Wait for the game to load, then export again.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("login_capture", type=Path, help="Login capture JSON, or one browser HAR file.")
    parser.add_argument("request_capture", type=Path, nargs="?", help="Authenticated API capture JSON; omit when importing HAR.")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / ".private" / "session.json")
    args = parser.parse_args()
    try:
        if args.request_capture:
            export(args.login_capture, args.request_capture, args.output)
        else:
            export_har(args.login_capture, args.output)
    except ClaimError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print("ERROR: invalid capture, unreadable file, or output already exists.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
