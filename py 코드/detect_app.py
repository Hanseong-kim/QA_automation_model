"""
detect_apps.py - OCR로 화면의 앱들을 인식하고 위치 구분

윗줄 앱들(Radius, Files, Knox Remote, Chrome)을 OCR로 읽어서
각 앱의 이름 + 화면위치(회전후 x,y) + 왼쪽부터 순서를 출력.

조작:
  d : 앱 감지 (현재 화면 OCR -> 앱 목록 + 위치 + 순서)
  s : 결과 이미지 저장 (image2)
  q : 종료

타겟 앱 이름들(이것만 앱으로 인정, 나머지 글자는 무시):
  Radius, Files, Knox, Chrome
"""
import cv2, numpy as np, easyocr, re, time
from difflib import SequenceMatcher

STREAM_URL = "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto/image2"
OCR_CONF = 0.4

# 인식할 앱 이름들 (소문자). OCR이 일부만 읽어도 매칭되게 키워드로.
APP_KEYWORDS = {
    "radius": "Radius",
    "files":  "Files",
    "knox":   "Knox Remote",
    "chrome": "Chrome",
}
# Remove 방향 (앱별 고정 규칙)
REMOVE_DIR = {
    "Radius":      "위",
    "Knox Remote": "위",
    "Files":       "아래",
    "Chrome":      "아래",
}

cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
print("EasyOCR 로딩...")
reader = easyocr.Reader(['en'])
print("d=앱감지  s=저장  q=종료\n")

def grab(flush=10):
    for _ in range(flush): cap.grab()
    ret, f = cap.read(); return f if ret else None

def match_app(text):
    """OCR 텍스트가 어떤 앱인지. 매칭되면 앱 정식이름, 아니면 None."""
    t = text.lower().strip()
    words = re.split(r'[\s\-_,./]+', t)
    for kw, name in APP_KEYWORDS.items():
        # 정확 단어 포함
        if kw in words or kw in t:
            return name
        # 유사 매칭 (오인식 대비)
        for w in words:
            if len(w) >= 4 and SequenceMatcher(None, w, kw).ratio() >= 0.8:
                return name
    return None

def detect():
    frame = grab(12)
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    results = reader.readtext(rot)
    raw = []
    for (bbox, text, conf) in results:
        if conf <= OCR_CONF: continue
        name = match_app(text)
        if name is None: continue
        cx = int((bbox[0][0]+bbox[2][0])/2)
        cy = int((bbox[0][1]+bbox[2][1])/2)
        raw.append((name, cx, cy, conf, bbox))

    # 1) 윗줄 앱만: y가 앱 줄 범위 안. 진짜 앱은 y≈400.
    #    가장 많은 앱이 모인 y대역을 자동으로 찾아서 그 줄만.
    if raw:
        ys = sorted([r[2] for r in raw])
        # 중앙값 기준 +-120 안의 것만 (한 줄)
        med_y = ys[len(ys)//2]
        raw = [r for r in raw if abs(r[2] - med_y) <= 120]

    # 2) 같은 앱 이름은 conf 높은 것 하나만 (중복 제거)
    best = {}
    for (name, cx, cy, conf, bbox) in raw:
        if name not in best or conf > best[name][2]:
            best[name] = (cx, cy, conf, bbox)
    apps = [(name, v[0], v[1], v[2], v[3]) for name, v in best.items()]
    apps.sort(key=lambda a: a[1])   # 왼쪽->오른쪽

    vis = rot.copy()
    print(f"\n=== 감지된 앱 {len(apps)}개 (왼쪽->오른쪽) ===")
    for i, (name, cx, cy, conf, bbox) in enumerate(apps):
        d = REMOVE_DIR.get(name, "?")
        print(f"  {i+1}번: {name}  위치(x={cx},y={cy})  conf={conf:.2f}  Remove방향={d}")
        pts = np.array(bbox, dtype=np.int32)
        cv2.polylines(vis, [pts], True, (0,255,0), 2)
        cv2.putText(vis, name, (pts[0][0], pts[0][1]-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
    return vis, apps

last_vis = None
while True:
    f = grab(2)
    if f is None: time.sleep(0.2); continue
    rot = cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE)
    cv2.imshow("detect", last_vis if last_vis is not None else rot)
    k = cv2.waitKey(30) & 0xFF
    if k == ord('d'):
        last_vis, apps = detect()
    elif k == ord('s'):
        if last_vis is not None:
            cv2.imwrite(f"{OUT}/detect_apps.jpg", last_vis)
            print(f"저장: {OUT}/detect_apps.jpg")
    elif k == ord('q'):
        break

cap.release(); cv2.destroyAllWindows()