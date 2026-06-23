"""qa_checks.py -- Stage 5 QA check-only steps (read-only, no settings changes)

QA_ITEMS spec table defines each check item as data.
run_item() is the generic runner that executes any item.
"""
import os, re, datetime, time

import cv2

from lib.qa import (
    open_settings, settings_search,
    check_text_present,
    detect_radio_selected, detect_toggle_state,
    ROI_TOP_HALF, NAV_BACK, SEARCH_CLEAR_CLICK,
)
from lib.esp import send
from lib.vision import grab

# ---------------------------------------------------------------------------
# QA Items spec table
#   id:       unique identifier (qa1, qa2, qa3, qa4, qa6, qa7, qa8)
#   name:     human-readable description (used in reports)
#   search:   Settings search keyword
#   nav:      key sequence to reach detail/option screen after search
#   detector/label/expected: 단일 검사 (한 화면에서 컨트롤 1개)
#       detector: "radio" or "toggle"
#       label:    OCR label for the detector's row (토글/라디오가 있는 '행'의 텍스트 —
#                 제목·검색결과 텍스트가 아니라 컨트롤 옆 라벨이어야 정확히 읽음)
#       expected: "SELECTED"/"NOT" for radio, "ON"/"OFF" for toggle
#   checks (opt): 한 화면에서 컨트롤 여러 개 검사 (병합 항목: qa4=Display 2토글, qa8=Notifications 2토글)
#       [{"detector":..,"label":..,"expected":..}, ...] — 전부 일치해야 PASS.
#       있으면 detector/label/expected 대신 이걸 사용.
#   exit_back (opt):    qa_between이 이 화면을 빠져나올 back 횟수 (기본 1; nav 깊이만큼)
#   reuse_screen (opt): True면 이전 항목 화면 그대로 검출 (현재 병합으로 미사용)
# read-only: 토글 항목은 ENTER로 토글을 누르지 않는다(상태 뒤집힘 방지)
# 가짜 OFF 주의: nav 부족으로 검색결과 페이지에 머물면 '파랑없음=OFF'로 오통과 →
#               반드시 실제 토글이 보이는 화면까지 nav해야 함
# ---------------------------------------------------------------------------
QA_ITEMS = [
    {
        "id": "qa1", "name": "3-button navigation",
        # checklist: TYPE '3-button navigation' -> ENTER ENTER (opens Navigation mode screen)
        "search": "3-button navigation",
        "nav": ["KEY:ENTER", "KEY:ENTER"],             # verified(checklist): 1->2 (qa1 hang fix)
        "exit_back": 2,                                # nav ENTER×2 → 2단계 깊이 (TODO probe ±1)
        "detector": "radio", "label": "3-button navigation",
        "expected": "SELECTED",
    },
    {
        "id": "qa2", "name": "Battery percentage ON",
        "search": "Battery percentage",                # checklist 'Show battery percentage'도 동일 동작
        "nav": ["KEY:ENTER", "KEY:ENTER"],             # verified(PASS): Battery 화면 도달, 토글 보임(누르지 않음)
        "exit_back": 2,                                # nav ENTER×2 → 2단계 깊이 (TODO probe ±1)
        "detector": "toggle", "label": "Battery percentage",
        "expected": "ON",
    },
    {
        "id": "qa3", "name": "Screen timeout = 5 minutes",
        "search": "Screen timeout",
        "nav": ["KEY:ENTER", "KEY:ENTER", "KEY:ENTER"],  # verified
        "exit_back": 3,                                  # nav ENTER×3 → 3단계 깊이 (qa3→qa4 전환 깨짐 수정, TODO probe ±1)
        "detector": "radio", "label": "5 minutes",
        "expected": "SELECTED",
    },
    {
        "id": "qa4", "name": "Display toggles OFF (Real-time + Double-click)",
        # qa4+qa5 병합: 같은 Display 화면에 두 토글이 함께 보임 (Double-click 위, Real-time 아래).
        # nav ENTER×2: 검색결과 페이지가 아니라 Display 화면으로 진입해야 진짜 토글이 보임
        # (이전 가짜 PASS 원인: 검색결과 흰 화면=파랑없음=OFF 오통과)
        "search": "Real-time network speed",
        "nav": ["KEY:ENTER", "KEY:ENTER"],             # Display 진입
        "exit_back": 2,                                # nav ENTER×2 → 2단계 깊이 (TODO probe ±1)
        "checks": [                                     # read-only: 토글 누르지 말 것
            {"detector": "toggle", "label": "Real-time network speed", "expected": "OFF"},
            {"detector": "toggle", "label": "Double",                  "expected": "OFF"},
        ],
    },
    {
        "id": "qa6", "name": "Lock screen clock size = Small",
        # checklist: TYPE Wallpaper -> Wallpaper&style -> Clock color and size -> Size
        "search": "Wallpaper",
        "nav": ["KEY:ENTER", "KEY:DOWN", "KEY:ENTER", "KEY:ENTER",
                "KEY:TAB", "KEY:TAB", "KEY:TAB", "KEY:ENTER",
                "KEY:TAB", "KEY:TAB", "KEY:ENTER"],    # 체크리스트 시퀀스. 마지막 ENTER가 Small을 '선택'하면 제거(read-only)
        "exit_back": 3,                                # TODO: probe — Wallpaper 깊은 화면, 검색창 복귀에 필요한 back 횟수
        "detector": "radio", "label": "Small",
        "expected": "SELECTED",
    },
    {
        "id": "qa7", "name": "Notification bubbles OFF",
        "search": "bubbles",                           # checklist: TYPE bubbles
        "nav": ["KEY:ENTER", "KEY:ENTER", "KEY:ENTER"],  # 체크리스트. 마지막 ENTER가 토글 누르면 1개 줄일 것(read-only)
        # 라벨: 제목 'Bubbles'가 아니라 실제 토글 행 'Allow apps to show bubbles'
        # (이전: 제목 행 오른쪽 빈영역을 읽어 OFF가 우연히 맞음)
        "detector": "toggle", "label": "Allow apps to show bubbles",
        "expected": "OFF",
    },
    {
        "id": "qa8", "name": "Notifications toggles OFF (Enhanced + Notification dot)",
        # qa8a+qa8b 병합: checklist: TYPE 'Enhanced notifications' → ENTER ENTER → 하단에 두 토글 보임
        "search": "Enhanced notifications",
        "nav": ["KEY:ENTER", "KEY:ENTER"],
        "exit_back": 2,                                # nav ENTER×2 → 2단계 깊이 (TODO probe ±1)
        "checks": [                                     # read-only: 토글 누르지 말 것
            {"detector": "toggle", "label": "Enhanced notifications", "expected": "OFF"},
            {"detector": "toggle", "label": "Notification dot",       "expected": "OFF"},
        ],
    },
]

