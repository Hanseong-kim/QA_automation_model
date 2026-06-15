"""
full_flow.py - Settings 진입 -> Internet 창 -> OCR로 Radius 찾아 클릭 -> 검증 -> 비번

추가된 것: '클릭 후 검증' 루프
  - 클릭 후 화면을 OCR로 다시 확인
  - (비번/연결 화면) AND (Radius 글자 있음)  -> 올바른 선택, 비번 입력
  - (비번/연결 화면) AND (Radius 글자 없음)  -> 다른 WiFi 잘못 클릭 -> 뒤로가기(90,20) -> 재시도
  - 아직 목록 화면                            -> 클릭 미작동 -> 뒤로가기 없이 재시도
  최대 MAX_TRIES회. 다 실패하면 ymap.json 드리프트 의심 안내.

사전 준비: radius_go.py calib 으로 ymap.json
실행: python full_flow.py
"""
import cv2, numpy as np, serial, time, easyocr, re, json, os
from difflib import SequenceMatcher

COM_PORT = "COM7"
STREAM_URL = "http://192.168.1.205:8080/video"
MAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ymap.json")
X_FIXED = 40
TARGET = "Radius"
PASSWORD = "9876543210"
BACK_BTN = (90, 20)        # 뒤로가기 버튼 ESP 좌표
OCR_CONF = 0.4
MAX_TRIES = 3

# 화면 종류 판별 키워드
LIST_HINTS = ("internet", "wi-fi", "wifi", "saved network", "add network", "network &")
PWD_HINTS  = ("password", "connect", "cancel", "forget", "security")

# ---------- 연결 ----------
ser = serial.Serial(COM_PORT, 115200, timeout=1)
time.sleep(2); ser.reset_input_buffer()
print("연결됨")

def send(cmd, wait=2, timeout=10):
    ser.reset_input_buffer()
    ser.write((cmd + '\n').encode())
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = ser.readline().decode(errors="ignore").strip()
        if line:
            print(f'  <- {line}')
        if line == 'DONE':
            time.sleep(wait)
            return True
    return False

# ---------- OCR ----------
print("EasyOCR 로딩...")
reader = easyocr.Reader(['en'])
cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab(flush=15):
    for _ in range(flush):
        cap.grab()
    ret, f = cap.read()
    return f if ret else None

def fresh_grab():
    """카메라를 닫았다 다시 열어 완전히 최신 프레임."""
    global cap
    cap.release()
    time.sleep(0.3)
    cap = cv2.VideoCapture(STREAM_URL)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    for _ in range(5):
        cap.grab()
    ret, f = cap.read()
    return f if ret else None

def ocr_all():
    frame = grab()
    if frame is None: return []
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    out = []
    for (bbox, text, conf) in reader.readtext(rot):
        if conf <= OCR_CONF: continue
        sy = (bbox[0][1] + bbox[2][1]) / 2
        out.append((text, conf, sy))
    return out

def is_match(text, target):
    t, g = text.lower().strip(), target.lower()
    words = re.split(r'[\s\-_,./]+', t)
    for w in words:
        if w == g: return True
    for w in words:
        if len(w) >= 4 and SequenceMatcher(None, w, g).ratio() >= 0.85: return True
    return False

def classify(items):
    """현재 화면이 목록인지 비번화면인지 + Radius 글자 유무."""
    texts = [t.lower() for (t, c, sy) in items]
    on_list = any(h in t for t in texts for h in LIST_HINTS)
    on_pwd  = any(h in t for t in texts for h in PWD_HINTS)
    has_radius = any(is_match(t, TARGET) for (t, c, sy) in items)
    return on_list, on_pwd, has_radius

def find_target_in_list(cal):
    """목록 화면에서 Radius의 화면y 찾기. 범위/목록여부 체크 포함.
       반환: (found_y, found_text, items) 또는 (None, None, items)."""
    cal_sys = [p[0] for p in cal["pairs"]]
    y_min, y_max = min(cal_sys), max(cal_sys)
    items = ocr_all()
    g = TARGET.lower()
    exact, fuzzy = [], []
    for (t, c, sy) in items:
        words = re.split(r'[\s\-_,./]+', t.lower().strip())
        if g in words: exact.append((t, c, sy))
        elif is_match(t, TARGET): fuzzy.append((t, c, sy))
    pool = exact if exact else fuzzy
    if not pool:
        return None, None, items
    pool.sort(key=lambda x: x[1], reverse=True)
    sy, text = pool[0][2], pool[0][0]
    # 목록 화면 맞고, 범위 안인지
    on_list, _, _ = classify(items)
    in_range = (y_min - 100) <= sy <= (y_max + 100)
    if not on_list:
        return None, None, items   # 아직 목록 아님(전환중)
    if not in_range:
        print(f"  Radius y={sy:.0f} 범위밖({y_min:.0f}~{y_max:.0f}) 가짜 의심")
        return None, None, items
    return sy, text, items

