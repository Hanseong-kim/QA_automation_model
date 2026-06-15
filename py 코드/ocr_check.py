"""
ocr_check.py - 화면 OCR 진단. radius 라벨 / Remove 글자가 읽히는지 확인.

조작:
  l : 현재 화면 OCR -> 모든 글자 + 화면좌표(회전 후 x,y) 출력
  s : 결과 이미지 저장 (image2 폴더)
  q : 종료

용도:
  - 홈 화면에서 l -> 앱 라벨에 'radius' 읽히는지
  - 앱 롱프레스 후 l -> 'Remove' 읽히는지, 위치 어디인지
"""
import cv2, numpy as np, easyocr, time

STREAM_URL = "http://192.168.1.205:8080/video"
OUT = "C:/hansung/project/radius-auto/image2"
OCR_CONF = 0.3

cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
print("EasyOCR 로딩...")
reader = easyocr.Reader(['en'])
print("l=OCR  s=저장  q=종료\n")

def grab(flush=10):
    for _ in range(flush): cap.grab()
    ret, f = cap.read(); return f if ret else None

last_vis = None
while True:
    f = grab(2)
    if f is None: time.sleep(0.2); continue
    rot = cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE)
    disp = last_vis if last_vis is not None else rot
    cv2.imshow("ocr_check", disp)
    k = cv2.waitKey(30) & 0xFF

    if k == ord('l'):
        frame = grab(10)
        rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        results = reader.readtext(rot)
        vis = rot.copy()
        print(f"\n=== OCR {len(results)}개 (회전화면 x,y) ===")
        for (bbox, text, conf) in results:
            if conf <= OCR_CONF: continue
            cx = int((bbox[0][0]+bbox[2][0])/2)
            cy = int((bbox[0][1]+bbox[2][1])/2)
            pts = np.array(bbox, dtype=np.int32)
            cv2.polylines(vis, [pts], True, (0,255,0), 2)
            cv2.putText(vis, text, (pts[0][0], pts[0][1]-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
            print(f"  '{text}' conf={conf:.2f}  x={cx} y={cy}")
        last_vis = vis
    elif k == ord('s'):
        if last_vis is not None:
            cv2.imwrite(f"{OUT}/ocr_check.jpg", last_vis)
            print(f"저장: {OUT}/ocr_check.jpg")
    elif k == ord('q'):
        break

cap.release(); cv2.destroyAllWindows()