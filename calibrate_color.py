"""calibrate_color.py -- RADIO / TOGGLE ratio threshold calibration script

Usage: .\\venv\\Scripts\\python.exe calibrate_color.py
Output:
  - Console: per-image blue-pixel ratio table + recommended thresholds + HSV range check
  - captures/debug_<stem>.jpg: debug image with crop regions drawn
Assumption: images are already in screen orientation (portrait, 90-deg CW rotated).
"""

import os
import re

import cv2
import numpy as np
from difflib import SequenceMatcher

from lib.vision import ocr_readtext

# ---------------------------------------------------------------------------
# Image configs  (path, label_keyword, kind, expected_state)
#   kind: "radio" / "toggle"
#   expected_state radio:  "SELECTED" / "NOT"
#   expected_state toggle: "ON" / "OFF"
#   label_keyword None -> auto-select longest OCR text
# ---------------------------------------------------------------------------
IMAGE_CONFIGS = [
    # -- radio buttons -------------------------------------------------------
    # qa1: Navigation mode -- 3-button(SELECTED) vs Gesture(NOT)
    ("captures/probe/qa1.jpg",    "3-button",       "radio",  "SELECTED"),
    ("captures/probe/qa1.jpg",    "Gesture",        "radio",  "NOT"),
    # qa3: Screen timeout -- OCR reads without space "5minutes"/"1minute"
    ("captures/probe/qa3.jpg",    "5minutes",       "radio",  "SELECTED"),
    ("captures/probe/qa3.jpg",    "1minute",        "radio",  "NOT"),
    # qa6: Clock color & size -- Small has standard blue radio dot on left.
    #      Dark navy preview box above causes false positive (0.72/0.87)
    #      without S+V lower bound -> RADIO_SAT_MINS + RADIO_VAL_MINS sweep.
    ("captures/probe/qa6.jpg",    "Small",          "radio",  "SELECTED"),
    ("captures/probe/qa6.jpg",    "Dynamic",        "radio",  "NOT"),
    # -- toggle --------------------------------------------------------------
    # qa2: Battery screen -- ON/OFF pair from same image
    #   Batterypercentage = ON (blue toggle)
    #   BatterySaver      = OFF (grey toggle, "Off" text confirmed by OCR)
    ("captures/probe/qa2.jpg",    "Batterypercentage", "toggle", "ON"),
    ("captures/probe/qa2.jpg",    "BatterySaver",      "toggle", "OFF"),
    # qa4_5: Display screen color palette floods entire area blue -> excluded
    # ("captures/probe/qa4_5.jpg",  "Auto-rotate",    "toggle", "ON"),
    # ("captures/probe/qa4_5.jpg",  "Double-click",   "toggle", "OFF"),
    # ("captures/probe/qa4_5.jpg",  "Real-time",      "toggle", "OFF"),
    # qa8: Notifications bottom -- Notification dot=OFF, Enhanced=OFF
    #   ON sample shared with qa2 Batterypercentage
    ("captures/probe/qa8.jpg",    "Notification dot",  "toggle", "OFF"),
    ("captures/probe/qa8.jpg",    "Enhanced",          "toggle", "OFF"),
]

# ---------------------------------------------------------------------------
# Sweep parameters
# ---------------------------------------------------------------------------
# Radio: label left boundary margin + label center y +/- range
RADIO_LABEL_MARGIN = 10   # px to the right of label x0
RADIO_Y_PAD        = 30   # +/- px from label center y
# Radio (S, V) threshold sweep -- qa6 UI background is light blue,
# need high S to separate radio dot from ambient blue
RADIO_SAT_MINS     = [40, 90, 120, 135, 140, 145, 150]
RADIO_VAL_MINS     = [0, 100]

# Toggle (A) tight crop: pill area narrow window start x fraction sweep
TOGGLE_X_FRACS  = [0.82, 0.85, 0.88, 0.90, 0.92]
# Toggle (S, V) threshold sweep -- cool-white background exclusion
TOGGLE_SAT_MINS = [60, 80, 100, 120]
TOGGLE_VAL_MINS = [0, 60, 100]

