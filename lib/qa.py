"""lib/qa.py — QA 확인 공통 헬퍼 (읽기 전용, 설정 변경 없음)"""
import re, time
import cv2
import numpy as np
from difflib import SequenceMatcher

from lib.config import OCR_CONF
from lib.esp import send
from lib.vision import grab, ocr_readtext

# ── 토글 색 분석 상수 (타이트크롭 방식 — 최종값은 calibrate 재실행으로 확정) ──
TOGGLE_ROW_PAD  = 10    # 토글 행 bbox에 추가할 y 패딩 (px)
TOGGLE_X_FRAC   = 0.88  # 프레임 너비 대비 토글 알약 좁은 크롭 시작 x 비율
ON_HUE_LOW      = 85    # HSV H 하한 — 파랑/초록 계열 (OpenCV 0-179)
ON_HUE_HIGH     = 135   # HSV H 상한
ON_SAT_MIN      = 100   # 채도 최소값 (회색/쿨화이트 배경 제외 — 상향)
ON_VAL_MIN      = 80    # 명도 최소값 (어두운 영역 제외)
ON_PIX_RATIO    = 0.10  # 이 비율 이상이면 ON 판정 (TODO: calibrate 재실행 확정)

# ── 라디오 버튼 선택 판정 상수 (calibrate qa1/qa3 실측 보정) ──────────────
# 측정영역을 calibrate_color.py와 동일하게 "라벨 왼쪽 strip 전체"로 일치시킴.
RADIO_LABEL_MARGIN = 10   # 라벨 x0에서 왼쪽으로 띄울 여백 (px)
RADIO_Y_PAD        = 30   # 라벨 중심 y 기준 ±px
RADIO_HUE_LOW   = 85    # 파랑 HSV H 하한 (OpenCV 0-179)
RADIO_HUE_HIGH  = 135   # 파랑 HSV H 상한
RADIO_SAT_MIN   = 40    # 채도 최소 — 실측: 라디오 점 S 분포 40~131, mean=54
RADIO_ON_RATIO  = 0.07  # 실측 보정: SELECTED min 0.104 / NOT max 0.033 → 임계 0.068
                        # (qa6 시계크기는 라디오 아님 → 이 함수 대상 제외)

# ── fuzzy 매칭 상수 ──────────────────────────────────────────────────────
FUZZY_MIN_LEN   = 4     # SequenceMatcher 적용 최소 단어 길이
_SPLIT_RE       = re.compile(r'[\s\-_,./]+')

# ── OCR ROI 프리셋 (비율 튜플: x1r, y1r, x2r, y2r, 0.0~1.0) ─────────────
# 회전 후 프레임 기준(세로 긴 화면). read_screen_text(roi=...) 에 전달.
ROI_TOP_HALF  = (0.0, 0.0, 1.0, 0.5)   # 상단 절반
ROI_TOP_THIRD = (0.0, 0.0, 1.0, 0.33)  # 상단 1/3


# ────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ────────────────────────────────────────────────────────────────────────

def _fuzzy_match(text: str, keyword: str, threshold: float) -> bool:
    """OCR 텍스트에 keyword가 fuzzy 포함되는지 판정.

    2del_protocol.py:74-81 패턴을 일반화한 단일 구현.
    단어 정확 일치 우선, 이후 SequenceMatcher ratio 비교.
    """
    t = text.lower().strip()
    kw = keyword.lower().strip()
    words = _SPLIT_RE.split(t)
    if kw in words or kw in t:
        return True
    for w in words:
        if len(w) >= FUZZY_MIN_LEN and SequenceMatcher(None, w, kw).ratio() >= threshold:
            return True
    return False


