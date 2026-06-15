import serial, time
from lib.config import COM_PORT, BAUD_RATE

_ser = None

def init(port=COM_PORT, baud=BAUD_RATE):
    global _ser
    _ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)
    _ser.reset_input_buffer()
    return _ser

def send(cmd, wait=2, timeout=12):
    print(f"  전송: {cmd}")
    _ser.reset_input_buffer()
    _ser.write((cmd + '\n').encode())
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = _ser.readline().decode(errors="ignore").strip()
        if line == "DONE":
            time.sleep(wait)
            return True
    print("  -> 시간초과")
    return False

def close():
    if _ser and _ser.is_open:
        _ser.close()
