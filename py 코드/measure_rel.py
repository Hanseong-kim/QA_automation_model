"""
measure_rel.py - 앱 롱프레스 -> Remove까지 상대이동(dx,dy) 측정

앱을 롱프레스한 뒤, MOVEREL로 커서를 Remove까지 옮기며 dx,dy를 찾음.
방향별(위/아래)로 한 번씩만 찾으면 같은 방향 앱은 같은 값 사용.

명령:
  lp x y    : 앱 롱프레스 (메뉴 띄움) - 측정한 앱 ESP 좌표
  r dx dy   : MOVEREL (현재 위치에서 상대이동) - Remove까지 조금씩
  c         : 현재 위치 제자리 클릭 (CLICKREL:0,0) - Remove 맞으면 확인용
  bg        : 배경터치(500,500) - 메뉴 닫기
  reset x y : 롱프레스 다시 (메뉴 다시 띄우고 누적 dx,dy 리셋)
  q         : 종료

측정법:
  1) lp 40 320      -> Radius 메뉴 (위 방향 앱)
  2) r 20 30        -> 커서 조금 이동, 누적 표시됨
  3) r 5 10         -> 더 조정... Remove에 닿을때까지
  4) 누적 dx,dy 기록! (이게 '위 방향' 이동값)
  5) bg
  6) Files로 '아래 방향'도 측정
"""
import serial, time

COM_PORT = "COM7"
ser = serial.Serial(COM_PORT, 115200, timeout=1)
time.sleep(2); ser.reset_input_buffer()
print("연결됨.")
print("  lp x y : 앱 롱프레스   r dx dy : 상대이동   c : 제자리클릭")
print("  bg : 메뉴닫기   q : 종료\n")
print("측정: lp로 메뉴 -> r로 Remove까지 조금씩 -> 누적값 기록\n")

acc = [0, 0]   # 누적 상대이동

def send(cmd, timeout=12):
    ser.reset_input_buffer()
    ser.write((cmd+"\n").encode())
    t0=time.time()
    while time.time()-t0<timeout:
        if ser.readline().decode(errors="ignore").strip()=="DONE":
            return True
    print("  시간초과"); return False

while True:
    s = input("> ").strip()
    if s == "q": break
    p = s.split()
    if s == "bg":
        send("CLICK:500,500"); acc=[0,0]; print("  메뉴 닫음, 누적 리셋")
    elif s == "c":
        send("CLICKREL:0,0"); print(f"  제자리 클릭 (누적 dx={acc[0]}, dy={acc[1]})")
    elif p[0] == "lp" and len(p)==3:
        send(f"LONGPRESS:{p[1]},{p[2]}")
        acc=[0,0]; print(f"  롱프레스 {p[1]},{p[2]} -> 메뉴, 누적 리셋")
    elif p[0] == "reset" and len(p)==3:
        send(f"LONGPRESS:{p[1]},{p[2]}")
        acc=[0,0]; print(f"  재롱프레스, 누적 리셋")
    elif p[0] == "r" and len(p)==3:
        try: dx,dy=int(p[1]),int(p[2])
        except ValueError: print("  숫자"); continue
        send(f"MOVEREL:{dx},{dy}")
        acc[0]+=dx; acc[1]+=dy
        print(f"  이동 ({dx},{dy}) -> 누적 dx={acc[0]}, dy={acc[1]}")
    else:
        print("  lp x y / r dx dy / c / bg / q")

ser.close(); print("종료")