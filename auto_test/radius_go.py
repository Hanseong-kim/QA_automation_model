"""
radius_go.py - OCR로 Radius 찾아 커서 올리기 (y 1차원 매핑)

x=100 고정, y만 변환. 가속 제거됨 -> 선형이라 점 2~3개로 정확.
커서를 영상에서 안 찾음 (OCR로 글자 위치만 봄) -> 카메라 지연/흐림 무관.

[캘리브 모드] python radius_go.py calib
  화면 글자에 커서 올리고(눈으로) 그 글자 이름 입력 -> (OCR화면y, ESP y) 쌍 저장
  위/중간/아래 3개 이상. 'done'으로 종료.

[실행 모드] python radius_go.py
  t : Radius 찾아서 커서 이동 (MOVE)
  c : MOVE <-> CLICK 토글
  l : 화면 글자 목록
  q : 종료
"""
import cv2, numpy as np, serial, time, easyocr, re, json, sys, os
from difflib import SequenceMatcher

COM_PORT = "COM7"
STREAM_URL = "http://192.168.1.205:8080/video"
# 이 스크립트와 같은 폴더에 ymap.json 저장/로드 (폴더 헷갈림 방지)
MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ymap.json")
X_FIXED = 40
TARGET = "Radius"
OCR_CONF = 0.4
SIMILARITY = 0.7

ser = serial.Serial(COM_PORT, 115200, timeout=2)
time.sleep(2); ser.reset_input_buffer()
cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
print("EasyOCR 로딩...")
reader = easyocr.Reader(['en'])

def grab():
    cap.grab(); cap.grab()
    ret, f = cap.read(); return f if ret else None

def send_wait(cmd, timeout=12):
    ser.reset_input_buffer()
    ser.write((cmd+"\n").encode())
    t0=time.time()
    while time.time()-t0<timeout:
        if ser.readline().decode(errors="ignore").strip()=="DONE": return True
    return False

def ocr_all():
    """90도 회전 OCR -> [(text, conf, screen_y)]. screen_y=회전화면 세로위치."""
    frame = grab()
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    out = []
    for (bbox, text, conf) in reader.readtext(rot):
        if conf <= OCR_CONF: continue
        sy = (bbox[0][1] + bbox[2][1]) / 2
        out.append((text, conf, sy))
    return out

def is_match(text, target):
    """정확히 'radius' 단어만. 유사매칭 줄여서 오검출 방지."""
    t, g = text.lower().strip(), target.lower()
    words = re.split(r'[\s\-_,./]+', t)
    # 1순위: 정확히 일치하는 단어
    for w in words:
        if w == g:
            return True
    # 2순위: 매우 비슷한 단어만 (Radlus 같은 오인식, 0.85+)
    for w in words:
        if len(w) >= 4 and SequenceMatcher(None, w, g).ratio() >= 0.85:
            return True
    return False

def find_y(target_text):
    """타겟 매칭. 여러 개면 정확일치 우선, 그 중 conf 높은 것."""
    items = ocr_all()
    exact = []   # 정확히 일치
    fuzzy = []   # 유사
    g = target_text.lower()
    for (t, c, sy) in items:
        words = re.split(r'[\s\-_,./]+', t.lower().strip())
        if g in words:
            exact.append((t, c, sy))
        elif is_match(t, target_text):
            fuzzy.append((t, c, sy))
    pool = exact if exact else fuzzy
    if not pool:
        return None, None
    if len(pool) > 1:
        print(f"  '{target_text}' 후보 {len(pool)}개:")
        for (t,c,sy) in pool:
            print(f"    '{t}' conf={c:.2f} y={sy:.0f}")
    # conf 가장 높은 것
    pool.sort(key=lambda x: x[1], reverse=True)
    t, c, sy = pool[0]
    return sy, t

