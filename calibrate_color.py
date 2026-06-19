"""calibrate_color.py — RADIO_X_OFFSET / TOGGLE_X_OFFSET / ratio 임계값 보정 스크립트

실행: .\\venv\\Scripts\\python.exe calibrate_color.py
출력:
  - 콘솔: 이미지별 · 오프셋별 파랑 픽셀 비율 테이블 + 권장값 + HSV 범위 검증
  - captures/debug_<stem>.jpg: 크롭 영역을 그린 디버그 이미지
전제: 이미지는 이미 화면 방향(세로, 90° CW 회전 완료)으로 저장된 파일.
"""

import os
import re

import cv2
import numpy as np
from difflib import SequenceMatcher

from lib.vision import ocr_readtext

# ─────────────────────────────────────────────────────────────────────────────
# 이미지 설정  (경로, 라벨_키워드, 종류, 예상_상태)
#   종류: "radio" / "toggle"
#   예상_상태 radio:  "SELECTED" / "NOT"
#   예상_상태 toggle: "ON" / "OFF"
#   라벨_키워드 None → 가장 긴 OCR 텍스트를 자동 선택
# ─────────────────────────────────────────────────────────────────────────────
IMAGE_CONFIGS = [
    # ── 라디오 버튼 ──────────────────────────────────────────────────────────
    # qa1: Navigation mode — 3-button(SELECTED) vs Gesture(NOT)
    ("captures/probe/qa1.jpg",    "3-button",       "radio",  "SELECTED"),
    ("captures/probe/qa1.jpg",    "Gesture",        "radio",  "NOT"),
    # qa3: Screen timeout — OCR가 공백 없이 "5minutes"/"1minute"으로 읽음
    ("captures/probe/qa3.jpg",    "5minutes",       "radio",  "SELECTED"),
    ("captures/probe/qa3.jpg",    "1minute",        "radio",  "NOT"),
    # qa6: Clock color & size — 왼쪽에 라디오 버튼이 없는 리스트형 UI.
    #      라벨 왼쪽 strip엔 검은 베젤뿐이라 저휘도 hue가 파랑으로 오검출(0.72/0.87).
    #      → 라디오 보정 대상에서 제외. 시계 크기는 별도 방식으로 판정 필요.
    # ("captures/probe/qa6.jpg",    "Small",          "radio",  "SELECTED"),
    # ("captures/probe/qa6.jpg",    "Dynamic",        "radio",  "NOT"),
    # ── 토글 ─────────────────────────────────────────────────────────────────
    # qa2: Battery 화면 — ON/OFF 쌍을 동일 이미지에서 확보
    #   Batterypercentage = ON (파란 토글)
    #   BatterySaver      = OFF (회색 토글, "Off" 텍스트도 OCR에서 확인됨)
    ("captures/probe/qa2.jpg",    "Batterypercentage", "toggle", "ON"),
    ("captures/probe/qa2.jpg",    "BatterySaver",      "toggle", "OFF"),
    # qa4_5: Display 화면은 색상 팔레트가 전체를 파랗게 물들여 ON/OFF 구분 불가 → 제외
    # ("captures/probe/qa4_5.jpg",  "Auto-rotate",    "toggle", "ON"),
    # ("captures/probe/qa4_5.jpg",  "Double-click",   "toggle", "OFF"),
    # ("captures/probe/qa4_5.jpg",  "Real-time",      "toggle", "OFF"),
    # qa8: Notifications 하단 — Notification dot=OFF, Enhanced=OFF(있으면)
    #   ON 샘플은 qa2의 Batterypercentage와 공유
    ("captures/probe/qa8.jpg",    "Notification dot",  "toggle", "OFF"),
    ("captures/probe/qa8.jpg",    "Enhanced",          "toggle", "OFF"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 스윕 파라미터
# ─────────────────────────────────────────────────────────────────────────────
# 라디오: 라벨 왼쪽 경계에서 오른쪽으로 띄울 여백 + 라벨 중심 y 기준 상하 범위
RADIO_LABEL_MARGIN = 10   # 라벨 x0 에서 오른쪽으로 띄울 여백 (px)
RADIO_Y_PAD        = 30   # 라벨 중심 y 기준 ±px

# 토글 (A) 타이트크롭: 알약 주변 좁은 창 시작 x 비율을 스윕
TOGGLE_X_FRACS  = [0.82, 0.85, 0.88, 0.90, 0.92]
# 토글 (S, V) 임계값 스윕 — 쿨화이트 배경(낮은 S)을 배제할 조합 탐색
TOGGLE_SAT_MINS = [60, 80, 100, 120]
TOGGLE_VAL_MINS = [0, 60, 100]

# ── HSV 파랑 범위 ────────────────────────────────────────────────────────────
HUE_LOW        = 85
HUE_HIGH       = 135
RADIO_SAT_MIN  = 40   # 라디오: S 분포 40~131, mean=54 → 40으로 낮춰야 점 포착

# ── OCR 설정 ─────────────────────────────────────────────────────────────────
OCR_CONF      = 0.4
FUZZY_MIN_LEN = 4
FUZZY_THRESH  = 0.92   # 높게 유지 — "1minute"/"2minutes" 등이 "5minutes"에 오매칭되는 것 방지

# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
_SPLIT_RE = re.compile(r'[\s\-_,./]+')


def _fuzzy_match(text: str, keyword: str) -> bool:
    t  = text.lower().strip()
    kw = keyword.lower().strip()
    words = _SPLIT_RE.split(t)
    if kw in words or kw in t:
        return True
    for w in words:
        if len(w) >= FUZZY_MIN_LEN and SequenceMatcher(None, w, kw).ratio() >= FUZZY_THRESH:
            return True
    return False


def _bbox_bounds(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def _bbox_center(bbox):
    x0, y0, x1, y1 = _bbox_bounds(bbox)
    return (x0 + x1) // 2, (y0 + y1) // 2


def _blue_ratio(crop: np.ndarray, sat_min: int, val_min: int = 0) -> float:
    """크롭 영역에서 파란 픽셀(HSV 기준) 비율 반환."""
    if crop.size == 0:
        return 0.0
    hsv  = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 0] >= HUE_LOW)  &
        (hsv[:, :, 0] <= HUE_HIGH) &
        (hsv[:, :, 1] >= sat_min)  &
        (hsv[:, :, 2] >= val_min)
    )
    return float(np.count_nonzero(mask)) / mask.size


