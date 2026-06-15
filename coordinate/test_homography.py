"""
test_homography.py - 마우스 클릭 연동 ESP 제어 테스트
화면을 마우스로 클릭하면, 캘리브레이션 데이터를 이용해 ESP 좌표를 계산하고 즉시 모터를 이동시킵니다.
"""
import cv2, numpy as np, serial, json, time, os

COM_PORT = "COM7"
BASE_URL = "http://192.168.1.205:8080"
STREAM_URL = f"{BASE_URL}/video"
CALIB_FILE = "homography.json"

# --- [여기 추가] 캡처 폴더 생성 ---
CAPTURE_DIR = "test_captures"
os.makedirs(CAPTURE_DIR, exist_ok=True)
need_capture = False  # 캡처 트리거용 플래그
# ----------------------------------

# 1. 캘리브레이션 데이터 불러오기
try:
    with open(CALIB_FILE, "r") as f:
        data = json.load(f)
        H_px2esp = np.array(data["H_px2esp"], dtype=np.float32)
        ROI_CORNERS = np.array(data["roi"], dtype=np.int32)
    print(f"✅ 캘리브레이션 데이터 로드 완료 ({CALIB_FILE})")
except Exception as e:
    print(f"❌ 데이터 로드 실패: {e}")
    exit()

# 2. ESP 시리얼 연결
try:
    ser = serial.Serial(COM_PORT, 115200, timeout=1)
    time.sleep(2)
    ser.reset_input_buffer()
    print("✅ ESP 연결됨")
except Exception as e:
    print(f"❌ ESP 연결 실패: {e}")
    exit()

def send_esp(cmd):
    """ESP로 명령 전송"""
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode())
    # 여기서는 빠른 피드백을 위해 DONE 응답을 무한 대기하지 않고 넘깁니다.

# 3. 카메라 세팅
cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab():
    for _ in range(2): cap.grab()
    ret, f = cap.read()
    return cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE) if ret else None

# 마우스 이벤트 처리기
target_px = None
target_esp = None

def on_mouse(event, x, y, flags, param):
    # [핵심 수정] 여기에 need_capture를 전역 변수로 연결해 주어야 합니다!
    global target_px, target_esp, need_capture
    
    if event == cv2.EVENT_LBUTTONDOWN:
        target_px = (x, y)
        
        # 카메라 픽셀(x, y) -> ESP 좌표로 변환 (마법의 공식)
        pt_px = np.array([[[x, y]]], dtype=np.float32)
        pt_esp = cv2.perspectiveTransform(pt_px, H_px2esp).reshape(2)
        
        esp_x = int(pt_esp[0])
        esp_y = int(pt_esp[1])
        target_esp = (esp_x, esp_y)
        
        print(f"🖱️ 클릭 픽셀: ({x}, {y})  =>  🤖 전송할 ESP 좌표: ({esp_x}, {esp_y})")
        
        # ESP로 이동 명령 전송
        send_esp(f"MOVE:{esp_x},{esp_y}")
        
        # 이제 전역 변수로 정상 인식되어 메인 루프에 신호가 갑니다.
        need_capture = True

# 메인 루프
cv2.namedWindow("ESP Control Test (Click to Move)", cv2.WINDOW_NORMAL)
cv2.setMouseCallback("ESP Control Test (Click to Move)", on_mouse)

print("\n=== 테스트를 시작합니다 ===")
print("- 화면의 아무 곳이나 마우스로 클릭해 보세요.")
print("- 모터가 이동한 후, 태블릿 화면의 커서가 클릭한 위치와 일치하는지 확인하세요.")
print("- 종료하려면 'q'를 누르세요.\n")

while True:
    frame = grab()
    if frame is None: continue
    disp = frame.copy()
    
    # 캘리브레이션 기준이 된 ROI(태블릿 화면 테두리) 그려주기
    cv2.polylines(disp, [ROI_CORNERS], True, (0, 255, 0), 2)
    cv2.putText(disp, "Click anywhere inside the green box!", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # 클릭했던 목표점 표시
    if target_px and target_esp:
        cx, cy = target_px
        cv2.drawMarker(disp, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 30, 2)
        cv2.putText(disp, f"ESP: {target_esp}", (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    cv2.imshow("ESP Control Test (Click to Move)", disp)
    
# --- [여기 추가] 모터 이동이 끝나면 최신 화면 캡처 ---
    if need_capture:
        cv2.waitKey(1) # UI 업데이트 허용
        
        # 안내 문구도 3초로 수정
        print("⏳ 모터 이동 및 화면 갱신 대기중... (3초 대기)") 
        
        # [핵심 수정] 대기 시간을 1.5초에서 3.0초로 넉넉하게 변경!
        time.sleep(8.0) 
        
        fresh_frame = grab() # 버퍼를 강제로 비우고 가장 최신의 실제 화면 가져오기
        if fresh_frame is not None:
            # 저장할 사진에도 내가 클릭했던 목표점(빨간 십자가)을 그려서 오차 확인을 쉽게 함
            cx, cy = target_px
            cv2.drawMarker(fresh_frame, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 30, 2)
            cv2.circle(fresh_frame, (cx, cy), 5, (0, 0, 255), -1)
            
            filename = f"{CAPTURE_DIR}/result_esp_{target_esp[0]}_{target_esp[1]}.jpg"
            cv2.imwrite(filename, fresh_frame)
            print(f"📸 실제 커서 이동 결과 캡처 완료: {filename}\n")
            
        need_capture = False
    # -----------------------------------------------------   
    
    if cv2.waitKey(30) & 0xFF == ord('q'):
        break

cap.release()
ser.close()
cv2.destroyAllWindows()
print("테스트 종료.")