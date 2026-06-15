"""
cursor_check2.py
글레어 줄인 지금 환경에서 "커서가 실시간으로 검출되나?"를 눈으로 확인.

이 창을 띄워놓고 키로 조작:
  m : 커서를 화면 중앙(ESP 180,250)으로 이동
  j : 커서 흔들기 시작/정지 토글 (계속 떨어서 안 사라지게)
  b : 현재 프레임을 배경으로 저장
  (배경 저장 후) 자동으로 매 프레임 차영상 검출해서 빨간원 표시
  +/- : thresh,  [/] : min_area
  d : 어두운 변화만 검출 토글 (커서는 어둡고 글레어는 밝음)
  s : 저장
  q : 종료

calibrate 전에 여기서 커서가 또렷이 잡히는 걸 확인해야 함.
"""
import cv2, numpy as np, serial, time, threading

COM_PORT = "COM7"
STREAM_URL = "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto"

thresh = 35
min_area = 15
max_area = 3000
dark_only = False   # True면 "어두워진 픽셀"만 (커서) - 글레어(밝아짐) 무시

try:
    ser = serial.Serial(COM_PORT, 115200, timeout=2); time.sleep(2)
    ser.reset_input_buffer()
except Exception as e:
    print(f"[경고] 시리얼 실패: {e}"); ser = None

jiggling = False

def send(cmd):
    if ser: ser.write((cmd + "\n").encode())

def jiggle_loop():
    """백그라운드로 커서를 계속 흔들어 살려둠. press 안 함."""
    i = 0
    while True:
        if jiggling and ser:
            send(f"MOVEREL:{8 if i%2==0 else -8},0")  # 8px로 크게 흔듦
            i += 1
        time.sleep(0.15)

if ser:
    threading.Thread(target=jiggle_loop, daemon=True).start()

cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab():
    cap.grab(); cap.grab()
    ret, f = cap.read()
    return f if ret else None

def detect(bg, fg):
    g_bg = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY).astype(int)
    g_fg = cv2.cvtColor(fg, cv2.COLOR_BGR2GRAY).astype(int)
    if dark_only:
        diff = np.clip(g_bg - g_fg, 0, 255).astype(np.uint8)  # 어두워진 것만
    else:
        diff = np.abs(g_fg - g_bg).astype(np.uint8)
    _, m = cv2.threshold(diff, thresh, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cand = [c for c in cnts if min_area <= cv2.contourArea(c) <= max_area]
    pos = None
    if cand:
        c = min(cand, key=cv2.contourArea)
        M = cv2.moments(c)
        if M['m00']>0: pos=(int(M['m10']/M['m00']), int(M['m01']/M['m00']))
    return pos, m, len(cand)

print(__doc__)
bg = None
while True:
    raw = grab()
    if raw is None:
        print("프레임 못받음"); time.sleep(0.3); continue
    disp = raw.copy()
    cv2.putText(disp, f"thresh={thresh} area={min_area}-{max_area} dark={dark_only} jig={jiggling} bg={'OK' if bg is not None else 'X'}",
                (10,25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2)
    cv2.putText(disp, "m=center j=jiggle b=bg d=darkonly +/- [/] q",
                (10,50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
    if bg is not None:
        pos, mask, n = detect(bg, raw)
        ms = cv2.resize(mask, (disp.shape[1]//3, disp.shape[0]//3))
        disp[0:ms.shape[0], disp.shape[1]-ms.shape[1]:] = cv2.cvtColor(ms, cv2.COLOR_GRAY2BGR)
        cv2.putText(disp, f"cand={n}", (10,75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,0), 1)
        if pos:
            cv2.circle(disp, pos, 14, (0,0,255), 2)
    cv2.imshow("cursor_check2", disp)
    k = cv2.waitKey(30) & 0xFF
    if k == ord('q'): break
    elif k == ord('m'): send("MOVE:180,250"); print("중앙으로")
    elif k == ord('j'): jiggling = not jiggling; print(f"흔들기={jiggling}")
    elif k == ord('b'): bg = raw.copy(); print("배경 저장")
    elif k == ord('d'): dark_only = not dark_only; print(f"dark_only={dark_only}")
    elif k == ord('s'):
        cv2.imwrite(f"{OUT}/cc2.jpg", disp)
        if bg is not None: cv2.imwrite(f"{OUT}/cc2_mask.jpg", mask)
        print("저장")
    elif k in (ord('+'), ord('=')): thresh=min(thresh+5,255); print(thresh)
    elif k == ord('-'): thresh=max(thresh-5,0); print(thresh)
    elif k == ord(']'): min_area+=10; print(min_area)
    elif k == ord('['): min_area=max(min_area-10,1); print(min_area)

cap.release(); cv2.destroyAllWindows()
if ser: ser.close()