# Lookup helper
_QA_BY_ID = {item["id"]: item for item in QA_ITEMS}

# ---------------------------------------------------------------------------
# Constants (generalized from step_03)
# ---------------------------------------------------------------------------
CAPTURES_DIR = "captures"

_NAV_DELAY        = 1.5   # delay between nav keys (seconds)
_OPEN_WAIT        = 1.5   # wait after last nav key for screen transition (알려진 정상값)
_LOAD_POLL_COUNT  = 6     # option screen loading poll attempts (틀린 화면이면 ~6회만에 빠르게 UNKNOWN 탈출 — 속도는 여기서만 줄임)
_LOAD_POLL_SEC    = 0.3   # poll interval (seconds)
_LOAD_FLUSH       = 15    # 로딩 폴링용 카메라 플러시. mjpeg 버퍼 지연 때문에 낮추면 이전 화면의
                          # 낡은 프레임을 읽어 올바른 화면에서도 라벨을 못 읽는다 — 낮추지 말 것.
_BETWEEN_DELAY    = 0.6   # qa_between 각 동작 사이 대기 (초)
_BETWEEN_TYPE_WAIT = 3.0  # qa_between TYPE 후 검색결과 렌더 대기 (초)


# ---------------------------------------------------------------------------
# qa between -- 항목 간 전환 (전체 실행 시 매번 Settings 재진입 대신 사용)
# ---------------------------------------------------------------------------

