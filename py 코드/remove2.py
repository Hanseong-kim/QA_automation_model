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
    print("Connected. Starting test...")

    # slot1 - tl 100 120에서 바로
    print('\n[1] slot1')
    send(s, 'LONGPRESSTL:100,120', wait=2)
    send(s, 'MOVEREL:100,-50', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    # slot2 - tl 100 120 → r 120 0
    print('\n[2] slot2')
    send(s, 'MOVETL:100,120', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'LONGPRESSREL:0,0', wait=2)
    send(s, 'MOVEREL:130,60', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    # slot3 - tl 100 120 → r 120 0 → r 120 0
    print('\n[3] slot3')
    send(s, 'MOVETL:100,120', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'LONGPRESSREL:0,0', wait=2)
    send(s, 'MOVEREL:100,-50', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    # slot4 - tl 100 120 → r 120 0 × 3
    print('\n[4] slot4')
    send(s, 'MOVETL:100,120', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'MOVEREL:120,0', wait=1)
    send(s, 'LONGPRESSREL:0,0', wait=2)
    send(s, 'MOVEREL:85,60', wait=2)
    send(s, 'CLICK:200,300', wait=2)

    s.close()
    print('\nDone!')

if __name__ == "__main__":
    main()