def screen_to_esp_y(sy, cal):
    pairs = sorted(cal["pairs"])
    xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
    return int(round(np.interp(sy, xs, ys)))

def connect_radius(cal):
    """Radius 찾기 -> 클릭 -> 검증 -> (실패시 뒤로가기 후 재시도). 성공 시 True."""
    for attempt in range(1, MAX_TRIES + 1):
        print(f"\n--- 시도 {attempt}/{MAX_TRIES} ---")
        # 목록에서 Radius 찾기 (몇 번 리프레시 허용)
        found_y = None
        for _ in range(4):
            found_y, found_text, items = find_target_in_list(cal)
            if found_y is not None:
                break
            print("  목록에서 Radius 못찾음/전환중, 리프레시")
            fresh_grab(); time.sleep(0.8)
        if found_y is None:
            print("  목록에서 Radius 확보 실패")
            continue

        # 클릭
        esp_y = max(0, min(400, screen_to_esp_y(found_y, cal)))
        print(f"  '{found_text}' 화면y={found_y:.0f} -> CLICK ESP({X_FIXED},{esp_y})")
        send(f"CLICK:{X_FIXED},{esp_y}", wait=2.5)

        # 검증
        time.sleep(1.0)
        fresh_grab(); time.sleep(0.4)
        items = ocr_all()
        on_list, on_pwd, has_radius = classify(items)
        print(f"  [검증] on_list={on_list} on_pwd={on_pwd} has_radius={has_radius}")

        if on_pwd and has_radius:
            print("  [OK] Radius 비번화면 확인")
            return True
        if on_pwd and not has_radius:
            hit = [t for (t, c, sy) in items if c > 0.6]
            print(f"  [실패] 다른 WiFi 들어감. 화면 글자: {hit}")
            print(f"  뒤로가기 {BACK_BTN}")
            send(f"CLICK:{BACK_BTN[0]},{BACK_BTN[1]}", wait=2)
            fresh_grab(); time.sleep(0.5)
            continue
        # 아직 목록 / 전환중 -> 클릭 미작동, 뒤로가기 없이 재시도
        print("  [재시도] 아직 목록이거나 전환중 (클릭 미작동 추정)")
        fresh_grab(); time.sleep(0.6)
    return False

# ========== 메인 ==========
def main():
    print("\n=== 홈/앱스 화면 ===")
    send('SWIPE:200,100,200,400', wait=2)

    print("\n=== Settings -> Internet 진입 ===")
    print('[1] Settings 클릭');           send('CLICK:150,250', wait=3)
    print('[2] Network & Internet 클릭'); send('CLICK:40,280', wait=3)
    print('[3] Internet 클릭');           send('CLICK:40,280', wait=3)

    print('\n=== Internet 창 안정 대기 ===')
    time.sleep(3)
    print("  카메라 리프레시...")
    fresh_grab(); time.sleep(0.5)

    cal = json.load(open(MAP_FILE))
    print(f"  캘리브: x={cal.get('x','?')}, {len(cal['pairs'])}쌍")

    ok = connect_radius(cal)
    if not ok:
        print(f"\n'{TARGET}' 연결 실패 (최대 {MAX_TRIES}회 시도).")
        print("의심 원인: 카메라 프레이밍이 바뀌어 ymap.json이 안 맞을 수 있음.")
        print(" -> radius_go.py calib 로 ymap.json 재생성 권장.")
        cap.release(); ser.close(); return

    print("\n=== 비밀번호 입력 ===")
    time.sleep(1.5)
    print(f"[비번] {PASSWORD} 입력"); send(f"TYPE:{PASSWORD}", wait=2)
    print("[엔터] 연결");            send("KEY:ENTER", wait=2)
    print("\n완료! Radius 연결 시도됨")
    cap.release(); ser.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
        try: cap.release()
        except: pass
        ser.close()