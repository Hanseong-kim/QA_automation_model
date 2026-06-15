"""
run.py - 최종 실행: OCR로 타겟 텍스트 찾아 ESP로 클릭 (90도 회전 처리 포함)

좌표계 처리 (중요):
  - OCR은 90도 회전한 화면에서 텍스트를 찾음 (글자가 세로라서)
  - 캘리브(H)는 회전 안 한 원본 카메라 좌표 기준
  - 그래서 OCR 좌표를 원본 좌표로 역회전한 뒤 H에 넣어 ESP로 변환

조작:
  t : OCR로 타겟 찾아서 이동/클릭
  마우스 클릭 : (원본 영상에서) 그 픽셀로 이동/클릭 - 검증용
  c : MOVE(검증) <-> CLICK(실제누름) 토글
  q : 종료

실행: python run.py
"""
import cv2, numpy as np, serial, time, easyocr
from difflib import SequenceMatcher

COM_PORT = "COM7"
STREAM_URL = "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto"
TARGET = "Radius"
OCR_CONF = 0.4
SIMILARITY = 0.75     # 더 엄격하게 (radius-auto 같은 건 제외)

# 회전된 화면에서 "태블릿 화면 영역"만 검출 (모니터/VSCode 반사 제외)
# None이면 전체. fail시 회전영상 보고 태블릿 영역 좌표로 설정.
# (회전 후 좌표 기준: x_min, y_min, x_max, y_max)
ROT_ROI = None

def is_match(text, target):
    """정확 단어 매칭 우선. radius-auto 같은 합성어는 제외."""
    t, g = text.lower().strip(), target.lower()
    # 단어 분리 (공백, 하이픈, 언더스코어로)
    import re
    words = re.split(r'[\s\-_]+', t)
    for w in words:
        if w == g:                       # 정확히 'radius' 단어
            return True, 1.0
    for w in words:
        sim = SequenceMatcher(None, w, g).ratio()
        if sim >= SIMILARITY:            # Radlus 같은 오인식만 허용
            return True, sim
    return False, 0.0

H = np.load(f"{OUT}/H_cam2esp.npy")
print("H 로드됨")

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

def rotated_to_original(rx, ry, orig_w, orig_h):
    """90도 시계방향 회전 화면의 (rx,ry) -> 원본 화면 좌표.
    cv2.ROTATE_90_CLOCKWISE: 원본(x,y) -> 회전(orig_h-1-y, x)
    역변환: 원본 x = ry, 원본 y = orig_h-1-rx
    """
    ox = ry
    oy = orig_h - 1 - rx
    return int(ox), int(oy)

def cam_to_esp(cx, cy):
    v = H @ np.array([cx, cy, 1.0])
    return int(round(v[0]/v[2])), int(round(v[1]/v[2]))

use_click = False
click_pos = None
def on_mouse(event, x, y, flags, param):
    global click_pos
    if event == cv2.EVENT_LBUTTONDOWN:
        click_pos = (x, y)

cv2.namedWindow("run")
cv2.setMouseCallback("run", on_mouse)

def act(cam_x, cam_y, label=""):
    """원본 카메라 좌표 -> ESP -> 이동/클릭."""
    ex, ey = cam_to_esp(cam_x, cam_y)
    ex = max(0, min(360, ex)); ey = max(0, min(490, ey))
    cmd = f"CLICK:{ex},{ey}" if use_click else f"MOVE:{ex},{ey}"
    print(f"{label} CAM({cam_x},{cam_y}) -> ESP({ex},{ey}) [{cmd.split(':')[0]}]")
    send_wait(cmd)

print("\n준비됨. t=OCR타겟  마우스클릭=검증  c=MOVE/CLICK  q=종료\n")
while True:
    f = grab()
    if f is None: continue
    disp = f.copy()
    mode = "CLICK(실제)" if use_click else "MOVE(검증)"
    cv2.putText(disp, f"mode={mode} target='{TARGET}' t=OCR c=toggle q=quit",
                (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
    cv2.imshow("run", disp)
    k = cv2.waitKey(30) & 0xFF

    if click_pos is not None:
        # 마우스 클릭은 원본 영상 좌표 그대로 (검증용)
        act(click_pos[0], click_pos[1], "클릭검증:")
        click_pos = None
    elif k == ord('c'):
        use_click = not use_click
        print(f"모드 -> {'CLICK' if use_click else 'MOVE'}")
    elif k == ord('t'):
        frame = grab()
        oh, ow = frame.shape[:2]
        rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)   # OCR용 회전
        results = reader.readtext(rot)
        found = None
        best_sim = 0
        candidates = []
        for (bbox, text, conf) in results:
            if conf <= OCR_CONF:
                continue
            ok, sim = is_match(text, TARGET)
            if not ok:
                continue
            rx = int((bbox[0][0]+bbox[2][0])/2)
            ry = int((bbox[0][1]+bbox[2][1])/2)
            # ROI 밖(모니터 반사 등) 제외
            if ROT_ROI is not None:
                x0,y0,x1,y1 = ROT_ROI
                if not (x0 <= rx <= x1 and y0 <= ry <= y1):
                    print(f"  (ROI밖 제외) '{text}' at ({rx},{ry})")
                    continue
            candidates.append((rx, ry, text, conf, sim))

        if candidates:
            # 유사도 높은 순, 같으면 conf 높은 순
            candidates.sort(key=lambda c: (c[4], c[3]), reverse=True)
            if len(candidates) > 1:
                print(f"  매칭 후보 {len(candidates)}개:")
                for (rx,ry,text,conf,sim) in candidates:
                    print(f"    '{text}' conf={conf:.2f} 유사도={sim:.2f} at ({rx},{ry})")
            rx, ry, text, conf, sim = candidates[0]
            ox, oy = rotated_to_original(rx, ry, ow, oh)
            print(f"OCR 선택: '{text}' conf={conf:.2f} | 회전CAM({rx},{ry}) -> 원본CAM({ox},{oy})")
            act(ox, oy, "OCR:")
            found = True
        else:
            print("타겟 못 찾음. 읽힌 텍스트:")
            for (_, t, c) in results:
                if c > OCR_CONF: print(f"  '{t}' ({c:.2f})")
    elif k == ord('q'):
        break

cap.release(); cv2.destroyAllWindows(); ser.close()