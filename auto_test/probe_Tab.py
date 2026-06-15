# probe_tab.py - Tab 순서 탐색 도구
import serial, time

s = serial.Serial("COM7", 115200, timeout=1)
time.sleep(2)

def send(cmd):
    s.write((cmd + '\n').encode())
    deadline = time.time() + 10
    while time.time() < deadline:
        if s.readline().decode().strip() == 'DONE':
            return

print("명령: t=Tab, e=Enter, q=종료, 그외 텍스트=타이핑")
while True:
    c = input("> ").strip()
    if c == 'q': break
    elif c == 't': send("KEY:TAB")
    elif c == 'e': send("KEY:ENTER")
    elif c == 'le': send("LONGENTER")
    elif c == 'd': send("KEY:DOWN")
    elif c == 'u': send("KEY:UP")
    elif c == 'l': send("KEY:LEFT")
    elif c == 'r': send("KEY:RIGHT")
    else: send(f"TYPE:{c}")
s.close()