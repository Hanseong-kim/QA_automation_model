import serial
import time

COM_PORT = "COM7"
BAUD_RATE = 115200

def send(s, cmd, wait=2):
    s.write((cmd + '\n').encode())
    deadline = time.time() + 10
    while time.time() < deadline:
        line = s.readline().decode().strip()
        if line:
            print(f'  <- {line}')
        if line == 'DONE':
            time.sleep(wait)
            return True
    return False

def main():
    s = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print("Connected. Starting delete...")

    print('\n[1] Settings 삭제')
    send(s, 'LONGPRESS::100,110', wait=2)
    send(s, 'MOVEREL:130,-165', wait=2)
    #send(s, 'CLICKREL:130,-165', wait=2)
    send(s, 'CLICK:500,500', wait=2)

    # Play Store 삭제
    print('\n[2] Play Store 삭제')
    send(s, 'MOVE:190,205', wait=1)
    send(s, 'LONGPRESSREL:202,0', wait=3)
    #send(s, 'CLICKREL:0,-90', wait=2)
    send(s, 'MOVEREL:0,-90', wait=2)
    send(s, 'CLICK:500,500', wait=2)

    s.close()
    print('\nDone!')

if __name__ == "__main__":
    main()