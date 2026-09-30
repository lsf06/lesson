"""Quick unit test for local NLP parser."""
import sys
sys.path.insert(0, r'd:\lesson\xiaolin\lesson-main (1)\lesson-main\week4_nlp_agent\server')
from app import _local_nlp_parse

tests = [
    ("查看 group01_esp32s3eye 的最新数据", "tool_query_latest", "group01_esp32s3eye"),
    ("查一下那个东西", "", "", True),         # ambiguous
    ("帮 group01_esp32s3eye 重新采集一次", "tool_request_collection", "group01_esp32s3eye"),
    ("查一下 group99_fake 的数据", "", "", False, True),  # rejected
    ("帮我测一下", "tool_request_collection", "group01_esp32s3eye"),
    ("今天天气不错", "", "", True),           # ambiguous (no intent)
    ("上一条记录是什么", "tool_query_latest", "group01_esp32s3eye"),
    ("测一下", "tool_request_collection", "group01_esp32s3eye"),
    ("查一下那个东西", "", "", True),
]

all_ok = True
for t in tests:
    text = t[0]
    exp_intent = t[1] if len(t) > 1 else ""
    exp_dev = t[2] if len(t) > 2 else ""
    exp_amb = t[3] if len(t) > 3 else False
    exp_rej = t[4] if len(t) > 4 else False
    r = _local_nlp_parse(text)
    ok = True
    if r.get("intent") != exp_intent:
        ok = False
    if r.get("device_id") != exp_dev:
        ok = False
    if r.get("ambiguous", False) != exp_amb:
        ok = False
    if r.get("rejected", False) != exp_rej:
        ok = False
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f'[{status}] "{text[:40]}" -> intent={r.get("intent")} dev={r.get("device_id")} amb={r.get("ambiguous")} rej={r.get("rejected")}')

if all_ok:
    print("\nALL TESTS PASSED ✅")
else:
    print("\nSOME TESTS FAILED ❌")