def _hsv_stats(crop: np.ndarray):
    """크롭에서 채도 40 이상인 유색 픽셀의 HSV 통계를 문자열로 반환."""
    if crop.size == 0:
        return "(빈 크롭)"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    colored = hsv[hsv[:, :, 1] >= 40]
    if len(colored) == 0:
        return "(유색 픽셀 없음 — 전체 회색/흰색)"
    h = colored[:, 0]
    s = colored[:, 1]
    v = colored[:, 2]
    return (f"H={int(h.min())}~{int(h.max())} (mean={h.mean():.0f})  "
            f"S={int(s.min())}~{int(s.max())} (mean={s.mean():.0f})  "
            f"V={int(v.min())}~{int(v.max())} (mean={v.mean():.0f})  "
            f"n={len(colored)}")


def _find_label(ocr_results, keyword):
    for bbox, text, conf in ocr_results:
        if conf < OCR_CONF:
            continue
        if _fuzzy_match(text, keyword):
            return bbox, text, conf
    return None, None, None


def _run_ocr(img: np.ndarray):
    results = ocr_readtext(img)
    return [(bbox, text, conf) for bbox, text, conf in results if conf >= OCR_CONF]


# ─────────────────────────────────────────────────────────────────────────────
# 라디오 버튼 분석  (라벨 왼쪽 전체 영역 크롭 — 버튼 위치 무관)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_radio(img: np.ndarray, label: str, expected: str, img_stem: str,
                  debug_img: np.ndarray) -> float | None:
    h, w = img.shape[:2]
    ocr_results = _run_ocr(img)

    bbox, text, conf = _find_label(ocr_results, label)
    if bbox is None:
        print(f"  [라디오] '{label}' 미발견 (파일: {img_stem})")
        print(f"           발견된 텍스트: {[t for _,t,_ in ocr_results][:10]}")
        return None

    cx, cy = _bbox_center(bbox)
    x0b, y0b, x1b, y1b = _bbox_bounds(bbox)

    # 라벨 왼쪽 전체를 크롭: x=[0, x0b - margin], y=[cy - pad, cy + pad]
    rx0 = 0
    rx1 = max(0, x0b - RADIO_LABEL_MARGIN)
    ry0 = max(0, cy - RADIO_Y_PAD)
    ry1 = min(h, cy + RADIO_Y_PAD)
    crop = img[ry0:ry1, rx0:rx1]
    ratio = _blue_ratio(crop, RADIO_SAT_MIN)

    print(f"  [라디오] 라벨='{text}' (conf={conf:.2f})  center=({cx},{cy})  예상={expected}")
    print(f"           탐색 영역: x=[{rx0},{rx1}] y=[{ry0},{ry1}]  ratio={ratio:.4f}")

    # HSV 통계 (SELECTED만)
    if expected == "SELECTED":
        print(f"           [HSV 통계] {_hsv_stats(crop)}")
        print(f"           [HSV 현재 범위: H {HUE_LOW}~{HUE_HIGH}, S>={RADIO_SAT_MIN}]")

    # 디버그 이미지: 탐색 영역 박스 (선택=초록, 미선택=빨강)
    box_color = (0, 200, 0) if expected == "SELECTED" else (0, 0, 200)
    cv2.rectangle(debug_img, (rx0, ry0), (rx1, ry1), box_color, 2)

    # 파란 픽셀 위치를 청록(0,255,255)으로 overlay
    if crop.size > 0:
        hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        blue_mask = (
            (hsv_crop[:, :, 0] >= HUE_LOW)  &
            (hsv_crop[:, :, 0] <= HUE_HIGH) &
            (hsv_crop[:, :, 1] >= RADIO_SAT_MIN)
        )
        overlay_region = debug_img[ry0:ry1, rx0:rx1]
        overlay_region[blue_mask] = (0, 220, 220)

    # 라벨 bbox
    cv2.rectangle(debug_img, (x0b, y0b), (x1b, y1b), (200, 200, 0), 1)
    cv2.putText(debug_img, f"{expected} {ratio:.3f}", (x0b, y0b - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 0), 1)

    return ratio


