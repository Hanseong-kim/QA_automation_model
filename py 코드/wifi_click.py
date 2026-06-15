"""
wifi_click.py - WiFi 목록에서 OCR로 타겟 찾아 행 기반으로 클릭

구조:
  - WiFi 목록은 x고정(=100), 세로 13행, 간격 일정
  - 캘리브: 1행 ESP_y와 13행 ESP_y만 정하면 -> 나머지는 선형보간
  - 실행: OCR로 글자들 읽고 세로 정렬 -> 타겟이 N번째 -> N행 y로 CLICK
  - OCR은 90도 회전 화면에서 수행

모드:
  python wifi_click.py calib   -> 캘리브 (1행/13행 y 정하고 저장)
  python wifi_click.py         -> 실행 (타겟 찾아 클릭)
"""
import cv2, numpy as np, serial, time, easyocr, re, json, sys
from difflib import SequenceMatcher

COM_PORT = "COM7"
STREAM_URL = "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto"
ROWS_FILE = f"{OUT}/wifi_rows.json"

X_FIXED = 100          # 클릭 x 고정
N_ROWS = 13            # 행 개수
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
    ret, f = cap.read()
    return f if ret else None

def send_wait(cmd, timeout=10):
    ser.reset_input_buffer()
    ser.write((cmd+"\n").encode())
    t0=time.time()
    while time.time()-t0<timeout:
        if ser.readline().decode(errors="ignore").strip()=="DONE": return True
    return False

def ocr_rows():
    """90도 회전 화면 OCR -> 텍스트들을 세로(행) 순으로 정렬해 반환.
    회전화면에서 y가 클수록 아래쪽 행. (text, conf, ry) 리스트."""
    frame = grab()
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    items = []
    for (bbox, text, conf) in reader.readtext(rot):
        if conf <= OCR_CONF: continue
        ry = (bbox[0][1] + bbox[2][1]) / 2    # 회전화면 세로 위치
        items.append((text, conf, ry))
    items.sort(key=lambda x: x[2])            # 위->아래 정렬
    return items

def is_match(text, target):
    t, g = text.lower().strip(), target.lower()
    for w in re.split(r'[\s\-_]+', t):
        if w == g: return True
    for w in re.split(r'[\s\-_]+', t):
        if SequenceMatcher(None, w, g).ratio() >= SIMILARITY: return True
    return False

# ============================================================
def calibrate():
    """13개 행의 ESP y를 각각 직접 맞춰서 저장 (가속 때문에 보간 불가, 실측)."""
    print(f"\n=== 행 캘리브 (13행 전부) ===")
    print(f"x는 {X_FIXED} 고정. 각 행 글자에 커서를 올려 y를 정함.\n")
    print("ESP y 입력 -> 커서가 MOVE(안누름). 글자에 올라가면 'ok'로 다음 행.\n")

    row_y = []
    cur_y = [0]
    for r in range(N_ROWS):
        print(f"\n# {r+1}행")
        while True:
            s = input(f"[{r+1}행] ESP y (또는 'ok') > ").strip()
            if s == 'ok':
                if cur_y[0] == 0:
                    print("  먼저 y를 입력해 커서를 올리세요"); continue
                row_y.append(cur_y[0])
                break
            try:
                y = int(s)
            except ValueError:
                print("  숫자나 'ok'"); continue
            send_wait(f"MOVE:{X_FIXED},{y}")
            cur_y[0] = y
            print(f"  커서 -> ESP({X_FIXED},{y})")

    json.dump({"x": X_FIXED, "n_rows": N_ROWS, "row_y": row_y}, open(ROWS_FILE, "w"))
    print(f"\n저장됨: {row_y}")

def row_to_esp_y(row_idx, cal):
    """행 번호(0=1행) -> ESP y (실측 룩업테이블)."""
    ry = cal["row_y"]
    row_idx = max(0, min(len(ry)-1, row_idx))
    return ry[row_idx]

def run():
    cal = json.load(open(ROWS_FILE))
    print(f"행 캘리브 로드: {cal['n_rows']}행, y={cal['row_y']}\n")
    print("t=타겟 찾아 클릭  l=현재 화면 글자 목록  q=종료")

    while True:
        cv2.imshow("wifi", grab())
        k = cv2.waitKey(30) & 0xFF
        if k == ord('q'): break
        elif k == ord('l'):
            rows = ocr_rows()
            print(f"\n현재 화면 {len(rows)}개 (위->아래):")
            for i, (t, c, ry) in enumerate(rows):
                print(f"  {i}행: '{t}' ({c:.2f})")
        elif k == ord('t'):
            rows = ocr_rows()
            hit_idx = None
            for i, (t, c, ry) in enumerate(rows):
                if is_match(t, TARGET):
                    hit_idx = i; hit_text = t; break
            if hit_idx is None:
                print(f"'{TARGET}' 못 찾음. 보인 글자:")
                for (t,c,ry) in rows: print(f"  '{t}'")
                continue
            # hit_idx는 'OCR로 읽힌 것 중 순서'. 실제 행번호로 보정 필요할 수 있음.
            esp_y = row_to_esp_y(hit_idx, cal)
            print(f"'{hit_text}' = {hit_idx}행 -> CLICK ESP({cal['x']},{esp_y})")
            send_wait(f"CLICK:{cal['x']},{esp_y}")

    cap.release(); cv2.destroyAllWindows(); ser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calib":
        calibrate()
        ser.close(); cap.release()
    else:
        run()