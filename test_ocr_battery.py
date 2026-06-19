"""test_ocr_battery.py — 배터리 % OCR 검출 가능 여부 확인

captures/battery_on.jpg  : 배터리 % 표시 ON 상태 캡처
captures/battery_off.jpg : 배터리 % 표시 OFF 상태 캡처

read_screen_text와 동일한 전처리(90도 CW 회전 → reader.readtext)를 적용하고
OCR 결과를 전부 출력한다. "%" 또는 숫자가 ON에서 잡히고 OFF에서 안 잡히면
OCR 단독 판정이 가능하다는 뜻.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
from lib.vision import ocr_readtext
from lib.config import OCR_CONF

IMAGES = {
    "ON":  "captures/battery_on.jpg",
    "OFF": "captures/battery_off.jpg",
}

CHECK_KEYWORDS = ["%", "84", "battery", "percentage"]


def ocr_from_file(path: str) -> list:
    """이미지 파일을 읽어 read_screen_text와 동일한 전처리 후 OCR 결과 반환."""
    frame = cv2.imread(path)
    if frame is None:
        print(f"  [오류] 파일을 읽을 수 없음: {path}")
        return []
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    results = []
    for (bbox, text, conf) in ocr_readtext(rot):
        results.append((text, conf))
    return results


def run():
    hit_summary = {}

    for label, path in IMAGES.items():
        print(f"\n{'='*50}")
        print(f"  [{label}] {path}")
        print(f"{'='*50}")

        results = ocr_from_file(path)
        if not results:
            hit_summary[label] = []
            continue

        print(f"  총 {len(results)}개 텍스트 검출 (OCR_CONF 필터 없음, 전체 출력):\n")

        hits = []
        for text, conf in sorted(results, key=lambda x: -x[1]):
            flag = ""
            for kw in CHECK_KEYWORDS:
                if kw.lower() in text.lower():
                    flag = f"  ◀ '{kw}' 포함"
                    hits.append((kw, text, conf))
                    break
            marker = "  ✓" if conf >= OCR_CONF else "  ·"
            print(f"  {marker} conf={conf:.2f}  '{text}'{flag}")

        hit_summary[label] = hits

    print(f"\n{'='*50}")
    print("  판정 요약")
    print(f"{'='*50}")
    for label, hits in hit_summary.items():
        if hits:
            kws = ", ".join(f"'{kw}'→'{txt}'({c:.2f})" for kw, txt, c in hits)
            print(f"  [{label}] 키워드 검출: {kws}")
        else:
            print(f"  [{label}] 키워드 미검출")

    on_hits  = bool(hit_summary.get("ON"))
    off_hits = bool(hit_summary.get("OFF"))

    print()
    if on_hits and not off_hits:
        print("  결론: OCR로 배터리 % 유무 판별 가능 (ON에서 검출, OFF에서 미검출)")
    elif on_hits and off_hits:
        print("  결론: ON/OFF 모두 검출 — OCR 단독 판별 어려움, 픽셀 색상 병용 필요")
    elif not on_hits and not off_hits:
        print("  결론: 양쪽 모두 미검출 — 이미지 확인 또는 신뢰도 임계값 조정 필요")
    else:
        print("  결론: ON에서만 미검출 — 이미지 상태 또는 OCR 해상도 확인 필요")


if __name__ == "__main__":
    run()
