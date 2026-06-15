# login.py - Tab 네비게이션 기반 로그인 자동화
# probe_tab.py로 확인한 시퀀스를 그대로 옮긴 버전 (좌표 클릭 최소)
#
# 확인된 시퀀스:
#   화면0   (진입)    : CLICK(120,20) -> Tab x2 -> Enter
#   화면0.5 (추가)    : Tab x3 -> Enter -> Enter -> Tab x2 -> Enter -> CLICK(90,20)
#   화면1 (이메일)   : Tab, Tab -> email -> Tab, Tab -> Enter (로그인 처리 2초+)
#   화면2 (비밀번호) : Tab -> password -> (대기) -> Tab, Tab -> Enter
#   화면3 (PIN)      : Tab, Tab, Tab -> PIN  (끝에 Enter 없음)

import serial
import time

COM_PORT = "COM7"
BAUD = 115200

# 로그인 정보 (필요시 여기만 수정)
EMAIL = "test@radiusxr.com"
PASSWORD = "production2023"
PIN = "5994"

s = serial.Serial(COM_PORT, BAUD, timeout=1)
time.sleep(2)
print("Connected. Starting login...")


def send(cmd, wait=0.4):
    """명령 전송 후 펌웨어의 DONE 응답을 기다리고, 추가로 wait초 대기."""
    print(f'  -> {cmd}')
    s.write((cmd + '\n').encode())
    deadline = time.time() + 10
    while time.time() < deadline:
        # errors="ignore": ESP가 깨진 바이트 흘려도 UnicodeDecodeError로 안 죽게
        if s.readline().decode(errors="ignore").strip() == 'DONE':
            time.sleep(wait)
            return True
    print('  시간초과')
    return False


def tab(n=1, wait=0.4):
    for _ in range(n):
        send("KEY:TAB", wait)


def enter(wait=3.0):
    # 화면 전환을 동반하는 Enter는 넉넉히 대기
    send("KEY:ENTER", wait)


def type_text(text, wait=0.5):
    send(f"TYPE:{text}", wait)


def click(x, y, wait=1.0):
    # 좌하단(BL) 기준 클릭 — calibrate.py의 'c x y'와 동일
    send(f"CLICK:{x},{y}", wait)


# ── 화면0: 진입 (클릭 + Tab + Enter) ────────────
# print('\n[화면0] 로그인 화면 진입')
# click(120, 20)         # c 120 20
# tab(2)                 # t, t
# enter()                # e  (화면 전환 대기)

# # ── 화면0.5: 추가 시퀀스 (Tab/Enter + 클릭) ──────
# print('\n[화면0.5] 추가 시퀀스')
# tab(3)                 # t, t, t
# enter()                # e
# enter()                # e
# tab(2)                 # t, t
# enter()                # e
# click(90, 20)          # 90,20 클릭

# ── 화면1: 이메일 ──────────────────────────────
print('\n[화면1] 이메일')
tab(2)                 # t, t
type_text(EMAIL)       # test@radiusxr.com
tab(2)                 # t, t
enter(wait=5)          # e  (로그인 처리 2초+ -> 화면2 뜰 때까지 넉넉히 대기)

# ── 화면2: 비밀번호 ────────────────────────────
print('\n[화면2] 비밀번호')
tab(1)                 # t
type_text(PASSWORD, wait=2.5)   # production2023 (비번 친 뒤 추가 대기)
tab(2)                 # t, t
enter(wait=5)          # e  (로그인 처리 대기 -> 화면3)

# ── 화면3: PIN ─────────────────────────────────
print('\n[화면3] PIN')
tab(3)                 # t, t, t
type_text(PIN)         # 5994
# PIN은 보통 4자리 입력 완료 시 자동 제출됨.
# 만약 자동 제출이 안 되면 아래 주석 해제:
# enter()

s.close()
print('\nDone!')