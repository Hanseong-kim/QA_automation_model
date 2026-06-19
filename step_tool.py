"""step_tool.py — Claude Code용 단발 실행 탐색 도구

명령 하나 실행 → OCR 결과 출력 → Claude Code가 다음 동작 판단.
매 실행마다 ESP + 카메라 init/close 자동.

사용법:
  python step_tool.py shot                    # 화면 캡처 + OCR 결과 출력
  python step_tool.py key <KEY>               # 키 전송 (TAB / ENTER / DOWN / UP / LEFT / RIGHT / ESC)
  python step_tool.py type <텍스트>           # 텍스트 입력
  python step_tool.py swipe <x1,y1,x2,y2>    # 스와이프 (BL 원점)
  python step_tool.py keyshot <KEY>           # 키 전송 후 캡처+OCR

주의: IP Webcam 버퍼 딜레이로 실제 화면 반영까지 수 초 소요.
      캡처 파일은 명령 실행 후 5~10초 후에 확인 권장.
"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
from lib.esp import init as init_esp, send, close as close_esp
from lib.vision import init_camera, grab
from lib.qa import read_screen_text
from lib.config import STREAM_URL

SHOT_DIR = os.path.join("captures", "step_tool")
FLUSH    = 15   # 카메라 버퍼 플러시 횟수


# ── 내부 유틸 ────────────────────────────────────────────────────────────

def _normalize_key(key: str) -> str:
    """TAB → KEY:TAB, KEY:ENTER → KEY:ENTER (이미 접두사 있으면 그대로)."""
    key = key.upper()
    return key if key.startswith("KEY:") else f"KEY:{key}"


def _save_shot() -> str:
    """현재 화면을 captures/step_tool/<timestamp>.jpg 로 저장. 경로 반환."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    frame = grab(FLUSH)
    if frame is None:
        print("[shot] 프레임 획득 실패")
        return ""
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    path = os.path.join(SHOT_DIR, f"{ts}.jpg")
    cv2.imwrite(path, rot)
    return path


def _print_ocr(results: list):
    """OCR 결과를 y좌표 오름차순으로 출력."""
    if not results:
        print("  (텍스트 없음 또는 OCR 실패)")
        return
    print(f"  {len(results)}개 텍스트 검출:")
    for text, conf, (cx, cy) in sorted(results, key=lambda x: x[2][1]):
        print(f"    conf={conf:.2f}  center=({cx:4d},{cy:4d})  '{text}'")


def _do_shot() -> int:
    """캡처 + OCR + 출력. 저장 경로도 출력."""
    path = _save_shot()
    results = read_screen_text(flush=FLUSH, roi=None)
    print("\n[OCR 결과]")
    _print_ocr(results)
    if path:
        print(f"\n[캡처 저장] {os.path.abspath(path)}")
        print("※ IP Webcam 딜레이: 명령 실행 후 5~10초 뒤 파일 확인 권장")
    return 0


# ── 명령 핸들러 ──────────────────────────────────────────────────────────

def cmd_shot(args):
    return _do_shot()


def cmd_key(args):
    if not args:
        print("오류: key 명령에 키 이름 필요 (예: TAB, ENTER, DOWN)")
        return 1
    key_cmd = _normalize_key(args[0])
    print(f"[key] 전송: {key_cmd}")
    send(key_cmd, wait=0)
    print("[key] 완료")
    return 0


def cmd_type(args):
    if not args:
        print("오류: type 명령에 텍스트 필요")
        return 1
    text = " ".join(args)
    print(f"[type] 전송: TYPE:{text}")
    send(f"TYPE:{text}", wait=0)
    print("[type] 완료")
    return 0


def cmd_swipe(args):
    if not args:
        print("오류: swipe 명령에 좌표 필요 (예: 200,100,200,500)")
        return 1
    coords = args[0]
    cmd = f"SWIPE:{coords}"
    print(f"[swipe] 전송: {cmd}")
    send(cmd, wait=0)
    print("[swipe] 완료")
    return 0


def cmd_keyshot(args):
    if not args:
        print("오류: keyshot 명령에 키 이름 필요")
        return 1
    key_cmd = _normalize_key(args[0])
    print(f"[keyshot] 키 전송: {key_cmd}")
    send(key_cmd, wait=0)
    print("[keyshot] 키 완료 → 캡처+OCR 시작")
    return _do_shot()


COMMANDS = {
    "shot":    (cmd_shot,    0),
    "key":     (cmd_key,     1),
    "type":    (cmd_type,    1),
    "swipe":   (cmd_swipe,   1),
    "keyshot": (cmd_keyshot, 1),
}


def usage():
    print("사용법:")
    print("  python step_tool.py shot")
    print("  python step_tool.py key <TAB|ENTER|DOWN|UP|LEFT|RIGHT|ESC|...>")
    print("  python step_tool.py type <텍스트>")
    print("  python step_tool.py swipe <x1,y1,x2,y2>")
    print("  python step_tool.py keyshot <KEY>")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        usage()
        sys.exit(1)

    cmd = args[0]
    fn, min_args = COMMANDS[cmd]
    cmd_args = args[1:]

    if len(cmd_args) < min_args:
        print(f"오류: '{cmd}'는 인자 {min_args}개 이상 필요")
        usage()
        sys.exit(1)

    print(f"=== step_tool: {cmd} ===")
    init_esp()
    init_camera(STREAM_URL)

    exit_code = 1
    try:
        exit_code = fn(cmd_args)
    finally:
        close_esp()

    sys.exit(exit_code)