# ===================== 캘리브 =====================
def calibrate():
    print("\n=== y 1차원 캘리브 ===")
    print(f"x={X_FIXED} 고정. 화면 글자 3개 이상(위/중간/아래)에 대해:")
    print("  1) ESP y 입력 -> 커서가 그 글자에 올라가게 조정")
    print("  2) 올라가면 그 글자 이름 입력 -> OCR이 화면y 찾아 쌍 저장")
    print("  글자이름 'done' 입력하면 종료\n")

    pairs = []
    cur_y = [0]
    while True:
        s = input("ESP y 입력 (커서이동) / 글자이름 (저장) / 'done' > ").strip()
        if s == 'done':
            break
        if s.lstrip('-').isdigit():
            y = int(s)
            send_wait(f"MOVE:{X_FIXED},{y}")
            cur_y[0] = y
            print(f"  커서 -> ESP({X_FIXED},{y}). 글자에 올라갔으면 그 글자이름 입력")
        else:
            if cur_y[0] == 0:
                print("  먼저 ESP y로 커서를 글자에 올려라"); continue
            sy, found = find_y(s)
            if sy is None:
                print(f"  OCR이 '{s}' 못 찾음. 철자 확인하거나 보이는 글자로"); continue
            pairs.append((sy, cur_y[0]))
            print(f"  저장: '{found}' 화면y={sy:.0f} <-> ESP y={cur_y[0]} (총 {len(pairs)})")

    if len(pairs) < 2:
        print("2쌍 미만 - 저장 안함"); return
    pairs.sort()
    # 단조성 검증: 화면y 증가하면 ESP y는 계속 감소해야 함
    print("\n=== 캘리브 검증 ===")
    bad = False
    for i in range(len(pairs)-1):
        sy0, ey0 = pairs[i]; sy1, ey1 = pairs[i+1]
        arrow = "OK" if ey1 < ey0 else "!! 역전(잘못됨)"
        if ey1 >= ey0: bad = True
        print(f"  화면y {sy0:.0f}->{sy1:.0f} : ESP {ey0}->{ey1}  {arrow}")
    if bad:
        print("\n[경고] ESP y가 단조감소하지 않음. 어떤 점을 잘못 찍었음.")
        ans = input("그래도 저장? (y/다시하려면 n) > ").strip().lower()
        if ans != 'y':
            print("저장 취소. calib 다시 하세요."); return
    json.dump({"x": X_FIXED, "pairs": pairs}, open(MAP_FILE, "w"))
    print(f"\n저장: {len(pairs)}쌍 -> {MAP_FILE}")
    for sy, ey in pairs:
        print(f"  화면y={sy:.0f} -> ESP y={ey}")

def screen_to_esp_y(sy, cal):
    pairs = sorted(cal["pairs"])
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    return int(round(np.interp(sy, xs, ys)))

# ===================== 실행 =====================
def run():
    if not os.path.exists(MAP_FILE):
        print(f"\n[경고] 캘리브 파일 없음: {MAP_FILE}")
        print("먼저 캘리브하세요: python radius_go.py calib\n")
        return
    cal = json.load(open(MAP_FILE))
    print(f"y매핑 로드: {MAP_FILE}")
    print(f"  x={cal.get('x','?')}, {len(cal['pairs'])}쌍:")
    for sy, ey in sorted(cal["pairs"]):
        print(f"    화면y={sy:.0f} -> ESP y={ey}")
    print("t=Radius 이동  c=MOVE/CLICK  l=글자목록  q=종료\n")
    use_click = [False]
    while True:
        cv2.imshow("radius", grab())
        k = cv2.waitKey(30) & 0xFF
        if k == ord('q'): break
        elif k == ord('c'):
            use_click[0] = not use_click[0]
            print(f"모드 -> {'CLICK' if use_click[0] else 'MOVE'}")
        elif k == ord('l'):
            items = ocr_all(); items.sort(key=lambda x:x[2])
            print("\n화면 글자(위->아래):")
            for (t,c,sy) in items: print(f"  화면y={sy:.0f}: '{t}' ({c:.2f})")
        elif k == ord('t'):
            sy, found = find_y(TARGET)
            if sy is None:
                print(f"'{TARGET}' 못 찾음"); continue
            ey = screen_to_esp_y(sy, cal)
            ey = max(0, min(400, ey))
            cmd = f"CLICK:{X_FIXED},{ey}" if use_click[0] else f"MOVE:{X_FIXED},{ey}"
            print(f"'{found}' 화면y={sy:.0f} -> ESP({X_FIXED},{ey}) [{cmd.split(':')[0]}]")
            send_wait(cmd)
    cap.release(); cv2.destroyAllWindows(); ser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calib":
        calibrate(); ser.close(); cap.release()
    else:
        run()