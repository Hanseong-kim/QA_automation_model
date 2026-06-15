"""
1remove_app.py - 앱들을 롱프레스 -> Remove 눌러 삭제 (6개)

setting이랑 playstore만 삭제
좌표는 모두 좌하단 기준(LONGPRESS / CLICK).

"""
import serial, time

COM_PORT = "COM7"

# (이름, 앱 롱프레스 좌표, Remove 클릭 좌표)
APPS = [
    ("setting",    (100, 110), (130, 160)),
    ("play store", (190, 110), (190, 140)),
    # ("first",      (40, 320),  (65, 330)),
    # ("second",     (70, 320),  (105, 295)),
    # ("third",      (100, 310), (125, 325)),
    # # ("forth",      (130, 310), (150, 293)),
]

BG_TOUCH = (500, 500)   # 삭제 후 배경 터치 (메뉴 닫기)

ser = serial.Serial(COM_PORT, 115200, timeout=1)
time.sleep(2); ser.reset_input_buffer()
print("연결됨\n")

def send(cmd, wait=2, timeout=12):
    print(f"  전송: {cmd}")
    ser.reset_input_buffer()
    ser.write((cmd + '\n').encode())
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = ser.readline().decode(errors="ignore").strip()
        if line == "DONE":
            time.sleep(wait)
            return True
    print("  -> 시간초과")
    return False

def delete_app(name, app_pos, remove_pos):
    print(f"\n=== '{name}' 삭제 ===")
    ax, ay = app_pos
    rx, ry = remove_pos

    print(f"[1] '{name}' 롱프레스 ({ax},{ay})")
    send(f"LONGPRESS:{ax},{ay}", wait=1.5)   # 메뉴 뜰 시간

    print(f"[2] Remove 클릭 ({rx},{ry})")
    send(f"CLICK:{rx},{ry}", wait=2)

    print(f"[3] 배경 터치 ({BG_TOUCH[0]},{BG_TOUCH[1]}) - 메뉴 닫기")
    send(f"CLICK:{BG_TOUCH[0]},{BG_TOUCH[1]}", wait=1.5)

def main():
    print(f"총 {len(APPS)}개 앱 삭제 시작\n")
    for name, app_pos, remove_pos in APPS:
        delete_app(name, app_pos, remove_pos)
    print("\n=== 전체 완료 ===")
    ser.close()

if __name__ == "__main__":
    main()