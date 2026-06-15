"""
calib_homography.py - ESP <-> 카메라 픽셀 1:1 매칭 (ROI 수동지정 + 움직임 검출)

처음 1회: 카메라 창에서 태블릿 화면 네 모서리를 클릭 -> ROI 저장(roi.json).
  이후 실행: 저장된 ROI 자동 사용 (지그 고정이라 안 변함).
검출: ROI 안에서만, 커서를 흔들어 누적 차영상 -> 움직이는 커서만.
  + 모양 필터(작고 길쭉) + 검출 시각화(track_*.png).

조작:
  ROI 설정 창: 네 모서리 클릭(좌상->우상->우하->좌하), r=리셋, 클릭4개 끝나면 아무키나
실행: python calib_homography.py
"""
import cv2, numpy as np, serial, time, json, requests, os

COM_PORT = "COM7"
BASE_URL = "http://192.168.1.205:8080"
STREAM_URL = f"{BASE_URL}/video"
OUT_FILE = "homography.json"
ROI_FILE = "roi.json"
DEBUG_DIR = "debug_calib"

GRID_X = [60, 130, 200]
GRID_Y = [60, 160, 260]
ROTATE = cv2.ROTATE_90_CLOCKWISE

WIGGLE = 20
WARMUP = 4
CAPTURE_CYCLES = 8
DIFF_THRESH = 22
MIN_AREA = 25
MAX_AREA = 6000
SAVE_DEBUG = True

os.makedirs(DEBUG_DIR, exist_ok=True)

ser = serial.Serial(COM_PORT, 115200, timeout=1)
time.sleep(2); ser.reset_input_buffer()
print("ESP 연결됨")

def send(cmd, wait=0.0, timeout=12):
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode())
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ser.readline().decode(errors="ignore").strip() == "DONE":
            if wait: time.sleep(wait)
            return True
    return False

cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab(flush=1):
    for _ in range(flush): cap.grab()
    ret, f = cap.read()
    return cv2.rotate(f, ROTATE) if ret else None

