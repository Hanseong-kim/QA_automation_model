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

    # Settings 삭제
    print('\n[1] Settings 삭제')
    send(s, 'LONGPRESS:190,205', wait=2)
    send(s, 'CLICKREL:130,-165', wait=2)
    send(s, 'CLICK:500,500', wait=2)

    # Play Store 삭제
    print('\n[2] Play Store 삭제')
    send(s, 'LONGPRESSBR:100,211', wait=3)
    send(s, 'CLICKREL:0,-90', wait=2)
    send(s, 'CLICK:500,500', wait=2)

    # slot1 삭제
    print('\n[3] slot1 삭제')
    send(s, 'LONGPRESSTL:100,120', wait=2)
    send(s, 'CLICKREL:100,-50', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    # slot2 삭제
    print('\n[4] slot2 삭제')
    send(s, 'MOVETL:100,120', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'LONGPRESSREL:0,0', wait=2)
    send(s, 'CLICKREL:130,60', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    # slot3 삭제
    print('\n[5] slot3 삭제')
    send(s, 'MOVETL:100,120', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'LONGPRESSREL:0,0', wait=2)
    send(s, 'CLICKREL:100,-50', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    # slot4 삭제
    print('\n[6] slot4 삭제')
    send(s, 'MOVETL:100,120', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'LONGPRESSREL:0,0', wait=2)
    send(s, 'CLICKREL:85,60', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    s.close()
    print('\nDone!')

if __name__ == "__main__":
    main()