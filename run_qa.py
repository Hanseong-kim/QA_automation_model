"""run_qa.py -- Device test entry script

Usage:
  python run_qa.py settings           # Settings app entry check
  python run_qa.py search <keyword>   # Settings entry + search
  python run_qa.py ocr [top]          # Current screen OCR text dump
  python run_qa.py check3             # Step 3: Screen timeout = 5min (legacy)
  python run_qa.py check <id> [id...] # Run QA check(s) by id (쉼표 허용: qa1 qa4, qa7)
  python run_qa.py check              # Run all QA checks
  python run_qa.py list               # List all QA item ids
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.esp import init as init_esp, close as close_esp
from lib.vision import init_camera
from lib.config import STREAM_URL
import time
from lib.qa import open_settings, settings_search, read_screen_text, ROI_TOP_HALF


def cmd_settings():
    print("[settings] open_settings()...")
    ok = open_settings()
    print(f"[settings] result: {'OK' if ok else 'FAIL -- Settings screen not confirmed'}")
    return 0 if ok else 1


def cmd_search(keyword: str):
    print(f"[search] open_settings()...")
    ok = open_settings()
    if not ok:
        print("[search] Settings entry failed -- abort")
        return 1
    print(f"[search] settings_search('{keyword}')...")
    found = settings_search(keyword)
    print(f"[search] '{keyword}' {'found on screen' if found else 'not found'}")
    return 0 if found else 1


def cmd_ocr(mode=""):
    roi = ROI_TOP_HALF if mode == "top" else None
    label = "top half (ROI_TOP_HALF)" if mode == "top" else "full frame"
    print(f"[ocr] reading screen text -- {label} (flush=15)...")
    t0 = time.time()
    results = read_screen_text(flush=15, roi=roi)
    elapsed = time.time() - t0
    print(f"[ocr] elapsed: {elapsed:.2f}s | ROI: {label}")
    if not results:
        print("[ocr] no text or frame capture failed")
        return 1
    print(f"[ocr] {len(results)} texts detected:\n")
    for text, conf, (cx, cy) in sorted(results, key=lambda x: x[2][1]):
        print(f"  conf={conf:.2f}  center=({cx:4d},{cy:4d})  '{text}'")
    return 0


def cmd_check3():
    from qa_checks import step_03_screen_timeout
    print("[check3] step_03_screen_timeout()...")
    name, status, detail, path = step_03_screen_timeout()
    print(f"[check3] {status} -- {detail}")
    if path:
        print(f"[check3] capture: {path}")
    return 0 if status == "PASS" else 1


def cmd_check(*item_ids):
    import re
    from qa_checks import run_sequence, QA_ITEMS, _QA_BY_ID

    # 쉼표/공백 혼용 허용: "qa1 qa4, qa7" → ["qa1","qa4","qa7"]
    item_ids = [t for t in re.split(r"[,\s]+", " ".join(item_ids)) if t]

    # No ids = run all
    if not item_ids:
        item_ids = [item["id"] for item in QA_ITEMS]

    # Validate
    for iid in item_ids:
        if iid not in _QA_BY_ID:
            print(f"ERROR: unknown item id '{iid}'")
            print(f"Available: {', '.join(_QA_BY_ID.keys())}")
            return 1

    # run_sequence가 진입 모드(full/between/reuse)를 자동 결정
    results = run_sequence(list(item_ids))

    print("\n=== Results summary ===")
    fail = 0
    for name, status, detail, _ in results:
        mark = "v" if status == "PASS" else ("?" if status == "UNKNOWN" else "x")
        print(f"  {mark} [{status}] {name}")
        if status != "PASS":
            fail += 1
    return 1 if fail else 0


def cmd_between(n="1"):
    """qa between 단독 실행 (back×n → UP → remove). 검색창 복귀 시퀀스 점검용."""
    from qa_checks import qa_between
    try:
        exit_back = int(n)
    except ValueError:
        exit_back = 1
    print(f"[between] qa_between(exit_back={exit_back})...")
    qa_between(exit_back)
    return 0


def cmd_list():
    from qa_checks import QA_ITEMS
    print("QA item ids:")
    for item in QA_ITEMS:
        nav_status = "verified" if item["nav"] else "TODO"
        if item.get("checks"):
            det = f"{len(item['checks'])}x{item['checks'][0]['detector']}"
        else:
            det = item["detector"]
        print(f"  {item['id']:6s}  [{det:8s}]  {item['name']:<50s}  nav: {nav_status}")
    return 0


COMMANDS = {
    "settings": (cmd_settings, 0, "Settings app entry check"),
    "search":   (cmd_search,   1, "Settings entry + keyword search"),
    "ocr":      (cmd_ocr,      0, "Current screen OCR text dump"),
    "check3":   (cmd_check3,   0, "Step 3: Screen timeout = 5min (legacy)"),
    "check":    (cmd_check,   -1, "Run QA check(s) by item id (no args = all)"),
    "between":  (cmd_between,  0, "qa between (back×n → UP → remove); optional n"),
    "list":     (cmd_list,     0, "List all QA item ids"),
}


def usage():
    print("Usage:")
    for cmd, (_, nargs, desc) in COMMANDS.items():
        if nargs > 0:
            arg = " <keyword>"
        elif nargs < 0:
            arg = " [id...]"
        else:
            arg = ""
        extra = " [top]" if cmd == "ocr" else ""
        print(f"  python run_qa.py {cmd}{arg}{extra}  -- {desc}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        usage()
        sys.exit(1)

    cmd = args[0]
    fn, nargs, _ = COMMANDS[cmd]

    # For check command: pass remaining args as item ids (variadic)
    if cmd == "check":
        extra = args[1:]
    elif cmd == "list":
        extra = []
    else:
        if nargs > 0 and len(args) - 1 < nargs:
            print(f"Error: '{cmd}' requires {nargs} argument(s)")
            usage()
            sys.exit(1)
        if cmd in ("ocr", "between"):   # optional single arg
            extra = args[1:2]
        else:
            extra = args[1:1 + nargs]

    print(f"=== run_qa: {cmd} ===")

    # list command doesn't need hardware init
    if cmd == "list":
        sys.exit(fn(*extra))

    print("Initializing (ESP + camera)...")
    init_esp()
    init_camera(STREAM_URL)
    print("Init complete\n")

    exit_code = 1
    try:
        exit_code = fn(*extra)
    finally:
        print("\nCleanup...")
        close_esp()
        print("Done")

    sys.exit(exit_code)
