"""identify_screens.py — captures/probe/ JPG OCR → QA 항목 자동 매핑

실행: .\\venv\\Scripts\\python.exe identify_screens.py
"""

import os
import glob
import cv2
from lib.vision import ocr_readtext

PROBE_DIR = "captures/probe"
OCR_CONF  = 0.35   # calibrate보다 약간 낮게 — 화면 식별이 목적이므로 더 넓게

# ── QA 항목 정의 (항목번호, 설명, 매칭 키워드 목록) ──────────────────────────
# 키워드 중 하나라도 OCR 텍스트에 포함되면 매칭
QA_ITEMS = [
    (1,  "3-button navigation",    ["3-button", "navigation mode", "gesture"]),
    (2,  "배터리% 표시",            ["battery percentage", "battery", "charge"]),
    (3,  "Screen timeout 5분",     ["screen timeout", "15 seconds", "30 seconds",
                                    "1 minute", "5 minutes", "10 minutes"]),
    (4,  "Real-time network speed", ["real-time", "real time", "network speed"]),
    (5,  "Double-click OFF",       ["double-click", "double click", "turn off screen"]),
    (6,  "시계 Small",              ["clock color", "clock size", "small", "dynamic"]),
    (7,  "Bubbles OFF",            ["bubbles", "bubble"]),
    (8,  "Enhanced+dot",           ["enhanced notification", "notification dot",
                                    "app icon", "dot on app"]),
]


def _keyword_in_texts(keyword: str, texts: list[str]) -> bool:
    kw = keyword.lower()
    for t in texts:
        if kw in t.lower():
            return True
    return False


def identify(texts: list[str]) -> list[int]:
    """OCR 텍스트 목록에서 매칭되는 QA 항목 번호 리스트 반환."""
    matched = []
    for num, _desc, keywords in QA_ITEMS:
        if any(_keyword_in_texts(kw, texts) for kw in keywords):
            matched.append(num)
    return matched


def main():
    jpgs = sorted(glob.glob(os.path.join(PROBE_DIR, "*.jpg")))
    if not jpgs:
        print(f"[ERROR] {PROBE_DIR}/ 에 JPG 없음")
        return

    # 파일별 결과 저장: {path: (top6_texts, matched_qa_nums)}
    file_results = {}

    print(f"\n{'='*70}")
    print(f"{'파일명':<22}  상위 6개 OCR 텍스트")
    print(f"{'='*70}")

    for path in jpgs:
        img = cv2.imread(path)
        if img is None:
            print(f"{os.path.basename(path):<22}  [이미지 로드 실패]")
            continue

        raw = ocr_readtext(img)
        # conf 기준 정렬 → 상위 6개
        filtered = [(text, conf) for _bbox, text, conf in raw if conf >= OCR_CONF]
        filtered.sort(key=lambda x: -x[1])
        top6 = [t for t, _ in filtered[:6]]

        matched = identify([t for t, _ in filtered])
        file_results[path] = (top6, matched)

        name = os.path.basename(path)
        texts_str = " | ".join(f'"{t}"' for t in top6) if top6 else "(인식 없음)"
        print(f"{name:<22}  {texts_str}")

    # ── 매핑표 출력 ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("파일 → QA 항목 매핑")
    print(f"{'='*70}")
    print(f"{'파일명':<22}  {'매칭 QA 항목'}")
    print(f"{'-'*70}")

    matched_qa_all: set[int] = set()
    for path in jpgs:
        if path not in file_results:
            continue
        top6, matched = file_results[path]
        name = os.path.basename(path)
        if matched:
            desc_list = []
            for num in matched:
                desc = next(d for n, d, _ in QA_ITEMS if n == num)
                desc_list.append(f"[{num}] {desc}")
            print(f"{name:<22}  {', '.join(desc_list)}")
            matched_qa_all.update(matched)
        else:
            print(f"{name:<22}  (매칭 없음 — OCR 결과: {top6[:3]})")

    # ── 커버리지 갭 분석 ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("커버리지 갭 (이미지가 없는 QA 항목)")
    print(f"{'='*70}")
    all_nums = {num for num, _, _ in QA_ITEMS}
    missing = all_nums - matched_qa_all
    if missing:
        for num in sorted(missing):
            desc = next(d for n, d, _ in QA_ITEMS if n == num)
            print(f"  [없음] [{num}] {desc}")
    else:
        print("  전체 커버됨")

    # ── 전체 OCR conf 포함 상세 출력 ─────────────────────────────────────────
    print(f"\n{'='*70}")
    print("파일별 전체 OCR 상세 (conf 포함, 상위 10개)")
    print(f"{'='*70}")
    for path in jpgs:
        if path not in file_results:
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        raw = ocr_readtext(img)
        filtered = [(text, conf) for _bbox, text, conf in raw if conf >= OCR_CONF]
        filtered.sort(key=lambda x: -x[1])
        print(f"\n  {os.path.basename(path)}")
        for text, conf in filtered[:10]:
            print(f"    [{conf:.2f}] {text}")


if __name__ == "__main__":
    main()
