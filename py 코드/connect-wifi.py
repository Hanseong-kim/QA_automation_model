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
    print("Connected. Opening Internet settings...")

    print('\n[1] Settings 클릭')
    send(s, 'CLICKTL:240,180', wait=3)

    print('\n[2] Network & Internet 클릭')
    send(s, 'CLICKTL:240,170', wait=3)

    print('\n[3] Internet 클릭')
    send(s, 'CLICKTL:240,165', wait=3)

    s.close()
    print('\nDone! Internet 창 열림')

if __name__ == "__main__":
    main()