"""qa_checks.py — Stage 5 QA 확인 전용 스텝 (설정 변경 없음)

각 함수: step_NN_name() -> (항목명, 상태, 상세, 캡처경로)
상태 값: "PASS" / "FAIL" / "UNKNOWN"
"""
import os, datetime
import cv2

from lib.qa import (
    open_settings, settings_search,
    check_text_present, read_screen_text,
)
from lib.vision import grab

# ── 경로 상수 ───────────────────────────────────────────────────────────
CAPTURES_DIR = "captures"


# ────────────────────────────────────────────────────────────────────────
# 내부 유틸
# ────────────────────────────────────────────────────────────────────────

def _save_frame(tag: str):
    """현재 화면을 captures/<tag>_<timestamp>.jpg 로 저장.

    Returns:
        저장 경로 문자열, 실패 시 None.
    """
    os.makedirs(CAPTURES_DIR, exist_ok=True)
    frame = grab(15)
    if frame is None:
        return None
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(CAPTURES_DIR, f"{tag}_{ts}.jpg")
    cv2.imwrite(path, rot)
    return path


def _print_result(result):
    name, status, detail, path = result
    mark = "PASS" if status == "PASS" else ("SKIP" if status == "UNKNOWN" else "FAIL")
    print(f"  [{mark}] {name}: {detail}")
    if path:
        print(f"         캡처: {path}")


# ────────────────────────────────────────────────────────────────────────
# 체크리스트 항목 3: Screen timeout = 5 minutes
# ────────────────────────────────────────────────────────────────────────

_STEP3_NAME     = "Screen timeout = 5 minutes"
_TIMEOUT_KW     = "Screen timeout"
_EXPECTED_VALUE = "5 minutes"


def step_03_screen_timeout():
    """[3] Screen timeout이 5분으로 설정돼 있는지 확인 (읽기 전용).

    흐름:
      1) open_settings() — 홈에서 Settings 진입
      2) settings_search("Screen timeout") — 검색창 TYPE (탭 좌표 TODO)
      3) check_text_present("5 minutes") — 현재 값 OCR 확인

    Returns:
        (항목명: str, 상태: str, 상세: str, 캡처경로: str|None)
    """
    print(f"\n[3] {_STEP3_NAME} 확인 시작")

    # ── 1. Settings 진입 ────────────────────────────────────────────────
    print("  [3-1] Settings 진입...")
    if not open_settings():
        path = _save_frame("step3_fail_settings")
        result = (_STEP3_NAME, "FAIL", "Settings 진입 확인 실패", path)
        _print_result(result)
        return result

    # ── 2. Screen timeout 항목으로 이동 ─────────────────────────────────
    print("  [3-2] 'Screen timeout' 검색/이동...")
    nav_ok = settings_search(_TIMEOUT_KW)
    if not nav_ok:
        # 검색창 탭 미구현이라 타입이 안 들어간 경우 등 — UNKNOWN으로 처리
        path = _save_frame("step3_unknown_nav")
        result = (_STEP3_NAME, "UNKNOWN",
                  f"'{_TIMEOUT_KW}' 화면 미확인 (검색창 탭 TODO)", path)
        _print_result(result)
        return result

    # ── 3. 현재 값 '5 minutes' 확인 ─────────────────────────────────────
    print(f"  [3-3] '{_EXPECTED_VALUE}' 표시 여부 확인...")
    found = check_text_present(_EXPECTED_VALUE, flush=15)
    path = _save_frame("step3_result")

    if found:
        detail = f"현재 값 '{_EXPECTED_VALUE}' 확인됨"
        status = "PASS"
    else:
        detail = f"현재 값 '{_EXPECTED_VALUE}' 미확인 — 다른 timeout 값이 설정됐을 수 있음"
        status = "FAIL"

    result = (_STEP3_NAME, status, detail, path)
    _print_result(result)
    return result


# ────────────────────────────────────────────────────────────────────────
# 독립 실행
# ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from lib.esp import init as init_esp, close as close_esp
    from lib.vision import init_camera
    from lib.config import STREAM_URL

    print("=== QA Checks — Stage 5 ===")
    init_esp()
    init_camera(STREAM_URL)

    results = []
    try:
        results.append(step_03_screen_timeout())
    finally:
        close_esp()

    print("\n=== 결과 요약 ===")
    fail = 0
    for name, status, detail, _ in results:
        mark = "✓" if status == "PASS" else ("?" if status == "UNKNOWN" else "✗")
        print(f"  {mark} [{status}] {name}")
        if status != "PASS":
            fail += 1

    sys.exit(1 if fail else 0)
