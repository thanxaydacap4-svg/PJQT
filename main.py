import os
import sys
import time
import json
import re
import urllib.request
import urllib.error

CLAIM_URL = "https://us.nkrpg.com/api/sexual_dating/claimItemExplore"

def parse_raw_headers(raw_text: str) -> dict:
    headers = {}
    if not raw_text:
        return headers
    
    # Nếu copy dạng cURL
    if "curl" in raw_text.lower() or "-H" in raw_text:
        clean_text = raw_text.replace("^", "").replace("\\", "")
        matches = re.findall(r"-H\s+['\"]([^'\"]+)['\"]", clean_text)
        for m in matches:
            if ":" in m:
                k, v = m.split(":", 1)
                headers[k.strip()] = v.strip()
        if headers:
            return headers

    # Nếu copy raw text từ F12
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith(":") or line.startswith("HTTP/"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            headers[key.strip()] = val.strip()
    return headers

def send_claim_request(headers: dict):
    if not headers:
        print("[X] Lỗi: Chưa có headers! Vui lòng cấu hình Secret PJQT_HEADERS trên GitHub.")
        sys.exit(1)

    print(f"[*] Gửi request nhận Potion: {CLAIM_URL}")
    print(f"[*] User: {headers.get('x-qookia-user') or headers.get('X-QOOKIA-USER')}")
    
    req_headers = {str(k): str(v) for k, v in headers.items()}
    # Luôn làm mới timestamp hiện tại
    now_str = str(int(time.time()))
    if "x-qookia-time" in req_headers:
        req_headers["x-qookia-time"] = now_str
    elif "X-QOOKIA-TIME" in req_headers:
        req_headers["X-QOOKIA-TIME"] = now_str

    req = urllib.request.Request(CLAIM_URL, data=b"", headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                r = data.get("response", {})
                rewards = r.get("reward_list", [])
                machine = r.get("user_explore_item_record", {})
                print("\n==========================================")
                print("🎉 THÀNH CÔNG! ĐÃ NHẬN POTION")
                print("==========================================")
                for item in rewards:
                    print(f"  + Nhận được: +{item.get('value')} Potion (ID: {item.get('asset_id')})")
                print(f"  + Cấp máy: Tier {machine.get('tier')}")
                print(f"  + Event ID: {machine.get('event_id')}")
            else:
                print(f"[!] Server trả về: {data}")
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="ignore")
        print(f"[X] HTTP {err.code}: {err.reason}\nBody: {err_body}")
        sys.exit(1)
    except Exception as e:
        print(f"[X] Lỗi: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Đọc từ GitHub Secret thông qua biến môi trường
    raw = os.environ.get("PJQT_HEADERS", "")
    headers = parse_raw_headers(raw)
    send_claim_request(headers)
