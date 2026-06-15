"""
calibrate_click.py  (수동 클릭 방식 - 가장 확실)
ESP를 각 격자점으로 보내고 흔들어서 커서를 띄운 뒤,
사람이 영상에서 커서를 마우스로 클릭하면 그 픽셀 <-> ESP 쌍을 저장.
9점 모으면 homography 계산.

조작:
  - ESP가 자동으로 한 점씩 이동하고 흔듦
  - 영상 창에서 "떨고 있는 커서"를 마우스 왼클릭 -> 저장하고 다음 점
  - 키 r : 흔들기 토글 (안 보이면 끄고 화면 확인)
  - 키 s : 이 점 건너뛰기
  - 키 q : 중단하고 지금까지로 계산

실행: python calibrate_click.py
"""
import cv2, numpy as np, serial, time, threading

COM_PORT = "COM7"
STREAM_URL = "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto"

GRID_X = (30, 180, 330)
GRID_Y = (40, 250, 460)
ESP_GRID = [(x, y) for y in GRID_Y for x in GRID_X]

ser = serial.Serial(COM_PORT, 115200, timeout=2)
time.sleep(2); ser.reset_input_buffer()
cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# 백그라운드 흔들기 (cursor_check2 검증 방식)
jiggle_on = False
def jiggle_loop():
    d = 1
    while True:
        if jiggle_on:
            ser.write(f"MOVEREL:{8*d},0\n".encode()); d *= -1
        time.sleep(0.15)
threading.Thread(target=jiggle_loop, daemon=True).start()

def send_wait(cmd, timeout=8):
    ser.reset_input_buffer()
    ser.write((cmd+"\n").encode())
    t0=time.time()
    while time.time()-t0<timeout:
        if ser.readline().decode(errors="ignore").strip()=="DONE": return True
    return False

def grab():
    cap.grab(); cap.grab()
    ret,f=cap.read(); return f if ret else None

# 마우스 클릭 콜백
click_pos = None
def on_mouse(event, x, y, flags, param):
    global click_pos
    if event == cv2.EVENT_LBUTTONDOWN:
        click_pos = (x, y)

cv2.namedWindow("click_cursor")
cv2.setMouseCallback("click_cursor", on_mouse)

pairs = []
idx = 0
while idx < len(ESP_GRID):
    ex, ey = ESP_GRID[idx]
    # 이 점으로 이동
    jiggle_on = False
    send_wait(f"MOVE:{ex},{ey}")
    jiggle_on = True
    click_pos = None

    # 클릭할 때까지 영상 표시
    while True:
        f = grab()
        if f is None: continue
        disp = f.copy()
        cv2.putText(disp, f"[{idx+1}/{len(ESP_GRID)}] ESP({ex},{ey}) - 떨고있는 커서를 클릭",
                    (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        cv2.putText(disp, "r=흔들기토글  s=건너뛰기  q=종료",
                    (10,60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
        for (e,(cx,cy)) in pairs:
            cv2.circle(disp,(cx,cy),6,(255,0,0),-1)
        cv2.imshow("click_cursor", disp)
        k = cv2.waitKey(30) & 0xFF

        if click_pos is not None:
            pairs.append(((ex,ey), click_pos))
            print(f"저장: ESP({ex},{ey}) <-> CAM{click_pos}")
            idx += 1
            break
        if k == ord('r'):
            jiggle_on = not jiggle_on; print(f"흔들기={jiggle_on}")
        elif k == ord('s'):
            print(f"건너뜀: ESP({ex},{ey})"); idx += 1; break
        elif k == ord('q'):
            idx = len(ESP_GRID); break

jiggle_on = False
cv2.destroyAllWindows()

print(f"\n수집: {len(pairs)}점")
if len(pairs) >= 4:
    cam = np.float32([p[1] for p in pairs])
    esp = np.float32([p[0] for p in pairs])
    H, mask = cv2.findHomography(cam, esp, cv2.RANSAC, 5.0)
    if H is not None:
        np.save(f"{OUT}/H_cam2esp.npy", H)
        proj = cv2.perspectiveTransform(cam.reshape(-1,1,2), H).reshape(-1,2)
        errs = np.linalg.norm(proj-esp, axis=1)
        print(f"H_cam2esp.npy 저장됨")
        print(f"재투영 오차: 평균 {errs.mean():.1f} | 최대 {errs.max():.1f} (ESP 단위)")
        for i in np.argsort(-errs):
            (ex,ey),(cx,cy)=pairs[i]
            u="" if mask is None or mask[i] else " [제외]"
            print(f"  ESP({ex:3d},{ey:3d}) CAM({cx},{cy}) | {errs[i]:5.1f}{u}")
    else:
        print("homography 실패")
else:
    print("4점 미만 - 계산 불가")

cap.release(); ser.close()