# -- HSV blue range --------------------------------------------------------
HUE_LOW        = 85
HUE_HIGH       = 135

# -- OCR settings ----------------------------------------------------------
OCR_CONF      = 0.4
FUZZY_MIN_LEN = 4
FUZZY_THRESH  = 0.92   # high to prevent "1minute"/"2minutes" matching "5minutes"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
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
    """Blue pixel ratio (HSV) in crop region."""
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
    """HSV stats string for colored pixels (S>=40) in crop."""
    if crop.size == 0:
        return "(empty crop)"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    colored = hsv[hsv[:, :, 1] >= 40]
    if len(colored) == 0:
        return "(no colored pixels -- all grey/white)"
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


# ---------------------------------------------------------------------------
# Radio button analysis  (label-left full strip crop -- button-position agnostic)
# ---------------------------------------------------------------------------

def analyze_radio(img: np.ndarray, label: str, expected: str, img_stem: str,
                  debug_img: np.ndarray):
    """Measure label-left strip at each (S, V) combo -> {(sat,val): ratio} dict (None if label not found)."""
    h, w = img.shape[:2]
    ocr_results = _run_ocr(img)

    bbox, text, conf = _find_label(ocr_results, label)
    if bbox is None:
        print(f"  [radio] '{label}' not found (file: {img_stem})")
        print(f"          detected: {[t for _,t,_ in ocr_results][:10]}")
        return None

    cx, cy = _bbox_center(bbox)
    x0b, y0b, x1b, y1b = _bbox_bounds(bbox)

    # Crop: x=[0, x0b - margin], y=[cy - pad, cy + pad]
    rx0 = 0
    rx1 = max(0, x0b - RADIO_LABEL_MARGIN)
    ry0 = max(0, cy - RADIO_Y_PAD)
    ry1 = min(h, cy + RADIO_Y_PAD)
    crop = img[ry0:ry1, rx0:rx1]

    # (S, V) combo sweep
    ratios = {}
    for sat in RADIO_SAT_MINS:
        for val in RADIO_VAL_MINS:
            ratios[(sat, val)] = _blue_ratio(crop, sat, val)

    print(f"  [radio] label='{text}' (conf={conf:.2f})  center=({cx},{cy})  expected={expected}")
    print(f"          crop: x=[{rx0},{rx1}] y=[{ry0},{ry1}]")
    # Summary table: S vs V (show at max V for readability)
    ref_val = max(RADIO_VAL_MINS)
    print(f"          [S sweep V>={ref_val}] " + " | ".join(
        f"S>={s}:{ratios[(s,ref_val)]:.4f}" for s in RADIO_SAT_MINS))

    if expected == "SELECTED":
        print(f"          [HSV stats] {_hsv_stats(crop)}")

    # Debug image: crop region box (selected=green, not=red)
    box_color = (0, 200, 0) if expected == "SELECTED" else (0, 0, 200)
    cv2.rectangle(debug_img, (rx0, ry0), (rx1, ry1), box_color, 2)

    # Blue pixel overlay in cyan (highest S + V thresholds -- surviving pixels)
    if crop.size > 0:
        hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        blue_mask = (
            (hsv_crop[:, :, 0] >= HUE_LOW)  &
            (hsv_crop[:, :, 0] <= HUE_HIGH) &
            (hsv_crop[:, :, 1] >= max(RADIO_SAT_MINS)) &
            (hsv_crop[:, :, 2] >= max(RADIO_VAL_MINS))
        )
        overlay_region = debug_img[ry0:ry1, rx0:rx1]
        overlay_region[blue_mask] = (0, 220, 220)

    # Label bbox
    cv2.rectangle(debug_img, (x0b, y0b), (x1b, y1b), (200, 200, 0), 1)
    best_key = (max(RADIO_SAT_MINS), max(RADIO_VAL_MINS))
    cv2.putText(debug_img, f"{expected} {ratios[best_key]:.3f}", (x0b, y0b - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 0), 1)

    return ratios


