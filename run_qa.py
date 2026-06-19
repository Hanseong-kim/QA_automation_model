"""run_qa.py — 실기기 테스트용 진입 스크립트

사용법:
  python run_qa.py settings           # Settings 앱 진입 확인
  python run_qa.py search <키워드>    # Settings 진입 후 검색
  python run_qa.py ocr                # 현재 화면 OCR 텍스트 전체 출력
  python run_qa.py check3             # Step 3: Screen timeout = 5분 확인
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.esp import init as init_esp, close as close_esp
from lib.vision import init_camera
from lib.config import STREAM_URL
import time
from lib.qa import open_settings, settings_search, read_screen_text, ROI_TOP_HALF


def cmd_settings():
    print("[settings] open_settings() 실행...")
    ok = open_settings()
    print(f"[settings] 결과: {'성공' if ok else '실패 — Settings 화면 확인 안 됨'}")
    return 0 if ok else 1


def cmd_search(keyword: str):
    print(f"[search] open_settings() 실행...")
    ok = open_settings()
    if not ok:
        print("[search] Settings 진입 실패 — 중단")
        return 1
    print(f"[search] settings_search('{keyword}') 실행...")
    found = settings_search(keyword)
    print(f"[search] '{keyword}' {'화면에서 발견됨' if found else '미발견'}")
    return 0 if found else 1


def cmd_ocr(mode=""):
    roi = ROI_TOP_HALF if mode == "top" else None
    label = "상단 절반 (ROI_TOP_HALF)" if mode == "top" else "전체 프레임"
    print(f"[ocr] 현재 화면 텍스트 읽는 중 — {label} (flush=15)...")
    t0 = time.time()
    results = read_screen_text(flush=15, roi=roi)
    elapsed = time.time() - t0
    print(f"[ocr] 소요: {elapsed:.2f}초 | ROI: {label}")
    if not results:
        print("[ocr] 텍스트 없음 또는 프레임 획득 실패")
        return 1
    print(f"[ocr] {len(results)}개 텍스트 검출:\n")
    for text, conf, (cx, cy) in sorted(results, key=lambda x: x[2][1]):
        print(f"  conf={conf:.2f}  center=({cx:4d},{cy:4d})  '{text}'")
    return 0


def cmd_check3():
    from qa_checks import step_03_screen_timeout
    print("[check3] step_03_screen_timeout() 실행...")
    name, status, detail, path = step_03_screen_timeout()
    print(f"[check3] {status} — {detail}")
    if path:
        print(f"[check3] 캡처: {path}")
    return 0 if status == "PASS" else 1


COMMANDS = {
    "settings": (cmd_settings, 0, "Settings 앱 진입 확인"),
    "search":   (cmd_search,   1, "Settings 진입 후 키워드 검색"),
    "ocr":      (cmd_ocr,      0, "현재 화면 OCR 텍스트 전체 출력"),
    "check3":   (cmd_check3,   0, "Step 3: Screen timeout = 5분 확인"),
}


def usage():
    print("사용법:")
    for cmd, (_, nargs, desc) in COMMANDS.items():
        arg = " <키워드>" if nargs else ""
        extra = " [top]" if cmd == "ocr" else ""
        print(f"  python run_qa.py {cmd}{arg}{extra}  — {desc}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        usage()
        sys.exit(1)

    cmd = args[0]
    fn, nargs, _ = COMMANDS[cmd]

    if len(args) - 1 < nargs:
        print(f"오류: '{cmd}'는 인자 {nargs}개 필요")
        usage()
        sys.exit(1)

    print(f"=== run_qa: {cmd} ===")
    print("초기화 중 (ESP + 카메라)...")
    init_esp()
    init_camera(STREAM_URL)
    print("초기화 완료\n")

    exit_code = 1
    try:
        # "ocr"는 선택적 [top] 인자를 받음, 나머지는 nargs 고정
        if cmd == "ocr":
            extra = args[1:2]
        else:
            extra = args[1:1 + nargs]
        exit_code = fn(*extra)
    finally:
        print("\n정리 중...")
        close_esp()
        print("종료")

    sys.exit(exit_code)
