"""
calib_manual.py - 수동 클릭 호모그래피 캘리브레이션 (개선판)

개선점:
  1) 다중클릭 평균    : 한 점을 여러 번 클릭 -> 평균 (손떨림 보정)
  2) 점별 오차 + 시각화: 어느 점이 부정확한지 콘솔 + calib_residuals.png
  3) undo / 재측정     : u=클릭 취소, b=이 점 다시, 끝나고 불량점만 재측정 가능
  4) 역방향 검증       : 끝나고 '아무 데나 클릭 -> ESP가 그리로 이동' 직접 확인
  5) 16점 격자(4x4)    : 화면 전체 정확도 향상

조작:
  모서리: 좌상->우상->우하->좌하 클릭, space=확정, r=리셋
  격자  : 커서 여러 번 클릭(평균), space=저장, u=클릭취소, b=이 점 초기화, q=종료
  검증  : 아무 데나 클릭하면 ESP가 그리로 이동, q=종료
"""
import cv2, numpy as np, serial, time, json, os

COM_PORT = "COM7"
BASE_URL = "http://192.168.1.205:8080"
STREAM_URL = f"{BASE_URL}/video"
OUT_FILE = "homography.json"
ROI_FILE = "roi.json"
RESID_IMG = "calib_residuals.png"

# 4x4 = 16점 (검증된 범위 내. 화면 밖이면 줄여)
GRID_X = [60, 110, 160, 200]
GRID_Y = [60, 130, 195, 260]
ROTATE = cv2.ROTATE_90_CLOCKWISE
CLICKS_PER_POINT = 3        # 한 점 권장 클릭 수(평균)
MOVE_WAIT = 1.2             # 이동 후 커서 뜰 때까지 대기

# --- ESP 연결 ---
try:
    ser = serial.Serial(COM_PORT, 115200, timeout=1)
    time.sleep(2); ser.reset_input_buffer()
    print("ESP 연결됨")
except Exception as e:
    print(f"ESP 연결 실패: {e}"); exit()

def send(cmd, wait=0.0, timeout=12):
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode())
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ser.readline().decode(errors="ignore").strip() == "DONE":
            if wait: time.sleep(wait)
            return True
    return False

# --- 카메라 ---
cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab():
    for _ in range(2): cap.grab()
    ret, f = cap.read()
    return cv2.rotate(f, ROTATE) if ret else None

# --- 마우스 클릭 버퍼 ---
_clicks = []
def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        _clicks.append((x, y))

