"""
test_esp32.py
ESP32 HID 컨트롤러 시리얼 테스트 스크립트.
Arduino 펌웨어의 모든 명령을 함수로 래핑하고 테스트 시나리오를 실행한다.
"""

import time
import serial
import serial.tools.list_ports

# ── 설정 ──────────────────────────────────────────────────────────────────────
PORT      = "COM7"      # None 으로 바꾸면 자동 탐색
BAUD      = 115200
TIMEOUT   = 60          # DONE 대기 최대 초
# ─────────────────────────────────────────────────────────────────────────────


def find_esp32_port() -> str | None:
    """CP210x / CH340 칩 기반 포트를 자동 탐색."""
    KEYWORDS = ("cp210", "ch340", "ch341", "esp32", "uart", "usb serial")
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in KEYWORDS):
            return p.device
    return None


class ESP32Controller:
    def __init__(self, port: str | None = PORT, baud: int = BAUD, timeout: int = TIMEOUT):
        if port is None:
            port = find_esp32_port()
            if port is None:
                raise RuntimeError("ESP32 포트를 찾을 수 없습니다. PORT 변수를 직접 설정하세요.")
            print(f"[자동감지] {port}")

        self.timeout = timeout
        self.ser = serial.Serial(port, baud, timeout=1)
        print(f"Connected: {port} @ {baud}")
        self._wait_ready()

    def _wait_ready(self):
        """부팅 후 READY 신호 대기."""
        print("READY 대기 중...", end="", flush=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            line = self.ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                print(f" [{line}]")
            if line == "READY":
                return
        print("\n경고: READY 신호를 받지 못했습니다. 계속 진행합니다.")

    def _send(self, cmd: str) -> bool:
        """명령 전송 후 DONE 또는 에러 대기. 성공 시 True."""
        self.ser.reset_input_buffer()
        payload = (cmd + "\n").encode("utf-8")
        self.ser.write(payload)
        print(f"  → {cmd}")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                print(f"  ← {line}")
            if line == "DONE":
                return True
            if line.startswith("ERROR"):
                print(f"  !! 에러 응답: {line}")
                return False

        print(f"  !! 타임아웃: DONE 미수신 ({self.timeout}s)")
        return False

    def close(self):
        self.ser.close()
        print("포트 닫힘.")

    # ── 이동 ──────────────────────────────────────────────────────────────────
    def move(self, x: int, y: int) -> bool:
        """좌하단 기준 절대 이동 (클릭 없음)."""
        return self._send(f"MOVE:{x},{y}")

    def move_tl(self, x: int, y: int) -> bool:
        """좌상단 기준 절대 이동."""
        return self._send(f"MOVETL:{x},{y}")

    def move_br(self, x: int, y: int) -> bool:
        """우하단 기준 절대 이동."""
        return self._send(f"MOVEBR:{x},{y}")

    def move_rel(self, dx: int, dy: int) -> bool:
        """현재 위치에서 상대 이동."""
        return self._send(f"MOVEREL:{dx},{dy}")

    # ── 클릭 ──────────────────────────────────────────────────────────────────
    def click(self, x: int, y: int) -> bool:
        """좌하단 기준 좌표로 이동 후 클릭."""
        return self._send(f"CLICK:{x},{y}")

    def click_tl(self, x: int, y: int) -> bool:
        """좌상단 기준 좌표로 이동 후 클릭."""
        return self._send(f"CLICKTL:{x},{y}")

    def click_rel(self, dx: int, dy: int) -> bool:
        """상대 이동 후 클릭."""
        return self._send(f"CLICKREL:{dx},{dy}")

    # ── 롱프레스 ──────────────────────────────────────────────────────────────
    def long_press(self, x: int, y: int) -> bool:
        """좌하단 기준 좌표로 이동 후 1.5초 롱프레스."""
        return self._send(f"LONGPRESS:{x},{y}")

    def long_press_tl(self, x: int, y: int) -> bool:
        return self._send(f"LONGPRESSTL:{x},{y}")

    def long_press_br(self, x: int, y: int) -> bool:
        return self._send(f"LONGPRESSBR:{x},{y}")

    def long_press_rel(self, dx: int, dy: int) -> bool:
        return self._send(f"LONGPRESSREL:{dx},{dy}")

    # ── 스와이프 ──────────────────────────────────────────────────────────────
    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """좌하단 기준 절대 좌표 스와이프."""
        return self._send(f"SWIPE:{x1},{y1},{x2},{y2}")

    def swipe_rel(self, dx: int, dy: int) -> bool:
        """현재 위치에서 상대 드래그."""
        return self._send(f"SWIPEREL:{dx},{dy}")

    # ── 키보드 ────────────────────────────────────────────────────────────────
    def type_text(self, text: str) -> bool:
        """문자열 입력."""
        return self._send(f"TYPE:{text}")

    def key_tab(self) -> bool:
        return self._send("KEY:TAB")

    def key_enter(self) -> bool:
        return self._send("KEY:ENTER")

    def key_esc(self) -> bool:
        return self._send("KEY:ESC")


# ── 테스트 시나리오 ────────────────────────────────────────────────────────────

def test_basic_movement(esp: ESP32Controller):
    print("\n=== [1] 기본 이동 테스트 ===")
    esp.move(200, 400)
    time.sleep(0.3)
    esp.move_tl(200, 400)
    time.sleep(0.3)
    esp.move_rel(50, -50)


def test_click(esp: ESP32Controller):
    print("\n=== [2] 클릭 테스트 ===")
    esp.click(400, 800)
    time.sleep(0.5)
    esp.click_tl(400, 200)


def test_long_press(esp: ESP32Controller):
    print("\n=== [3] 롱프레스 테스트 ===")
    esp.long_press(400, 600)


def test_swipe(esp: ESP32Controller):
    print("\n=== [4] 스와이프 테스트 ===")
    # 화면 아래쪽에서 위로 스와이프 (스크롤 업)
    esp.swipe(400, 300, 400, 900)
    time.sleep(0.5)
    # 위에서 아래로 (스크롤 다운)
    esp.swipe(400, 900, 400, 300)
    time.sleep(0.5)
    # 상대 스와이프
    esp.move(400, 600)
    esp.swipe_rel(200, 0)    # 오른쪽으로 200px


def test_keyboard(esp: ESP32Controller):
    print("\n=== [5] 키보드 테스트 ===")
    esp.click(400, 600)      # 입력 필드 클릭
    time.sleep(0.3)
    esp.type_text("hello")
    esp.key_tab()
    esp.type_text("world")
    esp.key_enter()


def run_all_tests(esp: ESP32Controller):
    test_basic_movement(esp)
    test_click(esp)
    test_long_press(esp)
    test_swipe(esp)
    test_keyboard(esp)
    print("\n=== 모든 테스트 완료 ===")


"""
test_esp32.py
ESP32 HID 컨트롤러 시리얼 테스트 스크립트.
Arduino 펌웨어의 모든 명령을 함수로 래핑하고 테스트 시나리오를 실행한다.
"""

import time
import serial
import serial.tools.list_ports

# ── 설정 ──────────────────────────────────────────────────────────────────────
PORT      = "COM7"      # None 으로 바꾸면 자동 탐색
BAUD      = 115200
TIMEOUT   = 60          # DONE 대기 최대 초
# ─────────────────────────────────────────────────────────────────────────────


def find_esp32_port() -> str | None:
    """CP210x / CH340 칩 기반 포트를 자동 탐색."""
    KEYWORDS = ("cp210", "ch340", "ch341", "esp32", "uart", "usb serial")
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in KEYWORDS):
            return p.device
    return None