def _bbox_bounds(bbox):
    """EasyOCR bbox [[x0,y0],...] 에서 (x_min, y_min, x_max, y_max) 반환."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_center(bbox):
    """EasyOCR bbox 중심좌표 (cx, cy) 반환."""
    x0, y0, x1, y1 = _bbox_bounds(bbox)
    return int((x0 + x1) / 2), int((y0 + y1) / 2)


# ────────────────────────────────────────────────────────────────────────
# 공개 API
# ────────────────────────────────────────────────────────────────────────

def read_screen_text(flush: int = 15, roi=None) -> list:
    """카메라 프레임을 grab → 90도 회전 → (선택) crop → OCR → 신뢰도 필터링.

    Args:
        flush: 카메라 버퍼 플러시 횟수.
        roi: None이면 전체 프레임. (x1r, y1r, x2r, y2r) 비율 튜플(0.0~1.0)이면
             회전 후 해당 영역만 crop해서 OCR. ROI_TOP_HALF 등 프리셋 사용 가능.

    Returns:
        [(text, confidence, (cx, cy)), ...] — 좌표는 항상 원본 회전 프레임 기준.
        프레임 획득 실패 시 빈 리스트.
    """
    frame = grab(flush)
    if frame is None:
        return []
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

    if roi is None:
        target = rot
        ox, oy = 0, 0
    else:
        h, w = rot.shape[:2]
        x1r, y1r, x2r, y2r = roi
        x1 = max(0, int(x1r * w))
        y1 = max(0, int(y1r * h))
        x2 = min(w, int(x2r * w))
        y2 = min(h, int(y2r * h))
        target = rot[y1:y2, x1:x2]
        ox, oy = x1, y1  # crop 좌표 → 원본 프레임 좌표 보정 오프셋

    results = []
    for (bbox, text, conf) in ocr_readtext(target):
        if conf < OCR_CONF:
            continue
        cx, cy = _bbox_center(bbox)
        results.append((text, conf, (cx + ox, cy + oy)))
    return results


def check_text_present(keyword: str, threshold: float = 0.8, flush: int = 15, roi=None) -> bool:
    """현재 화면에 keyword가 있는지 bool 반환.

    Args:
        keyword: 찾을 텍스트.
        threshold: fuzzy 매칭 임계값 (0~1).
        flush: 카메라 버퍼 플러시 횟수.
        roi: read_screen_text에 전달할 ROI 비율 튜플 (None이면 전체).
    """
    for (text, _conf, _center) in read_screen_text(flush, roi=roi):
        if _fuzzy_match(text, keyword, threshold):
            return True
    return False


def detect_toggle_state(label_text: str, threshold: float = 0.8, flush: int = 15) -> str:
    """라벨 텍스트 오른쪽 영역의 HSV 색으로 토글 ON/OFF 판정.

    Args:
        label_text: 토글 왼쪽에 표시되는 라벨 OCR 텍스트.
        threshold: 라벨 fuzzy 매칭 임계값.
        flush: 카메라 버퍼 플러시 횟수.

    Returns:
        "ON" / "OFF" / "UNKNOWN"
    """
    frame = grab(flush)
    if frame is None:
        return "UNKNOWN"
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    h, w = rot.shape[:2]

    target_bbox = None
    for (bbox, text, conf) in ocr_readtext(rot):
        if conf < OCR_CONF:
            continue
        if _fuzzy_match(text, label_text, threshold):
            target_bbox = bbox
            break

    if target_bbox is None:
        return "UNKNOWN"

    x0, y0, x1, y1 = _bbox_bounds(target_bbox)
    y_top = max(0, int(y0) - TOGGLE_ROW_PAD)
    y_bot = min(h, int(y1) + TOGGLE_ROW_PAD)
    x_start = int(w * TOGGLE_X_FRAC)  # 타이트 크롭: 토글 알약 주변만
    crop = rot[y_top:y_bot, x_start:w]

    if crop.size == 0:
        return "UNKNOWN"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 0] >= ON_HUE_LOW) &
        (hsv[:, :, 0] <= ON_HUE_HIGH) &
        (hsv[:, :, 1] >= ON_SAT_MIN) &
        (hsv[:, :, 2] >= ON_VAL_MIN)
    )
    ratio = np.count_nonzero(mask) / mask.size
    return "ON" if ratio >= ON_PIX_RATIO else "OFF"


def detect_radio_selected(label_text: str, threshold: float = 0.8, flush: int = 15) -> str:
    """라벨 왼쪽 strip 전체의 HSV 파랑 비율로 라디오 선택 여부 판정.

    측정영역을 calibrate_color.py와 동일하게 맞춤 (RADIO_ON_RATIO 호환):
    1. 라벨 bbox 탐색 → 왼쪽 끝(x0b), 중심 y(cy) 확보
    2. x=[0, x0b - RADIO_LABEL_MARGIN], y=[cy ± RADIO_Y_PAD] strip 크롭
    3. HSV 파랑 픽셀 비율 >= RADIO_ON_RATIO → "SELECTED", 아니면 "NOT"

    주의: qa6(시계 크기 Small/Dynamic)처럼 왼쪽에 라디오 버튼이 없는
    리스트/카드형 UI는 이 함수로 판정 불가 — 호출하지 말 것.

    Returns: "SELECTED" / "NOT" / "UNKNOWN"
    """
    frame = grab(flush)
    if frame is None:
        return "UNKNOWN"
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    h, w = rot.shape[:2]

    target_bbox = None
    for (bbox, text, conf) in ocr_readtext(rot):
        if conf < OCR_CONF:
            continue
        if _fuzzy_match(text, label_text, threshold):
            target_bbox = bbox
            break

    if target_bbox is None:
        return "UNKNOWN"

    x0b, y0b, x1b, y1b = _bbox_bounds(target_bbox)
    cy = int((y0b + y1b) / 2)
    x0 = 0
    x1 = max(0, int(x0b) - RADIO_LABEL_MARGIN)
    y0 = max(0, cy - RADIO_Y_PAD)
    y1 = min(h, cy + RADIO_Y_PAD)
    crop = rot[y0:y1, x0:x1]

    if crop.size == 0:
        return "UNKNOWN"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 0] >= RADIO_HUE_LOW) &
        (hsv[:, :, 0] <= RADIO_HUE_HIGH) &
        (hsv[:, :, 1] >= RADIO_SAT_MIN)
    )
    ratio = np.count_nonzero(mask) / mask.size
    return "SELECTED" if ratio >= RADIO_ON_RATIO else "NOT"


# ── Settings 진입 시퀀스 상수 (실측 확인됨) ──────────────────────────────
_SETTINGS_SWIPE      = "SWIPE:200,100,200,500"  # 홈 앱 서랍 열기 (아래→위, BL 기준)
_SETTINGS_SLIDE_WAIT = 0.5                       # 슬라이드 후 안착 대기 (초)
_SETTINGS_KEY_SEQ    = [                         # Settings 아이콘까지 포커스 이동 + Enter
    "KEY:TAB", "KEY:TAB",
    "KEY:RIGHT", "KEY:RIGHT", "KEY:RIGHT",
    "KEY:DOWN", "KEY:ENTER",
]
_NAV_KEY_DELAY       = 0.4                       # open_settings 앱 서랍 키 시퀀스 대기 (초)
_SETTINGS_VERIFY_KW  = "Display"                 # Settings 첫 화면 확인 키워드
_SETTINGS_POLL_COUNT = 5                         # 진입 확인 폴링 횟수 (간격 짧고 횟수 늘림)
_SETTINGS_POLL_SEC   = 0.3                       # 폴링 간격 (초) — OCR이 느리므로 짧아도 충분

# ── Settings 검색창 포커스 시퀀스 (실측 확인됨) ──────────────────────────
SEARCH_FOCUS_SEQ   = ["KEY:TAB", "KEY:UP", "KEY:ENTER"]  # 검색창 진입 키 순서
_SEARCH_KEY_DELAY  = 0.9   # SEARCH_FOCUS_SEQ 키 사이 대기 (초) — 검색창 포커스용, 천천히
_SEARCH_TYPE_DELAY = 1.0   # ENTER 후 입력 필드 활성화 대기 — 첫 글자 씹힘 방지
_SEARCH_POLL_COUNT = 33    # 검색 결과 폴링 횟수 (0.3초 × 33 ≈ 최대 10초)
_SEARCH_POLL_SEC   = 0.3   # 폴링 간격 (초)


def open_settings() -> bool:
    """홈에서 앱 서랍을 열고 키보드 네비게이션으로 Settings를 실행한다.

    시퀀스 (실측 확인):
      SWIPE 아래→위 → TAB TAB RIGHT RIGHT RIGHT DOWN ENTER

    Returns:
        Settings 진입 OCR 확인 성공 시 True, 실패 시 False.
    """
    print("  [Settings] 앱 서랍 슬라이드...")
    send(_SETTINGS_SWIPE, wait=0)
    time.sleep(_SETTINGS_SLIDE_WAIT)

    for key in _SETTINGS_KEY_SEQ:
        print(f"  [Settings] {key}")
        send(key, wait=0)
        time.sleep(_NAV_KEY_DELAY)

    print("  [Settings] 진입 확인 중 (폴링)...")
    for attempt in range(1, _SETTINGS_POLL_COUNT + 1):
        if check_text_present(_SETTINGS_VERIFY_KW, flush=15):
            print(f"  [Settings] 진입 성공 (시도 {attempt}/{_SETTINGS_POLL_COUNT})")
            return True
        print(f"  [Settings] 미확인 (시도 {attempt}/{_SETTINGS_POLL_COUNT}) — {_SETTINGS_POLL_SEC}초 대기")
        time.sleep(_SETTINGS_POLL_SEC)
    print("  [Settings] 진입 확인 실패 — Settings 화면이 아닐 수 있음")
    return False


def settings_search(keyword: str) -> bool:
    """Settings 검색창에 포커스를 맞추고 keyword를 TYPE한 뒤 결과 확인.

    검색창 진입 시퀀스 (실측 확인): TAB → UP → ENTER
    각 키 사이 _SEARCH_KEY_DELAY(0.9초) 대기 — 검색창 포커스 이동용으로 천천히.

    Returns:
        keyword가 화면에 나타나면 True.
    """
    for key in SEARCH_FOCUS_SEQ:
        print(f"  [검색] {key}")
        send(key, wait=0)
        time.sleep(_SEARCH_KEY_DELAY)

    # ENTER 직후 입력 필드가 활성화될 때까지 대기 (첫 글자 씹힘 방지)
    print(f"  [검색] 입력 필드 활성화 대기 {_SEARCH_TYPE_DELAY}초...")
    time.sleep(_SEARCH_TYPE_DELAY)

    print(f"  [검색] TYPE:{keyword}")
    send(f"TYPE:{keyword}", wait=0)

    print(f"  [검색] 결과 폴링 (최대 {_SEARCH_POLL_COUNT}회 × {_SEARCH_POLL_SEC}초)...")
    for attempt in range(1, _SEARCH_POLL_COUNT + 1):
        if check_text_present(keyword, flush=15, roi=ROI_TOP_HALF):
            print(f"  [검색] '{keyword}' 확인됨 (시도 {attempt}/{_SEARCH_POLL_COUNT})")
            return True
        print(f"  [검색] 미확인 (시도 {attempt}/{_SEARCH_POLL_COUNT}) — {_SEARCH_POLL_SEC}초 대기")
        time.sleep(_SEARCH_POLL_SEC)
    print(f"  [검색] '{keyword}' 미발견 — 타임아웃")
    return False