# ---------------------------------------------------------------------------
# Toggle analysis  (frame width frac point ~ right edge crop)
# ---------------------------------------------------------------------------

def analyze_toggle(img: np.ndarray, label, expected: str, img_stem: str,
                   debug_img: np.ndarray):
    h, w = img.shape[:2]
    ocr_results = _run_ocr(img)

    if not ocr_results:
        print(f"  [toggle] no OCR results (file: {img_stem})")
        return None

    if label is not None:
        bbox, text, conf = _find_label(ocr_results, label)
        if bbox is None:
            print(f"  [toggle] '{label}' not found. detected: {[t for _,t,_ in ocr_results][:8]}")
            bbox, text, conf = max(ocr_results, key=lambda x: len(x[1]))
    else:
        bbox, text, conf = max(ocr_results, key=lambda x: len(x[1]))

    x0b, y0b, x1b, y1b = _bbox_bounds(bbox)
    row_pad = 10
    y_top = max(0, y0b - row_pad)
    y_bot = min(h, y1b + row_pad)

    print(f"  [toggle] ref label='{text}' (conf={conf:.2f})  "
          f"y=[{y_top},{y_bot}]  expected={expected}")
    print(f"           detected: {[t for _,t,_ in ocr_results][:10]}")

    # (frac, sat, val) all-combo blue ratio
    results = {}
    for frac in TOGGLE_X_FRACS:
        x_start = int(w * frac)
        crop    = img[y_top:y_bot, x_start:w]
        for sat in TOGGLE_SAT_MINS:
            for val in TOGGLE_VAL_MINS:
                results[(frac, sat, val)] = _blue_ratio(crop, sat, val)

        color = (0, 200, 0) if expected == "ON" else (0, 0, 200)
        cv2.rectangle(debug_img, (x_start, y_top), (w - 1, y_bot), color, 1)
        if abs(frac - 0.88) < 0.01:   # highlight frac=0.88
            cv2.rectangle(debug_img, (x_start-1, y_top-1), (w, y_bot+1), (0, 255, 255), 2)

    cv2.rectangle(debug_img, (x0b, y0b), (x1b, y1b), (200, 200, 0), 1)
    cv2.putText(debug_img, expected, (x0b, y0b - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 0), 1)

    # Summary: fixed sat=100, val=60 across fracs
    ref_sat, ref_val = 100, 60
    print(f"    [ref sat={ref_sat},val={ref_val}]  "
          f"{'frac':>5} | " + " | ".join(f"{f:.2f}" for f in TOGGLE_X_FRACS))
    print(f"    {'':>22}{'ratio':>5} | "
          + " | ".join(f"{results[(f, ref_sat, ref_val)]:.3f}" for f in TOGGLE_X_FRACS))

    if expected == "ON":
        x_mid = int(w * TOGGLE_X_FRACS[len(TOGGLE_X_FRACS)//2])
        print(f"    [HSV stats ON crop] {_hsv_stats(img[y_top:y_bot, x_mid:w])}")

    return results


# ---------------------------------------------------------------------------
# Recommended values
# ---------------------------------------------------------------------------

def recommend_radio(collected):
    # collected: [(expected, {(sat,val): ratio}), ...]
    if not collected:
        return
    sel_ = [(e, r) for e, r in collected if e == "SELECTED"]
    not_ = [(e, r) for e, r in collected if e == "NOT"]
    if not sel_ or not not_:
        print("\n  [recommend] need both SELECTED and NOT samples")
        return

    # (sat, val) sweep -- find combo with max margin (exclude ratio>=0.9 card-type UI)
    best = None  # (margin, sat, val, sel_min, not_max)
    for sat in RADIO_SAT_MINS:
        for val in RADIO_VAL_MINS:
            key = (sat, val)
            sel_r = [r[key] for _, r in sel_ if key in r and r[key] < 0.9]
            not_r = [r[key] for _, r in not_ if key in r and r[key] < 0.9]
            if not sel_r or not not_r:
                continue
            sel_min, not_max = min(sel_r), max(not_r)
            margin = sel_min - not_max
            if best is None or margin > best[0]:
                best = (margin, sat, val, sel_min, not_max)

    if best is None:
        print("\n  [recommend radio] no valid combo -- all card-type (ratio>=0.9) or missing")
        return

    margin, sat, val, sel_min, not_max = best
    threshold = (sel_min + not_max) / 2
    print(f"\n  [recommend radio] RADIO_SAT_MIN  = {sat}")
    print(f"                    RADIO_VAL_MIN  = {val}")
    print(f"                    RADIO_ON_RATIO = {threshold:.4f}  "
          f"(SELECTED min={sel_min:.4f}, NOT max={not_max:.4f}, margin={margin:.4f})")
    if margin <= 0:
        print("  [WARNING] best combo margin <= 0 -- check HSV range or crop area")


def recommend_toggle(collected):
    if not collected:
        return
    on_  = [(e, r) for e, r in collected if e == "ON"]
    off_ = [(e, r) for e, r in collected if e == "OFF"]
    if not on_ or not off_:
        print("\n  [recommend] need both ON and OFF samples")
        return

    # (frac, sat, val) all-combo ON/OFF margin search
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
        print("\n  [recommend] combo comparison failed")
        return

    margin, frac, sat, val, on_min, off_max = best
    threshold = (on_min + off_max) / 2
    print(f"\n  [recommend toggle] TOGGLE_X_FRAC = {frac:.2f}  "
          f"(screen width {frac*100:.0f}% to right edge crop)")
    print(f"                     ON_SAT_MIN    = {sat}")
    print(f"                     ON_VAL_MIN    = {val}")
    print(f"                     ON_PIX_RATIO  = {threshold:.3f}  "
          f"(ON min={on_min:.3f}, OFF max={off_max:.3f}, margin={margin:.3f})")
    if margin <= 0:
        print("  [WARNING] best combo margin<=0 -- check pill position or try blob method")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    radio_collected  = []
    toggle_collected = []

    # One debug_img per file, accumulated across items from same file
    debug_cache = {}   # path -> debug_img (ndarray)

    for path, label, kind, expected in IMAGE_CONFIGS:
        if not os.path.exists(path):
            print(f"\n[SKIP] file not found: {path}")
            continue

        img = cv2.imread(path)
        if img is None:
            print(f"\n[SKIP] image load failed: {path}")
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
            ratios = analyze_radio(img, label, expected, stem, debug_img)
            if ratios is not None:
                radio_collected.append((expected, ratios))
        elif kind == "toggle":
            results = analyze_toggle(img, label, expected, stem, debug_img)
            if results:
                toggle_collected.append((expected, results))

    # Save debug images (once per file)
    print(f"\n{'='*64}")
    print("Debug images saved:")
    for path, debug_img in debug_cache.items():
        stem = os.path.splitext(os.path.basename(path))[0]
        safe_stem = re.sub(r'[^\w\-]', '_', stem)
        debug_path = os.path.join("captures", f"debug_{safe_stem}.jpg")
        cv2.imwrite(debug_path, debug_img)
        print(f"  -> {debug_path}")

    # -- Final recommended values -------------------------------------------
    print(f"\n{'='*64}")
    print("Recommended values")
    print(f"{'='*64}")
    recommend_radio(radio_collected)
    recommend_toggle(toggle_collected)

    print(f"\n{'='*64}")
    print("Apply to lib/qa.py constants:")
    print("  RADIO_SAT_MIN   =  (see [recommend radio] above)")
    print("  RADIO_VAL_MIN   =  (see [recommend radio] above)")
    print("  RADIO_ON_RATIO  =  (see [recommend radio] above)")
    print("  TOGGLE_X_FRAC   =  (see [recommend toggle] above)")
    print("  ON_SAT_MIN      =  (see [recommend toggle] above)")
    print("  ON_VAL_MIN      =  (see [recommend toggle] above)")
    print("  ON_PIX_RATIO    =  (see [recommend toggle] above)")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
