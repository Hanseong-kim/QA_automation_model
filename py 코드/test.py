import serial
import time
import cv2
import numpy as np

COM_PORT = "COM7"
BAUD_RATE = 115200
STREAM_URL = "http://192.168.1.205:8080/video"

# 테스트할 ESP 좌표 목록
TEST_POINTS = [
    (100, 200),
    (100, 150),
    (100, 120),
    (200, 100),
    (200, 150),
    (200, 200),
]

def send(s, cmd, wait=2):
    s.write((cmd + '\n').encode())
    deadline = time.time() + 10
    while time.time() < deadline:
        line = s.readline().decode().strip()
        if line == 'DONE':
            time.sleep(wait)
            return True
    return False

def get_frame(cap):
    for _ in range(10):
        cap.grab()
    ret, frame = cap.retrieve()
    if ret:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    return ret, frame

def find_cursor(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((3,3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 30 < area < 800:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / h if h > 0 else 0
            if 0.3 < aspect < 3.0:
                cx = x + w // 2
                cy = y + h // 2
                candidates.append((cx, cy, area))

    if candidates:
        candidates.sort(key=lambda c: -c[2])
        return candidates[0][0], candidates[0][1]
    return None, None

def main():
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Connected.")

    cap = cv2.VideoCapture(STREAM_URL)
    time.sleep(1)

    calib_points = []

    # 배경 프레임 (커서 없는 상태)
    print("배경 캡처 중... (커서 화면 밖으로)")
    send(ser, "MOVE:0,0", wait=3)
    ret, bg_frame = get_frame(cap)
    cv2.imwrite('bg.jpg', bg_frame)
    print("배경 저장됨")

    for i, (ex, ey) in enumerate(TEST_POINTS):
        print(f"\n[{i+1}/{len(TEST_POINTS)}] ESP:({ex},{ey}) 이동 중...")
        send(ser, f"LONGPRESS:{ex},{ey}", wait=3)
        time.sleep(1)

        ret, frame = get_frame(cap)
        if not ret:
            print("  프레임 못 받음, 스킵")
            continue

        cv2.imwrite(f'calib_{i}.jpg', frame)

        # 배경과 차이로 커서 찾기
        diff = cv2.absdiff(bg_frame, frame)
        diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, diff_bin = cv2.threshold(diff_gray, 30, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(diff_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > best_area:
                best_area = area
                best = cnt

        if best is not None:
            x, y, w, h = cv2.boundingRect(best)
            px, py = x + w // 2, y + h // 2
            print(f"  커서 찾음: 사진({px},{py})")
            calib_points.append((ex, ey, px, py))
        else:
            print(f"  커서 못 찾음")

    print(f"\n=== 결과 ({len(calib_points)}개) ===")
    for p in calib_points:
        print(f"  ESP:({p[0]},{p[1]}) → Photo:({p[2]},{p[3]})")

    cap.release()
    ser.close()

if __name__ == "__main__":
    main()