# ---------------- 1. 모서리 4개 ----------------
def setup_corners():
    print("\n=== [1] 태블릿 모서리 4개 클릭 (좌상->우상->우하->좌하), space=확정 ===")
    pts = []
    win = "Step 1: 4 Corners (space=confirm, r=reset)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.setMouseCallback(win, on_mouse)
    _clicks.clear()
    while True:
        frame = grab()
        if frame is None: continue
        while _clicks and len(pts) < 4:
            pts.append(_clicks.pop(0))
        _clicks.clear()
        disp = frame.copy()
        cv2.putText(disp, f"Click 4 corners: {len(pts)}/4  (space=ok, r=reset)",
                    (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
        for i,p in enumerate(pts):
            cv2.circle(disp,p,8,(0,0,255),-1)
            cv2.putText(disp,str(i+1),(p[0]+10,p[1]),cv2.FONT_HERSHEY_SIMPLEX,1,(0,255,0),2)
        if len(pts) >= 2:
            cv2.polylines(disp,[np.array(pts,np.int32)],len(pts)==4,(0,255,255),2)
        cv2.imshow(win, disp)
        k = cv2.waitKey(30) & 0xFF
        if k == ord('r'): pts.clear()
        elif len(pts)==4 and k==ord(' '): break
    cv2.destroyWindow(win)
    json.dump({"corners": pts}, open(ROI_FILE,"w"), indent=2)
    print(f"모서리 저장: {ROI_FILE}")
    return np.array(pts, dtype=np.int32)

# ---------------- 2. 한 점 다중클릭 평균 ----------------
def collect_one_point(win, gx, gy, corners):
    """한 격자점: 이동 -> 여러 번 클릭 -> 평균. 반환: (px,py) 또는 'quit'."""
    print(f"ESP 이동 ({gx},{gy})...", end=" ")
    send(f"MOVE:{gx},{gy}", wait=MOVE_WAIT)
    print("커서를 여러 번 클릭(평균) 후 space")
    _clicks.clear()
    clicks = []
    while True:
        frame = grab()
        if frame is None: continue
        while _clicks: clicks.append(_clicks.pop(0))
        disp = frame.copy()
        cv2.polylines(disp,[corners],True,(255,0,0),2)
        cv2.putText(disp,f"Target ESP({gx},{gy})  clicks {len(clicks)}/{CLICKS_PER_POINT}",
                    (20,50),cv2.FONT_HERSHEY_SIMPLEX,1.1,(0,255,255),3)
        cv2.putText(disp,"click cursor (space=save, u=undo, b=clear, q=quit)",
                    (20,90),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,0),2)
        for p in clicks: cv2.circle(disp,p,5,(0,0,255),-1)
        if clicks:
            ax = float(np.mean([c[0] for c in clicks])); ay = float(np.mean([c[1] for c in clicks]))
            cv2.drawMarker(disp,(int(ax),int(ay)),(0,255,255),cv2.MARKER_CROSS,40,2)
        cv2.imshow(win, disp)
        k = cv2.waitKey(30) & 0xFF
        if k == ord('u') and clicks: clicks.pop()
        elif k == ord('b'): clicks.clear()
        elif k == ord('q'): return 'quit'
        elif k == ord(' '):
            if clicks:
                ax = float(np.mean([c[0] for c in clicks])); ay = float(np.mean([c[1] for c in clicks]))
                print(f"  -> 저장 px=({ax:.0f},{ay:.0f}) (클릭 {len(clicks)}회 평균)")
                return (ax, ay)
            print("  먼저 커서를 클릭하세요")

def collect_points(corners, grid, indices=None):
    """indices=None이면 전체, 아니면 해당 index만 재측정. 반환 dict {idx:(px,py)}."""
    win = "Step 2: Click Cursor"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.setMouseCallback(win, on_mouse)
    targets = indices if indices is not None else range(len(grid))
    result = {}
    for i in targets:
        gx, gy = grid[i]
        r = collect_one_point(win, gx, gy, corners)
        if r == 'quit':
            result['quit'] = True; break
        result[i] = r
    cv2.destroyWindow(win)
    return result

# ---------------- 호모그래피 + 점별오차 ----------------
def compute(esp_pts, px_pts):
    esp = np.array(esp_pts, np.float32); px = np.array(px_pts, np.float32)
    H_px2esp,_ = cv2.findHomography(px, esp, cv2.RANSAC, 5.0)
    H_esp2px,_ = cv2.findHomography(esp, px, cv2.RANSAC, 5.0)
    proj = cv2.perspectiveTransform(px.reshape(-1,1,2), H_px2esp).reshape(-1,2)
    err = np.linalg.norm(proj - esp, axis=1)
    return H_px2esp, H_esp2px, err

def report_residuals(grid_used, px_pts, err, corners):
    print("\n=== 점별 오차 (큰 순) ===")
    order = np.argsort(-err)
    for rank, j in enumerate(order):
        gx, gy = grid_used[j]
        flag = "  <-- 큼!" if err[j] > err.mean()+err.std() else ""
        print(f"  ESP({gx},{gy})  px({px_pts[j][0]:.0f},{px_pts[j][1]:.0f})  오차 {err[j]:.1f}{flag}")
    print(f"평균 {err.mean():.2f}  최대 {err.max():.2f}")

    # 시각화 저장
    frame = grab()
    if frame is not None:
        vis = frame.copy()
        cv2.polylines(vis,[corners],True,(255,0,0),2)
        emax = max(err.max(), 1e-6)
        for j,(px,py) in enumerate(px_pts):
            t = err[j]/emax                      # 0(좋음)~1(나쁨)
            color = (0, int(255*(1-t)), int(255*t))   # green->red
            cv2.circle(vis,(int(px),int(py)),10,color,-1)
            cv2.putText(vis,f"{err[j]:.0f}",(int(px)+8,int(py)-8),
                        cv2.FONT_HERSHEY_SIMPLEX,0.6,color,2)
        cv2.imwrite(RESID_IMG, vis)
        print(f"오차 시각화 저장: {RESID_IMG} (초록=정확, 빨강=부정확)")

# ---------------- 역방향 검증 ----------------
def reverse_verify(corners, H_px2esp):
    print("\n=== [검증] 아무 데나 클릭하면 ESP가 그 위치로 커서 이동. q=종료 ===")
    win = "Verify: click -> ESP moves there (q=quit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL); cv2.setMouseCallback(win, on_mouse)
    _clicks.clear()
    target, esp = None, None
    while True:
        frame = grab()
        if frame is None: continue
        while _clicks:
            target = _clicks.pop(0)
            p = np.array([[[target[0], target[1]]]], np.float32)
            e = cv2.perspectiveTransform(p, H_px2esp).reshape(2)
            esp = (int(max(0,min(400,round(e[0])))), int(max(0,min(450,round(e[1])))))
            send(f"MOVE:{esp[0]},{esp[1]}")
            for _ in range(3):           # 잠깐 흔들어 커서 보이게
                send("MOVEREL:1,0"); send("MOVEREL:-1,0")
        disp = frame.copy()
        cv2.polylines(disp,[corners],True,(255,0,0),2)
        if target:
            cv2.drawMarker(disp,target,(0,0,255),cv2.MARKER_CROSS,40,3)
            cv2.putText(disp,f"click px{target} -> ESP{esp}",(20,50),
                        cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,255),2)
        cv2.putText(disp,"Click anywhere: cursor should land on the X. q=quit",
                    (20,90),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,0),2)
        cv2.imshow(win, disp)
        if cv2.waitKey(30)&0xFF == ord('q'): break
    cv2.destroyWindow(win)

