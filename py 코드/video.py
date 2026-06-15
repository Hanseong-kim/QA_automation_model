import cv2, serial, time, numpy as np

COM_PORT, STREAM_URL = "COM7", "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto"

ser = serial.Serial(COM_PORT, 115200, timeout=1); time.sleep(2)
cap = cv2.VideoCapture(STREAM_URL); cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab_fresh(n=5):
    for _ in range(n): cap.grab()
    ret, f = cap.read()
    return f if ret else None

def preprocess(f):                      # ★ OCR 쪽과 반드시 동일하게
    f = cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE)
    h, w = f.shape[:2]
    return f[int(h*0.05):int(h*0.95), int(w*0.05):int(w*0.95)]

def send_move(x, y, settle=0.4):
    ser.write(f"MOVE:{x},{y}\n".encode()); time.sleep(settle)

def find_cursor(bg, fg, min_area=20):
    d = cv2.absdiff(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY),
                    cv2.cvtColor(fg, cv2.COLOR_BGR2GRAY))
    _, m = cv2.threshold(d, 30, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) >= min_area]
    if not cnts: return None
    M = cv2.moments(max(cnts, key=cv2.contourArea))
    return (int(M['m10']/M['m00']), int(M['m01']/M['m00']))

# ESP 좌표계 격자 (네 좌표 범위에 맞게 조정)
esp_grid = [(x, y) for y in (50, 250, 450) for x in (50, 250, 450)]

send_move(0, 0, 0.6)                     # 배경: 커서 구석으로
bg = preprocess(grab_fresh())
pairs = []
for ex, ey in esp_grid:
    send_move(ex, ey)
    fg = preprocess(grab_fresh())
    pos = find_cursor(bg, fg)
    if pos is None:
        print(f"ESP({ex},{ey}) 커서 못찾음 → skip"); continue
    print(f"ESP({ex},{ey}) <-> CAM{pos}")
    pairs.append(((ex, ey), pos))
    vis = fg.copy(); cv2.circle(vis, pos, 10, (0,0,255), 2)
    cv2.imwrite(f"{OUT}/calib_{ex}_{ey}.jpg", vis)

# CAM → ESP homography
cam = np.float32([p[1] for p in pairs])
esp = np.float32([p[0] for p in pairs])
H, _ = cv2.findHomography(cam, esp, cv2.RANSAC, 5.0)
np.save(f"{OUT}/H_cam2esp.npy", H)

# 품질 체크 (ESP 단위 평균 오차)
proj = cv2.perspectiveTransform(cam.reshape(-1,1,2), H).reshape(-1,2)
print("재투영 오차:", np.linalg.norm(proj - esp, axis=1).mean())

cap.release(); ser.close()