# ─────────────────────────────────────────────────────────────────────────────
# 토글 분석  (프레임 폭의 frac 지점 ~ 오른쪽 끝 크롭)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_toggle(img: np.ndarray, label, expected: str, img_stem: str,
                   debug_img: np.ndarray):
    h, w = img.shape[:2]
    ocr_results = _run_ocr(img)

    if not ocr_results:
        print(f"  [토글] OCR 결과 없음 (파일: {img_stem})")
        return None

    if label is not None:
        bbox, text, conf = _find_label(ocr_results, label)
        if bbox is None:
            print(f"  [토글] '{label}' 미발견. 발견된 텍스트: {[t for _,t,_ in ocr_results][:8]}")
            bbox, text, conf = max(ocr_results, key=lambda x: len(x[1]))
    else:
        bbox, text, conf = max(ocr_results, key=lambda x: len(x[1]))

    x0b, y0b, x1b, y1b = _bbox_bounds(bbox)
    row_pad = 10
    y_top = max(0, y0b - row_pad)
    y_bot = min(h, y1b + row_pad)

    print(f"  [토글] 기준 라벨='{text}' (conf={conf:.2f})  "
          f"y=[{y_top},{y_bot}]  예상={expected}")
    print(f"         발견된 텍스트: {[t for _,t,_ in ocr_results][:10]}")

    # (frac, sat, val) 모든 조합의 파랑 비율 측정
    results = {}
    for frac in TOGGLE_X_FRACS:
        x_start = int(w * frac)
        crop    = img[y_top:y_bot, x_start:w]
        for sat in TOGGLE_SAT_MINS:
            for val in TOGGLE_VAL_MINS:
                results[(frac, sat, val)] = _blue_ratio(crop, sat, val)

        color = (0, 200, 0) if expected == "ON" else (0, 0, 200)
        cv2.rectangle(debug_img, (x_start, y_top), (w - 1, y_bot), color, 1)
        if abs(frac - 0.88) < 0.01:   # frac=0.88 강조 (새 기본값 후보)
            cv2.rectangle(debug_img, (x_start-1, y_top-1), (w, y_bot+1), (0, 255, 255), 2)

    cv2.rectangle(debug_img, (x0b, y0b), (x1b, y1b), (200, 200, 0), 1)
    cv2.putText(debug_img, expected, (x0b, y0b - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 0), 1)

    # 요약 테이블: 고정 sat=100, val=60 기준으로 frac별 비율 (가독성용)
    ref_sat, ref_val = 100, 60
    print(f"    [참고 sat={ref_sat},val={ref_val}]  "
          f"{'frac':>5} | " + " | ".join(f"{f:.2f}" for f in TOGGLE_X_FRACS))
    print(f"    {'':>22}{'ratio':>5} | "
          + " | ".join(f"{results[(f, ref_sat, ref_val)]:.3f}" for f in TOGGLE_X_FRACS))

    if expected == "ON":
        x_mid = int(w * TOGGLE_X_FRACS[len(TOGGLE_X_FRACS)//2])
        print(f"    [HSV 통계 ON 크롭] {_hsv_stats(img[y_top:y_bot, x_mid:w])}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# 권장값 계산
# ─────────────────────────────────────────────────────────────────────────────

def recommend_radio(collected):
    # collected: [(expected, float), ...]
    if not collected:
        return

    # 카드형 UI(ratio > 0.9) 자동 제외
    sel_r  = [r for e, r in collected if e == "SELECTED" and r < 0.9]
    not_r  = [r for e, r in collected if e == "NOT"      and r < 0.9]
    n_excluded = sum(1 for _, r in collected if r >= 0.9)
    if n_excluded:
        print(f"\n  [주의] {n_excluded}개 샘플 ratio>=0.9 → 카드형 UI로 판단, 제외함")

    if not sel_r or not not_r:
        print("  [권장] 유효한 라디오 버튼 샘플 없음 — 카드형 UI 샘플만 존재")
        return

    sel_min  = min(sel_r)
    not_max  = max(not_r)
    margin   = sel_min - not_max
    threshold = (sel_min + not_max) / 2

    print(f"\n  [권장 라디오] RADIO_ON_RATIO = {threshold:.4f}  "
          f"(SELECTED min={sel_min:.4f}, NOT max={not_max:.4f}, margin={margin:.4f})")
    if margin <= 0:
        print("  [경고] margin <= 0 — SELECTED/NOT 비율이 겹침. HSV 범위 또는 영역 재확인 필요")


def recommend_toggle(collected):
    if not collected:
        return
    on_  = [(e, r) for e, r in collected if e == "ON"]
    off_ = [(e, r) for e, r in collected if e == "OFF"]
    if not on_ or not off_:
        print("\n  [권장] ON/OFF 양쪽 필요")
        return

    # (frac, sat, val) 모든 조합에서 ON/OFF margin 최대 조합 탐색
    best = None  # (margin, frac, sat, val, on_min, off_max)
    for frac in TOGGLE_X_FRACS:
        for sat in TOGGLE_SAT_MINS:
            for val in TOGGLE_VAL_MINS:
                key   = (frac, sat, val)
                on_r  = [r[key] for _, r in on_  if key in r]
                off_r = [r[key] for _, r in off_ if key in r]
                if not on_r or not off_r:
                    continue
                on_min, off_max = min(on_r), max(off_r)
                margin = on_min - off_max
                if best is None or margin > best[0]:
                    best = (margin, frac, sat, val, on_min, off_max)

    if best is None:
        print("\n  [권장] 조합 비교 실패")
        return

    margin, frac, sat, val, on_min, off_max = best
    threshold = (on_min + off_max) / 2
    print(f"\n  [권장 토글] TOGGLE_X_FRAC = {frac:.2f}  "
          f"(화면 폭의 {frac*100:.0f}% 지점부터 오른쪽 끝 크롭)")
    print(f"             ON_SAT_MIN    = {sat}")
    print(f"             ON_VAL_MIN    = {val}")
    print(f"             ON_PIX_RATIO  = {threshold:.3f}  "
          f"(ON min={on_min:.3f}, OFF max={off_max:.3f}, margin={margin:.3f})")
    if margin <= 0:
        print("  [경고] 최선 조합도 margin<=0 — 알약 위치 재확인 또는 blob 방식(B) 검토 필요")


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    radio_collected  = []
    toggle_collected = []

    # 한 파일당 debug_img는 첫 처리 시 생성, 같은 파일의 후속 항목에 누적
    debug_cache = {}   # path → debug_img (ndarray)

    for path, label, kind, expected in IMAGE_CONFIGS:
        if not os.path.exists(path):
            print(f"\n[SKIP] 파일 없음: {path}")
            continue

        img = cv2.imread(path)
        if img is None:
            print(f"\n[SKIP] 이미지 로드 실패: {path}")
            continue

        stem = os.path.splitext(os.path.basename(path))[0]
        safe_stem = re.sub(r'[^\w\-]', '_', stem)

        if path not in debug_cache:
            debug_cache[path] = img.copy()
        debug_img = debug_cache[path]

        print(f"\n{'='*64}")
        print(f"[{kind.upper()}] {path}  label='{label}'  ({expected})")
        print(f"{'='*64}")

        if kind == "radio":
            ratio = analyze_radio(img, label, expected, stem, debug_img)
            if ratio is not None:
                radio_collected.append((expected, ratio))
        elif kind == "toggle":
            results = analyze_toggle(img, label, expected, stem, debug_img)
            if results:
                toggle_collected.append((expected, results))

    # 디버그 이미지 저장 (파일당 한 번)
    print(f"\n{'='*64}")
    print("디버그 이미지 저장:")
    for path, debug_img in debug_cache.items():
        stem = os.path.splitext(os.path.basename(path))[0]
        safe_stem = re.sub(r'[^\w\-]', '_', stem)
        debug_path = os.path.join("captures", f"debug_{safe_stem}.jpg")
        cv2.imwrite(debug_path, debug_img)
        print(f"  → {debug_path}")

    # ── 최종 권장값 ────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("최종 권장값")
    print(f"{'='*64}")
    recommend_radio(radio_collected)
    recommend_toggle(toggle_collected)

    print(f"\n{'='*64}")
    print("lib/qa.py 상단 상수에 반영:")
    print("  RADIO_ON_RATIO  =  (위 [권장 라디오] RADIO_ON_RATIO)")
    print("  TOGGLE_X_FRAC   =  (위 [권장 토글] TOGGLE_X_FRAC)   ← 폭 비율")
    print("  ON_SAT_MIN      =  (위 [권장 토글] ON_SAT_MIN)")
    print("  ON_VAL_MIN      =  (위 [권장 토글] ON_VAL_MIN)")
    print("  ON_PIX_RATIO    =  (위 [권장 토글] ON_PIX_RATIO)")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
