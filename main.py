"""Collect earned Explore rewards for one explicitly selected Project QT event."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://us.nkrpg.com/api/"
ALLOWED_REQUESTS = {
    ("GET", "sexual_dating/settings?version=0"),
    ("POST", "sexual_dating/records"),
    ("POST", "sexual_dating/claimItemExplore"),
}


class ClaimError(Exception):
    """An error whose message is safe to include in a public Actions log."""


def integer(value, name, minimum=0):
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ClaimError(f"Invalid {name}; stopped.")
    number = int(value)
    if number < minimum:
        raise ClaimError(f"Invalid {name}; stopped.")
    return number


@dataclass(repr=False, frozen=True)
class Session:
    user_id: str
    token: str
    nkid: str
    device_id: str
    server_prefix: str
    build_version: str
    channel: str = "Qookia"

    @classmethod
    def parse(cls, raw):
        try:
            values = json.loads(raw)
            fields = {key: values[key] for key in (
                "user_id", "token", "nkid", "device_id", "server_prefix", "build_version"
            )}
            fields["channel"] = values.get("channel", "Qookia")
        except (ValueError, TypeError, KeyError):
            raise ClaimError("Invalid PJQT_SESSION JSON; use export_session.py.") from None
        if any(not isinstance(v, str) or not v or not v.isascii()
               or any(ord(c) < 33 or ord(c) > 126 for c in v) for v in fields.values()):
            raise ClaimError("Invalid session fields; use export_session.py.")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", fields["token"]):
            raise ClaimError("Expected the login response token, not PACK or copied headers.")
        if not fields["user_id"].startswith(fields["server_prefix"]):
            raise ClaimError("Session account and server prefix do not match.")
        return cls(**fields)


def digest(method, token):
    return hashlib.sha1((method.lower() + "$" + token + "4087532952").encode("ascii")).hexdigest()


def pack(timestamp, build_version, channel="Qookia"):
    signature = hashlib.md5(b"WebGL").hexdigest()
    value = channel + build_version + str(timestamp) + signature + "4983iujkrfgdsv09gg43547837uej"
    return hashlib.sha1(value.encode("ascii")).hexdigest()


def signed_headers(session, method, timestamp):
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-QOOKIA-USER": session.user_id,
        "X-QOOKIA-NKID": session.nkid,
        "X-QOOKIA-DEVICE": session.device_id,
        "X-QOOKIA-DEVICE-TYPE": "web",
        "X-QOOKIA-SERVER-PREFIX": session.server_prefix,
        "X-QOOKIA-BUILD": session.build_version,
        "X-QOOKIA-TIME": str(timestamp),
        "X-QOOKIA-PACK": pack(timestamp, session.build_version, session.channel),
        "X-QOOKIA-DIGEST": digest(method, session.token),
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward account headers to a redirect destination.
        return None


class Client:
    def __init__(self, session):
        self.session = session
        self.clock_offset = 0
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, event_id=None):
        if (method, path) not in ALLOWED_REQUESTS:
            raise ClaimError("Request outside the Explore collector scope.")
        now = int(time.time()) + self.clock_offset
        payload = None
        if method == "POST":
            payload = urllib.parse.urlencode({"event_id": str(integer(event_id, "event_id", 1))}).encode("ascii")
        req = urllib.request.Request(
            API_ROOT + path, data=payload, method=method,
            headers=signed_headers(self.session, method, now),
        )
        try:
            with self.opener.open(req, timeout=25) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise ClaimError(f"HTTP {exc.code}; no automatic retry. Check the account before retrying a claim.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ClaimError("Network failure; result may be unknown. No automatic retry.") from None
        except (ValueError, UnicodeError):
            raise ClaimError("Invalid server response; no automatic retry.") from None
        if not isinstance(result, dict):
            raise ClaimError("Unexpected response format; stopped.")
        if result.get("success") is not True:
            code = integer(result.get("error_code", 0), "error_code")
            if code == 11009:
                raise ClaimError("REQUIRE_LOGIN (11009): refresh PJQT_SESSION from a new successful login.")
            raise ClaimError(f"API rejected the request (code {code}); stopped.")
        server_time = integer(result.get("server_time"), "server_time", 1)
        self.clock_offset = server_time - int(time.time())
        body = result.get("response")
        if not isinstance(body, dict):
            raise ClaimError("Unexpected response body; stopped.")
        return body, server_time


def machine_record(body, session, event_id):
    record = body.get("user_explore_item_record")
    if not isinstance(record, dict):
        raise ClaimError("Explore record unavailable; open this event in the game first.")
    if record.get("user_id") != session.user_id:
        raise ClaimError("Explore account mismatch; stopped.")
    if integer(record.get("event_id"), "record event_id", 1) != event_id:
        raise ClaimError("Explore event mismatch; stopped.")
    integer(record.get("tier"), "tier", 1)
    integer(record.get("last_claim_time"), "last_claim_time", 1)
    return record


def earned_cycles(record, setting, server_time):
    period = integer(setting.get("duration"), "duration", 1)
    capacity = integer(setting.get("max_explore_limit"), "max_explore_limit", period)
    last_claim = integer(record.get("last_claim_time"), "last_claim_time", 1)
    elapsed = max(0, min(server_time - last_claim, capacity))
    return elapsed // period


def rewards_from(value):
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        raise ClaimError("Reward data unavailable; stopped.")
    return [
        (integer(item.get("asset_id"), "reward asset_id", 1),
         integer(item.get("value"), "reward quantity", 1))
        for item in value
    ]


def collect(client, event_id, claim=False):
    settings, _ = client.request("GET", "sexual_dating/settings?version=0")
    events = settings.get("sexual_dating_settings")
    tiers = settings.get("explore_item_settings")
    if not isinstance(events, list) or not isinstance(tiers, list):
        raise ClaimError("Unexpected Explore settings schema; stopped.")
    matching = [e for e in events if isinstance(e, dict) and str(e.get("event_id")) == str(event_id)]
    if len(matching) != 1:
        raise ClaimError("Configured event is absent or ambiguous in current settings; stopped.")
    if str(matching[0].get("active")) != "1":
        print(f"SKIP: event {event_id} is inactive.")
        return
    body, server_time = client.request("POST", "sexual_dating/records", event_id)
    record = machine_record(body, client.session, event_id)
    selected = [s for s in tiers if isinstance(s, dict)
                and str(s.get("event_id")) == str(event_id)
                and str(s.get("tier")) == str(record["tier"])]
    if len(selected) != 1 or str(selected[0].get("active")) != "1":
        raise ClaimError("Current Explore tier setting unavailable; stopped.")
    cycles = earned_cycles(record, selected[0], server_time)
    rewards = rewards_from(selected[0].get("reward_list"))
    if not rewards:
        raise ClaimError("No valid Explore reward; stopped.")
    print(f"Event {event_id}; tier {record['tier']}; accrued cycles {cycles}.")
    if cycles == 0:
        print("SKIP: nothing has accrued yet.")
        return
    if not claim:
        print("DRY RUN: eligible to collect; no claim sent.")
        return
    result, _ = client.request("POST", "sexual_dating/claimItemExplore", event_id)
    updated = machine_record(result, client.session, event_id)
    if integer(updated["last_claim_time"], "last_claim_time", 1) <= integer(record["last_claim_time"], "last_claim_time", 1):
        raise ClaimError("Claim returned success but the timestamp did not advance; inspect in game before retrying.")
    rewards = rewards_from(result.get("reward_list"))
    if not rewards:
        raise ClaimError("Claim response has no rewards; inspect in game before retrying.")
    for asset_id, amount in rewards:
        print(f"COLLECTED: item {asset_id}, quantity {amount}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-file", type=Path, help="Local private JSON; Actions uses PJQT_SESSION.")
    parser.add_argument("--event-id", default=os.environ.get("PJQT_EVENT_ID"))
    parser.add_argument("--claim", action="store_true", help="Send one claim when eligible; default is read-only.")
    args = parser.parse_args(argv)
    try:
        raw = args.session_file.read_text(encoding="utf-8-sig") if args.session_file else os.environ.get("PJQT_SESSION", "")
        if not raw:
            raise ClaimError("Missing PJQT_SESSION. PJQT_HEADERS alone is insufficient.")
        session = Session.parse(raw)
        event_id = integer(args.event_id, "PJQT_EVENT_ID", 1)
        collect(Client(session), event_id, args.claim)
    except ClaimError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("ERROR: could not read the private session file.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
