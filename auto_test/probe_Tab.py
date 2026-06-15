# probe_tab.py - Tab/방향키 탐색 도구
import serial, time

s = serial.Serial("COM7", 115200, timeout=1)
time.sleep(2)
print("연결됨. 명령: t=Tab, e=Enter, le=LongEnter, u/d/l/r=방향키, q=종료, 그외=타이핑")

history = []

def send(cmd):
    s.write((cmd + '\n').encode())
    deadline = time.time() + 10
    while time.time() < deadline:
        if s.readline().decode(errors="ignore").strip() == 'DONE':
            return True
    print("  ⚠ 타임아웃 (펌웨어에 이 명령이 없을 수 있음)")
    return False

CMD = {'t':"KEY:TAB", 'e':"KEY:ENTER", 'le':"LONGENTER",
       'u':"KEY:UP", 'd':"KEY:DOWN", 'l':"KEY:LEFT", 'r':"KEY:RIGHT"}

while True:
    c = input("> ").strip()
    if c == 'q':
        break
    cmd = CMD.get(c, f"TYPE:{c}")
    ok = send(cmd)
    if ok:
        history.append(cmd)
        print("  히스토리:", " → ".join(history))

s.close()
if history:
    fn = f"probe_{int(time.time())}.txt"
    with open(fn, "w", encoding="utf-8") as f:
        f.write(" → ".join(history))
    print(f"저장됨: {fn}")