# ---------------- 메인 ----------------
def main():
    corners = setup_corners()
    grid = [(gx,gy) for gy in GRID_Y for gx in GRID_X]

    res = collect_points(corners, grid)
    quit_flag = res.pop('quit', False)
    if len(res) < 4:
        print("4점 미만 -> 종료"); cap.release(); ser.close(); return

    idxs = sorted(res.keys())
    grid_used = [grid[i] for i in idxs]
    px_pts = [list(res[i]) for i in idxs]
    esp_pts = [list(grid[i]) for i in idxs]

    H_px2esp, H_esp2px, err = compute(esp_pts, px_pts)
    report_residuals(grid_used, px_pts, err, corners)

    # 불량점 재측정 루프
    while True:
        s = input("\n다시 측정할 점 번호(오차 출력의 ESP좌표 말고, 순서 인덱스 0~%d, 콤마구분 / 엔터=완료): " % (len(grid)-1)).strip()
        if not s: break
        try:
            redo = [int(x) for x in s.split(",") if x.strip().isdigit()]
        except:
            print("입력 형식 오류"); continue
        redo = [i for i in redo if 0 <= i < len(grid)]
        if not redo: continue
        r2 = collect_points(corners, grid, indices=redo)
        r2.pop('quit', None)
        # 갱신/추가
        cur = {i: tuple(p) for i,p in zip(idxs, px_pts)}
        for i,p in r2.items(): cur[i] = p
        idxs = sorted(cur.keys())
        grid_used = [grid[i] for i in idxs]
        px_pts = [list(cur[i]) for i in idxs]
        esp_pts = [list(grid[i]) for i in idxs]
        H_px2esp, H_esp2px, err = compute(esp_pts, px_pts)
        report_residuals(grid_used, px_pts, err, corners)

    json.dump({
        "H_px2esp": H_px2esp.tolist(), "H_esp2px": H_esp2px.tolist(),
        "rotate": "ROTATE_90_CLOCKWISE", "grid_x": GRID_X, "grid_y": GRID_Y,
        "roi": corners.tolist(), "n_points": len(esp_pts),
        "mean_error": float(err.mean()), "max_error": float(err.max()),
    }, open(OUT_FILE,"w",encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n캘리브 저장: {OUT_FILE}")

    # 역방향 검증
    if input("역방향 검증 할래? (y/n): ").strip().lower() == 'y':
        reverse_verify(corners, H_px2esp)

    cap.release(); ser.close(); print("완료")

if __name__ == "__main__":
    main()