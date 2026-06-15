"""
ocr_debug.py - OCR가 실제로 무엇을 읽는지 시각화해서 저장

목적: "왜 4번째 앱이 안 잡히나"를 눈으로 확인.
  - IP Webcam의 /shot.jpg로 단일 정지 프레임 캡처 (MJPEG 스트림 깨짐 회피)
  - 회전 후 EasyOCR 실행
  - 매칭 여부와 무관하게 '모든' 텍스트 박스를 이미지에 그려 저장
  - 콘솔에 각 텍스트의 conf, 매칭 결과 출력

색깔:
  초록 = 앱 매칭 + conf 통과 (감지 성공)
  주황 = 앱 매칭됐지만 conf 낮아서 버려짐  <- 이게 범인이면 OCR_CONF 낮추기
  빨강 = 앱 키워드에 매칭 안 됨            <- 이게 범인이면 키워드/철자 문제

실행: python ocr_debug.py
"""
import cv2, numpy as np, requests, easyocr, re, time
from difflib import SequenceMatcher

BASE_URL = "http://192.168.1.205:8080"
OCR_CONF = 0.4
APP_KEYWORDS = {"radius": "Radius", "knox": "Knox Remote", "files": "Files", "chrome": "Chrome"}

def match_app(text):
    t = text.lower().strip()
    words = re.split(r'[\s\-_,./]+', t)
    for kw, name in APP_KEYWORDS.items():
        if kw in words or kw in t:
            return name
        for w in words:
            if len(w) >= 4 and SequenceMatcher(None, w, kw).ratio() >= 0.8:
                return name
    return None

def grab_still():
    """IP Webcam 정지 프레임 1장."""
    r = requests.get(f"{BASE_URL}/shot.jpg", timeout=5)
    r.raise_for_status()
    arr = np.frombuffer(r.content, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def main():
    # 포커스 한 번 잡기
    try:
        requests.get(f"{BASE_URL}/settings/focusmode", params={"set": "auto"}, timeout=5)
        requests.get(f"{BASE_URL}/focus", timeout=5)
        time.sleep(1.5)
        print("focus locked")
    except Exception as e:
        print(f"포커스 트리거 실패: {e}")

    print("EasyOCR 로딩...")
    reader = easyocr.Reader(['en'])

    frame = grab_still()
    if frame is None:
        print("프레임 캡처 실패 (BASE_URL / 포트 확인)")
        return
    print(f"원본 해상도: {frame.shape[1]}x{frame.shape[0]}")

    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    results = reader.readtext(rot)

    print(f"\n=== OCR 원시 결과 (총 {len(results)}개) ===")
    vis = rot.copy()
    for (bbox, text, conf) in results:
        name = match_app(text)
        matched = name is not None
        passed = conf > OCR_CONF
        flag = "OK " if (matched and passed) else "   "
        tag = f"-> {name}" if matched else ""
        print(f"{flag}conf={conf:.2f}  '{text}'  {tag}")

        pts = np.array(bbox, dtype=np.int32)
        if matched and passed:
            color = (0, 255, 0)      # 초록
        elif matched:
            color = (0, 165, 255)    # 주황
        else:
            color = (0, 0, 255)      # 빨강
        cv2.polylines(vis, [pts], True, color, 2)
        x, y = pts[0]
        cv2.putText(vis, f"{text} {conf:.2f}", (int(x), max(int(y) - 5, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    cv2.imwrite("ocr_debug_raw.png", rot)
    cv2.imwrite("ocr_debug_annotated.png", vis)
    print("\n저장 완료: ocr_debug_raw.png (원본), ocr_debug_annotated.png (박스표시)")
    print("초록=감지성공 / 주황=앱이지만 conf낮음 / 빨강=매칭안됨")

if __name__ == "__main__":
    main()