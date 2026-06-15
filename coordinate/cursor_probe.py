"""
cursor_probe.py - 커서가 카메라에 실제로 잡히는 순간이 있는지 '눈으로' 확인하는 진단 도구

검출 로직 없음. 그냥:
  - 커서를 한 좌표로 보내고, 그 자리에서 계속 좌우로 흔들어 '살려둠'
  - 흔드는 동안 카메라 원본 프레임을 연속으로 통째로 저장 (probe_frames/)
  - 너가 그 사진들을 넘겨보며 커서(▶)가 보이는 프레임이 있는지 확인

목적: "커서가 1초도 안 떠서 못 잡는다"가 진짜인지, 흔들면 떠 있는지부터 판정.
실행: python cursor_probe.py
"""
import cv2, serial, time, requests, os

COM_PORT = "COM7"
BASE_URL = "http://192.168.1.205:8080"
STREAM_URL = f"{BASE_URL}/video"
OUT_DIR = "probe_frames"
ROTATE = cv2.ROTATE_90_CLOCKWISE

TARGET = (130, 160)   # 커서 보낼 좌표 (화면 중앙쯤)
WIGGLE = 20           # 흔드는 진폭
N_FRAMES = 30         # 저장할 프레임 수

os.makedirs(OUT_DIR, exist_ok=True)
for f in os.listdir(OUT_DIR):       # 이전 결과 정리
    os.remove(os.path.join(OUT_DIR, f))

ser = serial.Serial(COM_PORT, 115200, timeout=1)
time.sleep(2); ser.reset_input_buffer()
print("ESP 연결됨")

def send(cmd, wait=0.0, timeout=10):
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode())
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ser.readline().decode(errors="ignore").strip() == "DONE":
            if wait: time.sleep(wait)
            return True
    return False

try:
    requests.get(f"{BASE_URL}/settings/focusmode", params={"set": "auto"}, timeout=5)
    requests.get(f"{BASE_URL}/focus", timeout=5); time.sleep(1.5)
    print("focus locked")
except Exception as e:
    print(f"포커스 실패(무시): {e}")

cap = cv2.VideoCapture(STREAM_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def grab(flush=1):
    for _ in range(flush): cap.grab()
    ret, f = cap.read()
    return cv2.rotate(f, ROTATE) if ret else None

print(f"\n커서를 {TARGET}로 보내고 흔들면서 {N_FRAMES}프레임 저장...")
print("저장되는 동안 태블릿 화면을 직접 보면서 커서가 뜨는지도 같이 확인해봐.\n")

send(f"MOVE:{TARGET[0]},{TARGET[1]}", wait=0.3)

saved = 0
for i in range(N_FRAMES):
    # 흔들기(커서 유지) - 매 프레임마다 한 번씩 까딱
    send(f"MOVEREL:{WIGGLE},0")
    f1 = grab(flush=1)
    if f1 is not None:
        cv2.imwrite(f"{OUT_DIR}/f{i:02d}a.png", f1); saved += 1
    send(f"MOVEREL:-{WIGGLE},0")
    f2 = grab(flush=1)
    if f2 is not None:
        cv2.imwrite(f"{OUT_DIR}/f{i:02d}b.png", f2); saved += 1
    print(f"  프레임 {i+1}/{N_FRAMES} 저장")

cap.release(); ser.close()
print(f"\n완료. {saved}장 저장됨 -> {OUT_DIR}/ 폴더")
print("그 폴더 사진들 빠르게 넘겨보면서 커서(▶)가 보이는 프레임이 있는지 확인해줘.")
print("커서가 좌우로 왔다갔다 하는 게 보이면 추적 가능. 한 장도 안 보이면 흔들기를 더 키워야 함.")