# ---------------- ROI 지정 ----------------
def setup_roi():
    """저장된 ROI 있으면 로드, 없으면 클릭으로 지정."""
    if os.path.exists(ROI_FILE):
        d = json.load(open(ROI_FILE))
        print(f"기존 ROI 사용 ({ROI_FILE}). 다시 잡으려면 이 파일 삭제.")
        return np.array(d["corners"], dtype=np.int32)

    print("\n=== ROI 설정: 카메라 창에서 태블릿 화면 네 모서리를 클릭 ===")
    print("  순서: 좌상 -> 우상 -> 우하 -> 좌하 / r=리셋")
    pts = []
    frame = None
    for _ in range(10):
        frame = grab(flush=3)
        if frame is not None: break
    if frame is None:
        print("카메라 프레임 못 받음"); return None

    clone = frame.copy()
    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x, y))

    cv2.namedWindow("ROI 설정 (4모서리 클릭, r=리셋)", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("ROI 설정 (4모서리 클릭, r=리셋)", on_mouse)
    while True:
        disp = clone.copy()
        for i, p in enumerate(pts):
            cv2.circle(disp, p, 8, (0,0,255), -1)
            cv2.putText(disp, str(i+1), (p[0]+10, p[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
        if len(pts) >= 2:
            cv2.polylines(disp, [np.array(pts, np.int32)], len(pts)==4, (0,255,255), 2)
        cv2.imshow("ROI 설정 (4모서리 클릭, r=리셋)", disp)
        k = cv2.waitKey(30) & 0xFF
        if k == ord('r'):
            pts.clear()
        elif len(pts) == 4 and k != 255:
            break
    cv2.destroyAllWindows()

    json.dump({"corners": pts}, open(ROI_FILE, "w"), indent=2)
    print(f"ROI 저장: {ROI_FILE}")
    return np.array(pts, dtype=np.int32)

def make_roi_mask(shape, corners):
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(mask, [corners], 255)
    return mask

# ---------------- 커서 검출 ----------------
def wiggle_once():
    out = []
    send(f"MOVEREL:{WIGGLE},0"); f = grab(1)
    if f is not None: out.append(f)
    send(f"MOVEREL:-{WIGGLE},0"); f = grab(1)
    if f is not None: out.append(f)
    return out

def detect_at(gx, gy, roi_mask):
    send(f"MOVE:{gx},{gy}", wait=0.3)
    for _ in range(WARMUP): wiggle_once()
    frames = []
    for _ in range(CAPTURE_CYCLES): frames.extend(wiggle_once())
    if len(frames) < 2: return None

    grays = [cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY),(5,5),0) for f in frames]
    accum = np.zeros_like(grays[0], dtype=np.float32)
    for i in range(1, len(grays)):
        accum += cv2.absdiff(grays[i], grays[i-1]).astype(np.float32)
    accum = cv2.normalize(accum, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    accum = cv2.bitwise_and(accum, accum, mask=roi_mask)   # << ROI 밖 제거
    _, mask = cv2.threshold(accum, DIFF_THRESH, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7,7), np.uint8))

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, -1
    for c in cnts:
        ar = cv2.contourArea(c)
        if ar < MIN_AREA or ar > MAX_AREA: continue
        x,y,w,h = cv2.boundingRect(c)
        aspect = max(w,h)/max(1,min(w,h))     # 커서는 길쭉(>1.2), 아이콘은 정사각(~1)
        # 점수: 적당한 길쭉함 + 적당한 크기 우선
        score = ar * (1.0 if 1.1 <= aspect <= 3.5 else 0.3)
        if score > best_score:
            M = cv2.moments(c)
            if M["m00"] == 0: continue
            best = (M["m10"]/M["m00"], M["m01"]/M["m00"]); best_score = score

    if SAVE_DEBUG:
        track = frames[-1].copy()
        cv2.polylines(track, [np.array(ROI_CORNERS, np.int32)], True, (255,0,0), 2)
        if best:
            bx, by = int(best[0]), int(best[1])
            cv2.drawMarker(track,(bx,by),(0,0,255),cv2.MARKER_CROSS,40,3)
            cv2.circle(track,(bx,by),18,(0,0,255),2)
        cv2.putText(track,f"ESP({gx},{gy})",(20,50),cv2.FONT_HERSHEY_SIMPLEX,1.2,(0,255,0),3)
        cv2.imwrite(f"{DEBUG_DIR}/track_{gx}_{gy}.png", track)
    return best

ROI_CORNERS = None

def main():
    global ROI_CORNERS
    ROI_CORNERS = setup_roi()
    if ROI_CORNERS is None:
        cap.release(); ser.close(); return
    sample = grab(2)
    roi_mask = make_roi_mask(sample.shape, ROI_CORNERS)

    print("\n=== 격자 캘리브 (ROI 제한) ===")
    esp_pts, px_pts = [], []
    for gy in GRID_Y:
        for gx in GRID_X:
            print(f"[격자] ESP=({gx},{gy})", end="  ")
            px = detect_at(gx, gy, roi_mask)
            if px is None:
                print("검출 실패"); continue
            print(f"픽셀=({px[0]:.0f},{px[1]:.0f})")
            esp_pts.append([gx,gy]); px_pts.append([px[0],px[1]])

    print(f"\n검출 {len(esp_pts)}/{len(GRID_X)*len(GRID_Y)}점")
    print(">> debug_calib/track_*.png 에서 빨간 십자가 커서에 찍혔는지 확인")
    if len(esp_pts) < 4:
        cap.release(); ser.close(); return

    esp_arr = np.array(esp_pts, np.float32); px_arr = np.array(px_pts, np.float32)
    H_px2esp,_ = cv2.findHomography(px_arr, esp_arr, cv2.RANSAC, 5.0)
    H_esp2px,_ = cv2.findHomography(esp_arr, px_arr, cv2.RANSAC, 5.0)
    proj = cv2.perspectiveTransform(px_arr.reshape(-1,1,2), H_px2esp).reshape(-1,2)
    err = np.linalg.norm(proj - esp_arr, axis=1)
    print(f"평균 재투영오차 {err.mean():.2f} (max {err.max():.2f})")

    json.dump({"H_px2esp":H_px2esp.tolist(),"H_esp2px":H_esp2px.tolist(),
        "rotate":"ROTATE_90_CLOCKWISE","grid_x":GRID_X,"grid_y":GRID_Y,
        "roi":ROI_CORNERS.tolist(),"n_points":len(esp_pts),"mean_error":float(err.mean())},
        open(OUT_FILE,"w",encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"저장: {OUT_FILE}")

    cx=int(np.mean(GRID_X)); cy=int(np.mean(GRID_Y))
    pred=cv2.perspectiveTransform(np.array([[[cx,cy]]],np.float32),H_esp2px).reshape(2)
    actual=detect_at(cx,cy,roi_mask)
    print(f"[검증] 중앙({cx},{cy}) 예측px=({pred[0]:.0f},{pred[1]:.0f})", end="  ")
    if actual:
        print(f"실제=({actual[0]:.0f},{actual[1]:.0f}) 오차 {np.linalg.norm(np.array(actual)-pred):.1f}px")
    else:
        print("검증 실패")
    cap.release(); ser.close(); print("\n완료")

if __name__ == "__main__":
    main()