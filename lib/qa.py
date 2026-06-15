"""lib/qa.py — QA 확인 공통 헬퍼 (읽기 전용, 설정 변경 없음)"""
import re, time
import cv2
import numpy as np
from difflib import SequenceMatcher

from lib.config import OCR_CONF
from lib.esp import send
from lib.vision import grab, reader

# ── 토글 색 분석 상수 (TODO: 실제 캡처로 보정) ──────────────────────────
TOGGLE_ROW_PAD  = 10    # 토글 행 bbox에 추가할 y 패딩 (px)
TOGGLE_X_OFFSET = 0.6   # 프레임 너비 대비 토글 영역 시작 x 비율
ON_HUE_LOW      = 85    # HSV H 하한 — 파랑/초록 계열 (OpenCV 0-179)
ON_HUE_HIGH     = 135   # HSV H 상한
ON_SAT_MIN      = 60    # 채도 최소값 (회색/흰색 제외)
ON_PIX_RATIO    = 0.10  # 이 비율 이상이면 ON 판정 (TODO: 실측 보정)

# ── fuzzy 매칭 상수 ──────────────────────────────────────────────────────
FUZZY_MIN_LEN   = 4     # SequenceMatcher 적용 최소 단어 길이
_SPLIT_RE       = re.compile(r'[\s\-_,./]+')


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

def read_screen_text(flush: int = 15) -> list:
    """카메라 프레임을 grab → 90도 회전 → OCR → 신뢰도 필터링.

    Returns:
        [(text, confidence, (cx, cy)), ...] — OCR_CONF 미만 항목 제외.
        프레임 획득 실패 시 빈 리스트.
    """
    frame = grab(flush)
    if frame is None:
        return []
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    results = []
    for (bbox, text, conf) in reader.readtext(rot):
        if conf < OCR_CONF:
            continue
        cx, cy = _bbox_center(bbox)
        results.append((text, conf, (cx, cy)))
    return results


def check_text_present(keyword: str, threshold: float = 0.8, flush: int = 15) -> bool:
    """현재 화면에 keyword가 있는지 bool 반환.

    Args:
        keyword: 찾을 텍스트.
        threshold: fuzzy 매칭 임계값 (0~1).
        flush: 카메라 버퍼 플러시 횟수.
    """
    for (text, _conf, _center) in read_screen_text(flush):
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
    for (bbox, text, conf) in reader.readtext(rot):
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
    x_start = int(w * TOGGLE_X_OFFSET)  # TODO: 실측 후 보정
    crop = rot[y_top:y_bot, x_start:w]

    if crop.size == 0:
        return "UNKNOWN"

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 0] >= ON_HUE_LOW) &
        (hsv[:, :, 0] <= ON_HUE_HIGH) &
        (hsv[:, :, 1] >= ON_SAT_MIN)
    )
    ratio = np.count_nonzero(mask) / mask.size
    return "ON" if ratio >= ON_PIX_RATIO else "OFF"


# ── Settings 진입 시퀀스 상수 (실측 확인됨) ──────────────────────────────
_SETTINGS_SWIPE      = "SWIPE:200,100,200,500"  # 홈 앱 서랍 열기 (아래→위, BL 기준)
_SETTINGS_SLIDE_WAIT = 0.5                       # 슬라이드 후 안착 대기 (초)
_SETTINGS_KEY_SEQ    = [                         # Settings 아이콘까지 포커스 이동 + Enter
    "KEY:TAB", "KEY:TAB",
    "KEY:RIGHT", "KEY:RIGHT", "KEY:RIGHT",
    "KEY:DOWN", "KEY:ENTER",
]
_SETTINGS_KEY_DELAY  = 0.4                       # 키 사이 대기 (초)
_SETTINGS_VERIFY_KW  = "Display"                 # Settings 첫 화면 확인 키워드

# ── Settings 검색창 포커스 시퀀스 (실측 확인됨) ──────────────────────────
SEARCH_FOCUS_SEQ  = ["KEY:TAB", "KEY:UP", "KEY:ENTER"]  # 검색창 진입 키 순서


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
        time.sleep(_SETTINGS_KEY_DELAY)

    print("  [Settings] 진입 확인 중...")
    ok = check_text_present(_SETTINGS_VERIFY_KW, flush=15)
    if ok:
        print("  [Settings] 진입 성공")
    else:
        print("  [Settings] 진입 확인 실패 — Settings 화면이 아닐 수 있음")
    return ok


def settings_search(keyword: str) -> bool:
    """Settings 검색창에 포커스를 맞추고 keyword를 TYPE한 뒤 결과 확인.

    검색창 진입 시퀀스 (실측 확인): TAB → UP → ENTER
    각 키 사이 _SETTINGS_KEY_DELAY(0.4초) 대기.

    Returns:
        keyword가 화면에 나타나면 True.
    """
    for key in SEARCH_FOCUS_SEQ:
        print(f"  [검색] {key}")
        send(key, wait=0)
        time.sleep(_SETTINGS_KEY_DELAY)

    print(f"  [검색] TYPE:{keyword}")
    send(f"TYPE:{keyword}", wait=0)
    time.sleep(1.5)  # 검색 결과 렌더링 대기
    return check_text_present(keyword)
