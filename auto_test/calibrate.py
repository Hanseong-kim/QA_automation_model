import serial
import json
import os
import time

COM_PORT = "COM7"
BAUD_RATE = 115200
CALIBRATION_FILE = "calibration.json"

def load_cal():
    if os.path.exists(CALIBRATION_FILE):
        with open(CALIBRATION_FILE, "r", encoding="utf-8") as f: 
            return json.load(f)
    return {}

def save_cal(data):
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def send_cmd(ser, cmd_str):
    print(f"전송: {cmd_str.strip()}")
    ser.reset_input_buffer()
    ser.write((cmd_str + '\n').encode())
    
    # 넉넉하게 10초 대기 (이동 거리가 멀거나 타이핑이 길 때 대비)
    deadline = time.time() + 10 
    while time.time() < deadline:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if line == "DONE":
                print("-> 동작 완료 (DONE)\n")
                return True
            elif line and line != "READY":
                print(f"ESP: {line}")
        except Exception as e:
            print(f"읽기 에러: {e}")
            break
            
    print("-> 응답 시간 초과!\n")
    return False

def main():
    print(f"ESP32 연결 시도 ({COM_PORT})...")
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        ser.reset_input_buffer()
        print("연결 성공!\n")
    except Exception as e:
        print(f"포트 열기 실패: {e}\n(다른 터미널이 COM7을 점유 중인지 확인해)")
        return

    cal_data = load_cal()
    last_coord = None 

    print("=== 🎯 태블릿 캘리브레이션 툴 ===")
    print("[1. 좌하단 기준 (기본)] - Settings 등 화면 왼쪽 앱")
    print("  m x y   : 이동 (MOVE)")
    print("  c x y   : 클릭 (CLICK)")
    print("  l x y   : 롱클릭 (LONGPRESS)")
    print("\n[2. 현재 위치 기준] - 앱 안에서 Remove 찌를 때")
    print("  rm dx dy : 상대 이동 (MOVEREL)")
    print("  rc dx dy : 상대 클릭 (CLICKREL)")
    print("  rl dx dy : 상대 롱클릭 (LONGPRESSREL)")
    print("\n[3. 기타 앵커 (보조)]")
    print("  tlm x y : 좌상단 기준 이동")
    print("  brm x y : 우하단 기준 이동 (Play Store 등)")
    print("\n[4. 시스템]")
    print("  s 이름  : 방금 쓴 좌표(x,y) 저장")
    print("  q       : 저장된 좌표 목록 보기")
    print("  t 텍스트: 타이핑")
    print("  exit    : 종료")
    print("==================================\n")

    while True:
        try:
            line = input("> ").strip()
            if not line: continue
            if line.lower() == "exit": break

            parts = line.split()
            cmd = parts[0].lower()

            # --- 단일 명령어 (저장, 조회, 타이핑 등) ---
            if cmd == "q":
                if not cal_data: print("저장된 좌표가 없어.")
                else:
                    for k, v in cal_data.items(): print(f"  {k}: {v}")
                continue
            elif cmd == "s" and len(parts) >= 2:
                if not last_coord:
                    print("이동/클릭 명령을 먼저 실행해야 저장할 수 있어.")
                    continue
                name = parts[1]
                cal_data[name] = last_coord
                save_cal(cal_data)
                print(f"[{name}] 좌표 {last_coord} 저장 완료!")
                continue
            elif cmd == "t" and len(parts) >= 2:
                send_cmd(ser, f"TYPE:{line[2:]}")
                continue
            elif cmd == "k" and len(parts) == 2:
                send_cmd(ser, f"KEY:{parts[1].upper()}")
                continue

            # --- 마우스 이동/클릭 명령어 파싱 ---
            if len(parts) != 3:
                print("입력 형식이 틀렸어. (예: m 100 200)")
                continue

            try:
                x, y = int(parts[1]), int(parts[2])
            except ValueError:
                print("좌표는 숫자만 입력해야 해.")
                continue

            last_coord = [x, y]
            cmd_str = ""

            # 기본 (좌하단 BL)
            if cmd == "m": cmd_str = f"MOVE:{x},{y}"
            elif cmd == "c": cmd_str = f"CLICK:{x},{y}"
            elif cmd == "l": cmd_str = f"LONGPRESS:{x},{y}"
            
            # 상대 이동 (REL)
            elif cmd == "rm": cmd_str = f"MOVEREL:{x},{y}"
            elif cmd == "rc": cmd_str = f"CLICKREL:{x},{y}"
            elif cmd == "rl": cmd_str = f"LONGPRESSREL:{x},{y}"

            # 좌상단 (TL)
            elif cmd == "tlm": cmd_str = f"MOVETL:{x},{y}"
            elif cmd == "tlc": cmd_str = f"CLICKTL:{x},{y}"
            elif cmd == "tll": cmd_str = f"LONGPRESSTL:{x},{y}"

            # 우하단 (BR)
            elif cmd == "brm": cmd_str = f"MOVEBR:{x},{y}"
            elif cmd == "brl": cmd_str = f"LONGPRESSBR:{x},{y}"
            
            else:
                print("알 수 없는 명령어입니다.")
                continue

            # ESP32로 명령 전송
            send_cmd(ser, cmd_str)

        except KeyboardInterrupt:
            print("\n안전하게 종료 중...")
            break
        except Exception as e:
            print(f"알 수 없는 에러 발생: {e}")

    ser.close()
    print("포트가 닫혔습니다.")

if __name__ == "__main__":
    main()