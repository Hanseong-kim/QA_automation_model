"""
test_sweep.py - 선형성 자동 확인. 한 축을 고정하고 다른 축을 0~400 자동 스윕.

명령:
  sx <y> <step>   : y 고정, x를 0~400까지 step 간격으로 자동 이동
  sy <x> <step>   : x 고정, y를 0~400까지 step 간격으로 자동 이동
  x y             : 한 점 이동
  q               : 종료

예:
  sx 200 50    -> y=200 고정, x=0,50,100,...,400 순서로 이동 (가로 선형 확인)
  sy 100 50    -> x=100 고정, y=0,50,...,400 (세로 선형 확인)
"""
import serial, time

COM_PORT = "COM7"
ser = serial.Serial(COM_PORT, 115200, timeout=2)
time.sleep(2); ser.reset_input_buffer()
print("연결됨.")
print("  sx <y> <step> : y고정 x스윕   |  sy <x> <step> : x고정 y스윕")
print("  x y : 한 점   |  q : 종료\n")

def send_wait(cmd, timeout=12):
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode())
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ser.readline().decode(errors="ignore").strip() == "DONE":
            return True
    return False

def sweep(fixed_axis, fixed_val, step, pause):
    """fixed_axis='x'면 x고정 y스윕, 'y'면 y고정 x스윕."""
    for v in range(0, 401, step):
        if fixed_axis == 'x':
            cmd = f"MOVE:{fixed_val},{v}"
        else:
            cmd = f"MOVE:{v},{fixed_val}"
        t0 = time.time()
        send_wait(cmd)
        print(f"  {cmd}  ({time.time()-t0:.1f}초) - 커서 확인...")
        time.sleep(pause)   # 눈으로 볼 시간

while True:
    s = input("> ").strip()
    if s == "q":
        break
    p = s.split()
    if len(p) == 3 and p[0] == "sx":
        # y고정, x스윕
        sweep('y', int(p[1]), int(p[2]), pause=1.0)
        print("  스윕 끝. x가 0->400 가는 동안 커서가 일정 간격으로 움직였으면 선형 OK")
    elif len(p) == 3 and p[0] == "sy":
        # x고정, y스윕
        sweep('x', int(p[1]), int(p[2]), pause=1.0)
        print("  스윕 끝. y가 0->400 가는 동안 일정 간격이면 선형 OK")
    elif len(p) == 2:
        try:
            x, y = int(p[0]), int(p[1])
            send_wait(f"MOVE:{x},{y}")
            print(f"  MOVE:{x},{y}")
        except ValueError:
            print("  형식 오류")
    else:
        print("  sx <y> <step> | sy <x> <step> | x y | q")

ser.close()
print("종료")