class ESP32Controller:
    def __init__(self, port: str | None = PORT, baud: int = BAUD, timeout: int = TIMEOUT):
        if port is None:
            port = find_esp32_port()
            if port is None:
                raise RuntimeError("ESP32 포트를 찾을 수 없습니다. PORT 변수를 직접 설정하세요.")
            print(f"[자동감지] {port}")

        self.timeout = timeout
        self.ser = serial.Serial(port, baud, timeout=1)
        print(f"Connected: {port} @ {baud}")
        self._wait_ready()

    def _wait_ready(self):
        """부팅 후 READY 신호 대기."""
        print("READY 대기 중...", end="", flush=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            line = self.ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                print(f" [{line}]")
            if line == "READY":
                return
        print("\n경고: READY 신호를 받지 못했습니다. 계속 진행합니다.")

    def _send(self, cmd: str) -> bool:
        """명령 전송 후 DONE 또는 에러 대기. 성공 시 True."""
        self.ser.reset_input_buffer()
        payload = (cmd + "\n").encode("utf-8")
        self.ser.write(payload)
        print(f"  → {cmd}")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                print(f"  ← {line}")
            if line == "DONE":
                return True
            if line.startswith("ERROR"):
                print(f"  !! 에러 응답: {line}")
                return False

        print(f"  !! 타임아웃: DONE 미수신 ({self.timeout}s)")
        return False

    def close(self):
        self.ser.close()
        print("포트 닫힘.")

    # ── 이동 ──────────────────────────────────────────────────────────────────
    def move(self, x: int, y: int) -> bool:
        """좌하단 기준 절대 이동 (클릭 없음)."""
        return self._send(f"MOVE:{x},{y}")

    def move_tl(self, x: int, y: int) -> bool:
        """좌상단 기준 절대 이동."""
        return self._send(f"MOVETL:{x},{y}")

    def move_br(self, x: int, y: int) -> bool:
        """우하단 기준 절대 이동."""
        return self._send(f"MOVEBR:{x},{y}")

    def move_rel(self, dx: int, dy: int) -> bool:
        """현재 위치에서 상대 이동."""
        return self._send(f"MOVEREL:{dx},{dy}")

    # ── 클릭 ──────────────────────────────────────────────────────────────────
    def click(self, x: int, y: int) -> bool:
        """좌하단 기준 좌표로 이동 후 클릭."""
        return self._send(f"CLICK:{x},{y}")

    def click_tl(self, x: int, y: int) -> bool:
        """좌상단 기준 좌표로 이동 후 클릭."""
        return self._send(f"CLICKTL:{x},{y}")

    def click_rel(self, dx: int, dy: int) -> bool:
        """상대 이동 후 클릭."""
        return self._send(f"CLICKREL:{dx},{dy}")

    # ── 롱프레스 ──────────────────────────────────────────────────────────────
    def long_press(self, x: int, y: int) -> bool:
        """좌하단 기준 좌표로 이동 후 1.5초 롱프레스."""
        return self._send(f"LONGPRESS:{x},{y}")

    def long_press_tl(self, x: int, y: int) -> bool:
        return self._send(f"LONGPRESSTL:{x},{y}")

    def long_press_br(self, x: int, y: int) -> bool:
        return self._send(f"LONGPRESSBR:{x},{y}")

    def long_press_rel(self, dx: int, dy: int) -> bool:
        return self._send(f"LONGPRESSREL:{dx},{dy}")

    # ── 스와이프 ──────────────────────────────────────────────────────────────
    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """좌하단 기준 절대 좌표 스와이프."""
        return self._send(f"SWIPE:{x1},{y1},{x2},{y2}")

    def swipe_rel(self, dx: int, dy: int) -> bool:
        """현재 위치에서 상대 드래그."""
        return self._send(f"SWIPEREL:{dx},{dy}")

    # ── 키보드 ────────────────────────────────────────────────────────────────
    def type_text(self, text: str) -> bool:
        """문자열 입력."""
        return self._send(f"TYPE:{text}")

    def key_tab(self) -> bool:
        return self._send("KEY:TAB")

    def key_enter(self) -> bool:
        return self._send("KEY:ENTER")

    def key_esc(self) -> bool:
        return self._send("KEY:ESC")


# ── 테스트 시나리오 ────────────────────────────────────────────────────────────

def test_basic_movement(esp: ESP32Controller):
    print("\n=== [1] 기본 이동 테스트 ===")
    esp.move(200, 400)
    time.sleep(0.3)
    esp.move_tl(200, 400)
    time.sleep(0.3)
    esp.move_rel(50, -50)


def test_click(esp: ESP32Controller):
    print("\n=== [2] 클릭 테스트 ===")
    esp.click(400, 800)
    time.sleep(0.5)
    esp.click_tl(400, 200)


def test_long_press(esp: ESP32Controller):
    print("\n=== [3] 롱프레스 테스트 ===")
    esp.long_press(400, 600)


def test_swipe(esp: ESP32Controller):
    print("\n=== [4] 스와이프 테스트 ===")
    # 화면 아래쪽에서 위로 스와이프 (스크롤 업)
    esp.swipe(400, 300, 400, 900)
    time.sleep(0.5)
    # 위에서 아래로 (스크롤 다운)
    esp.swipe(400, 900, 400, 300)
    time.sleep(0.5)
    # 상대 스와이프
    esp.move(400, 600)
    esp.swipe_rel(200, 0)    # 오른쪽으로 200px


def test_keyboard(esp: ESP32Controller):
    print("\n=== [5] 키보드 테스트 ===")
    esp.click(400, 600)      # 입력 필드 클릭
    time.sleep(0.3)
    esp.type_text("hello")
    esp.key_tab()
    esp.type_text("world")
    esp.key_enter()


def run_all_tests(esp: ESP32Controller):
    test_basic_movement(esp)
    test_click(esp)
    test_long_press(esp)
    test_swipe(esp)
    test_keyboard(esp)
    print("\n=== 모든 테스트 완료 ===")


if __name__ == "__main__":
    esp = ESP32Controller(port=PORT, baud=BAUD)
    try:
        print("\n=== 스와이프 테스트 ===")
        
        # 1) 아래 -> 위 (네가 원한 '절반 아래에서 절반 위로')
        print("[1] 아래에서 위로 스와이프")
        esp.swipe(200, 100, 200, 400)
        time.sleep(2)
        
        # 2) 위 -> 아래 (반대 방향 확인)
        print("[2] 위에서 아래로 스와이프")
        esp.swipe(200, 400, 200, 100)
        time.sleep(2)
        
    finally:
        esp.close()
