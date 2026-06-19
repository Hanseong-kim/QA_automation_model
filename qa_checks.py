"""qa_checks.py — Stage 5 QA 확인 전용 스텝 (설정 변경 없음)

각 함수: step_NN_name() -> (항목명, 상태, 상세, 캡처경로)
상태 값: "PASS" / "FAIL" / "UNKNOWN"
"""
import os, datetime
import cv2

import time

from lib.qa import (
    open_settings, settings_search,
    check_text_present, read_screen_text,
    ROI_TOP_HALF, detect_radio_selected,
)
from lib.esp import send
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

# 검색 결과 첫 항목 진입 시퀀스 (검색 결과 화면 → Screen timeout 상세)
SCREEN_TIMEOUT_NAV         = ["KEY:ENTER", "KEY:ENTER", "KEY:ENTER"]  # 검색결과→상세 진입 (실측)
_SCREEN_TIMEOUT_NAV_DELAY  = 1.5   # 각 키 사이 대기 (초)
_SCREEN_TIMEOUT_OPEN_WAIT  = 1.5   # 마지막 ENTER 후 화면 전환 대기 (초)
_SCREEN_TIMEOUT_POLL_COUNT = 17    # 상세 화면 폴링 횟수 (0.3초 × 17 ≈ 최대 5초)
_SCREEN_TIMEOUT_POLL_SEC   = 0.3   # 폴링 간격 (초)


def step_03_screen_timeout():
    """[3] Screen timeout이 5분으로 설정돼 있는지 확인 (읽기 전용).

    흐름:
      1) open_settings()
      2) settings_search("Screen timeout") — 결과 폴링 확인
      3) SCREEN_TIMEOUT_NAV (ENTER×3) → 상세 화면 진입 대기
      4) "5 minutes" 폴링 (최대 5초, ROI_TOP_HALF)
      5) PASS / FAIL (FAIL 시 화면 텍스트 detail 포함)

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

    # ── 2. "Screen timeout" 검색 (폴링 확인) ────────────────────────────
    print("  [3-2] 'Screen timeout' 검색...")
    if not settings_search(_TIMEOUT_KW):
        path = _save_frame("step3_fail_search")
        result = (_STEP3_NAME, "UNKNOWN", f"'{_TIMEOUT_KW}' 검색 결과 미확인", path)
        _print_result(result)
        return result

    # ── 3. 상세 화면 진입 (ENTER × 3, 실측) ────────────────────────────
    print("  [3-3] Screen timeout 상세 화면 진입...")
    for i, key in enumerate(SCREEN_TIMEOUT_NAV):
        print(f"    {key}")
        send(key, wait=0)
        if i < len(SCREEN_TIMEOUT_NAV) - 1:
            time.sleep(_SCREEN_TIMEOUT_NAV_DELAY)
    print(f"  [3-3] 화면 전환 대기 {_SCREEN_TIMEOUT_OPEN_WAIT}초...")
    time.sleep(_SCREEN_TIMEOUT_OPEN_WAIT)

    # ── 4. 옵션 화면 로딩 확인 폴링 — 전체 화면 (최대 5초) ─────────────────
    print(f"  [3-4] '{_EXPECTED_VALUE}' 화면 로딩 폴링 (최대 {_SCREEN_TIMEOUT_POLL_COUNT}회)...")
    loaded = False
    for attempt in range(1, _SCREEN_TIMEOUT_POLL_COUNT + 1):
        if check_text_present(_EXPECTED_VALUE, flush=15, roi=None):
            print(f"  [3-4] 옵션 화면 확인됨 (시도 {attempt}/{_SCREEN_TIMEOUT_POLL_COUNT})")
            loaded = True
            break
        print(f"  [3-4] 미확인 (시도 {attempt}/{_SCREEN_TIMEOUT_POLL_COUNT}) — {_SCREEN_TIMEOUT_POLL_SEC}초 대기")
        time.sleep(_SCREEN_TIMEOUT_POLL_SEC)

    if not loaded:
        path = _save_frame("step3_fail_load")
        result = (_STEP3_NAME, "UNKNOWN", "옵션 화면 로딩 미확인 — 타임아웃", path)
        _print_result(result)
        return result

    # ── 5. 라디오 버튼 선택 여부 판정 ────────────────────────────────────
    print(f"  [3-5] '{_EXPECTED_VALUE}' 라디오 선택 여부 판정...")
    radio_state = detect_radio_selected(_EXPECTED_VALUE)
    path = _save_frame("step3_result")

    if radio_state == "SELECTED":
        result = (_STEP3_NAME, "PASS", f"'{_EXPECTED_VALUE}' 라디오 선택 확인됨", path)
    elif radio_state == "NOT":
        screen_items = read_screen_text(flush=5, roi=None)
        visible = ", ".join(f"'{t}'" for t, _c, _xy in screen_items[:8]) or "없음"
        detail = f"'{_EXPECTED_VALUE}' 라디오 미선택 — 화면 텍스트: {visible}"
        result = (_STEP3_NAME, "FAIL", detail, path)
    else:  # UNKNOWN
        result = (_STEP3_NAME, "UNKNOWN", f"'{_EXPECTED_VALUE}' 라벨 미검출 — 라디오 판정 불가", path)

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