def qa_between(exit_back: int = 1):
    """한 QA 항목 검사 후 다음 항목 검색을 위해 검색창으로 복귀.

    시퀀스: back(NAV_BACK) × exit_back → KEY:UP → remove(SEARCH_CLEAR_CLICK)
      - back: 상세화면을 빠져나와 검색 결과 화면으로
      - UP:   검색창으로 포커스 복귀
      - remove: 검색창 X 버튼 클릭 → 이전 검색어 비움

    Args:
        exit_back: 현재 화면 깊이만큼 back을 누를 횟수 (기본 1).
    """
    for i in range(max(1, exit_back)):
        print(f"  [between] back {NAV_BACK} ({i + 1}/{exit_back})")
        send(NAV_BACK, wait=0)
        time.sleep(_BETWEEN_DELAY)
    print("  [between] KEY:UP (검색창 복귀)")
    send("KEY:UP", wait=0)
    time.sleep(_BETWEEN_DELAY)
    print(f"  [between] remove {SEARCH_CLEAR_CLICK} (이전 검색어 지움)")
    send(SEARCH_CLEAR_CLICK, wait=0)
    time.sleep(_BETWEEN_DELAY)


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _save_frame(tag: str):
    """Save current screen to captures/<tag>_<timestamp>.jpg.

    Returns:
        File path string, None on failure.
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
        print(f"         capture: {path}")


# ---------------------------------------------------------------------------
# Generic runner
# ---------------------------------------------------------------------------

def run_item(item, entry_mode: str = "full", prev_exit_back: int = 1):
    """Run a single QA check item.

    Args:
        item: dict from QA_ITEMS (or looked up by id string).
        entry_mode: 검색창까지 도달하는 방법.
            "full"    -- open_settings() + settings_search() (전체 실행 첫 항목)
            "solo"    -- settings_search() + nav만 (단독 실행: Settings 메인 화면에
                         이미 들어와 있다고 가정, 앱 서랍 SWIPE 생략)
            "between" -- qa_between() + TYPE (전체 실행 중 항목 간 전환)
            "reuse"   -- 진입/검색/nav 생략, 현재 화면에서 검출만 (그룹 2번째 항목)
        prev_exit_back: "between"에서 직전 항목 화면을 빠져나올 back 횟수.

    Returns:
        (name: str, status: str, detail: str, capture_path: str|None)
    """
    if isinstance(item, str):
        item = _QA_BY_ID[item]

    item_id  = item["id"]
    name     = item["name"]
    search   = item["search"]
    nav      = item["nav"]

    # checks 정규화: 병합 항목은 "checks" 리스트, 단일 항목은 detector/label/expected
    checks = item.get("checks") or [{
        "detector": item["detector"],
        "label":    item["label"],
        "expected": item["expected"],
    }]
    load_label = checks[0]["label"]   # 화면 로딩 확인용 (첫 컨트롤 라벨)

    print(f"\n[{item_id}] {name} check start (entry={entry_mode})")

    if entry_mode == "reuse":
        # 이전 항목과 같은 화면 그대로 — 진입/검색/nav 전부 생략, 바로 검출
        print(f"  [{item_id}-1~3] reuse: 이전 항목 화면 재사용 (진입/검색/nav 생략)")
    else:
        # -- 1. 검색창 확보 --------------------------------------------------
        if entry_mode == "between":
            print(f"  [{item_id}-1] qa_between (back×{prev_exit_back} → UP → remove)...")
            qa_between(prev_exit_back)
        elif entry_mode == "full":
            print(f"  [{item_id}-1] open_settings()...")
            if not open_settings():
                path = _save_frame(f"{item_id}_fail_settings")
                result = (name, "UNKNOWN", "Settings 진입 실패 -- 'Display' 미확인", path)
                _print_result(result)
                return result
        else:  # "solo": Settings 메인 화면 가정 — 앱 서랍 SWIPE 생략, 검색만
            print(f"  [{item_id}-1] solo: Settings 메인 화면 가정 (open_settings 생략)")

        # -- 2. 검색어 입력 --------------------------------------------------
        if entry_mode == "between":
            # qa_between이 검색창 포커스+클리어까지 했으므로 바로 TYPE
            print(f"  [{item_id}-2] TYPE:{search} (검색창 복귀 상태)...")
            send(f"TYPE:{search}", wait=0)
            print(f"  [{item_id}-2] 결과 렌더 대기 {_BETWEEN_TYPE_WAIT}s...")
            time.sleep(_BETWEEN_TYPE_WAIT)
        else:  # "full" / "solo": settings_search가 검색창 포커스+TYPE 수행
            print(f"  [{item_id}-2] settings_search('{search}')...")
            if not settings_search(search):
                path = _save_frame(f"{item_id}_fail_search")
                result = (name, "UNKNOWN", f"검색어 '{search}' 화면 미확인 -- 검색 실패", path)
                _print_result(result)
                return result

        # -- 3. 상세/옵션 화면 진입 (검색 결과에서 nav 키 시퀀스) ------------
        if nav:
            print(f"  [{item_id}-3] 상세화면 이동 ({len(nav)} keys)...")
            for i, key in enumerate(nav):
                print(f"    {key}")
                send(key, wait=0)
                if i < len(nav) - 1:
                    time.sleep(_NAV_DELAY)
            print(f"  [{item_id}-3] 화면 전환 대기 {_OPEN_WAIT}s...")
            time.sleep(_OPEN_WAIT)

    # -- 4. 옵션 화면 로딩 확인 (OCR 폴링 — 첫 컨트롤 label 등장 대기) ---------
    print(f"  [{item_id}-4] 옵션 화면 로딩 확인 (label '{load_label}' 폴링)...")
    loaded = False
    for attempt in range(1, _LOAD_POLL_COUNT + 1):
        if check_text_present(load_label, flush=_LOAD_FLUSH, roi=None):
            print(f"  [{item_id}-4] 로딩 확인 (시도 {attempt}/{_LOAD_POLL_COUNT})")
            loaded = True
            break
        time.sleep(_LOAD_POLL_SEC)
    if not loaded:
        path = _save_frame(f"{item_id}_fail_load")
        result = (name, "UNKNOWN", f"'{load_label}' 미등장 -- 옵션 화면 로딩 실패", path)
        _print_result(result)
        return result

    # -- 5. Detect state (최종 화면에서 각 컨트롤이 켜졌/선택됐는지 확인) ------
    #   checks를 순회: 전부 expected 일치 → PASS, 라벨 미검출 있으면 UNKNOWN,
    #   그 외 불일치 있으면 FAIL. detail에 컨트롤별 결과 나열.
    print(f"  [{item_id}-5] Detecting {len(checks)} control(s)...")

    parts    = []          # 컨트롤별 결과 문자열
    any_fail = False
    any_unknown = False

    for chk in checks:
        c_det   = chk["detector"]
        c_label = chk["label"]
        c_exp   = chk["expected"]

        if c_det == "radio":
            state = detect_radio_selected(c_label)
        elif c_det == "toggle":
            state = detect_toggle_state(c_label)
        else:
            state = "UNKNOWN"

        mark = "OK" if state == c_exp else ("?" if state == "UNKNOWN" else "X")
        parts.append(f"'{c_label}' {c_det}:{state}(exp {c_exp}) {mark}")
        print(f"    - {parts[-1]}")
        if state == "UNKNOWN":
            any_unknown = True
        elif state != c_exp:
            any_fail = True

    path = _save_frame(f"{item_id}_result")
    detail = " / ".join(parts)

    if any_fail:
        status = "FAIL"
    elif any_unknown:
        status = "UNKNOWN"
    else:
        status = "PASS"

    result = (name, status, detail, path)
    _print_result(result)
    return result


# ---------------------------------------------------------------------------
# Sequence runner (first=full, rest=between, group 2nd=reuse)
# ---------------------------------------------------------------------------

def run_sequence(item_ids):
    """여러 항목을 순서대로 실행하며 진입 모드를 자동 결정.

    - 항목이 1개뿐(단독 실행): "solo" (Settings 메인 화면 가정, open_settings 생략)
    - 여러 개의 첫 항목: "full" (open_settings + search)
    - reuse_screen 항목: "reuse" (이전 화면 그대로 검출)
    - 그 외: "between" (qa_between으로 검색창 복귀 후 검색)

    Returns: [(name, status, detail, path), ...]
    """
    results = []
    prev_exit_back = 1
    single = len(item_ids) == 1   # 단독 실행이면 Settings 진입 생략(solo)
    for i, iid in enumerate(item_ids):
        item = _QA_BY_ID[iid] if isinstance(iid, str) else iid
        if i == 0:
            mode = "solo" if single else "full"
        elif item.get("reuse_screen"):
            mode = "reuse"
        else:
            mode = "between"
        results.append(run_item(item, mode, prev_exit_back))
        if mode != "reuse":
            prev_exit_back = item.get("exit_back", 1)
    return results


# ---------------------------------------------------------------------------
# Legacy wrapper (step_03 compatibility)
# ---------------------------------------------------------------------------

def step_03_screen_timeout():
    """[3] Screen timeout = 5 minutes check (legacy wrapper -> run_item)."""
    return run_item("qa3")


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from lib.esp import init as init_esp, close as close_esp
    from lib.vision import init_camera
    from lib.config import STREAM_URL

    # Parse optional item ids (쉼표/공백 혼용 허용). 기본값: qa3 (하위 호환)
    item_ids = [t for t in re.split(r"[,\s]+", " ".join(sys.argv[1:])) if t] or ["qa3"]

    # Validate
    for iid in item_ids:
        if iid not in _QA_BY_ID:
            print(f"ERROR: unknown item id '{iid}'")
            print(f"Available: {', '.join(_QA_BY_ID.keys())}")
            sys.exit(1)

    print("=== QA Checks -- Stage 5 ===")
    init_esp()
    init_camera(STREAM_URL)

    results = []
    try:
        results = run_sequence(item_ids)
    finally:
        close_esp()

    print("\n=== Results summary ===")
    fail = 0
    for name, status, detail, _ in results:
        mark = "v" if status == "PASS" else ("?" if status == "UNKNOWN" else "x")
        print(f"  {mark} [{status}] {name}")
        if status != "PASS":
            fail += 1

    sys.exit(1 if fail else 0)
