"""probe.py — 체크리스트 경로 탐색 도구 (키 + 타이핑 + 화면확인)

명령:
  t            = TAB
  e            = ENTER
  le           = LONGENTER
  u/d/l/r      = 방향키 (UP/DOWN/LEFT/RIGHT)
  s            = 현재 화면 캡처 + OCR (지금 어디인지 확인)
  c [라벨]     = 현재 화면을 jpg로 저장 (예: c battery → cap_battery_<ts>.jpg)
  type <텍스트> = 텍스트 입력 (예: type Screen timeout)
  swipe x1,y1,x2,y2 = 스와이프 (예: swipe 200,100,200,500)
  goto         = 홈에서 Settings 진입 (묶음 동작)
  search <키워드> = Settings 검색 진입 + 키워드 타이핑 (묶음 동작)
  b            = 뒤로가기 (3-button nav Back)
  home         = 홈으로 (3-button nav Home)
  h            = 지금까지 히스토리 출력
  q            = 종료 (히스토리 파일 저장)

사용 예 (Screen timeout 경로 찾기):
  goto                    → Settings 진입
  search Screen timeout   → 검색
  s                       → 화면 확인 (결과 떴나?)
  e                       → ENTER
  s                       → 확인 (들어갔나?)
  ...
"""
import sys, os, time
import cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.esp import init as init_esp, close as close_esp, send
from lib.vision import init_camera, grab, grab_fresh, reconnect
from lib.config import STREAM_URL
from lib.qa import read_screen_text, open_settings, settings_search, SEARCH_CLEAR_CLICK

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures", "probe")

NAV_BACK = "CLICK:80,20"
NAV_HOME = "CLICK:120,20"

KEY_CMD = {
    't':  "KEY:TAB",
    'e':  "KEY:ENTER",
    'le': "LONGENTER",
    'u':  "KEY:UP",
    'd':  "KEY:DOWN",
    'l':  "KEY:LEFT",
    'r':  "KEY:RIGHT",
}

history = []


def capture_screen(label=""):
    """재연결 후 화면을 grab → 90° CW 회전 → jpg 저장. 절대경로 반환."""
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    ts = int(time.time())
    name = f"cap_{label}_{ts}.jpg" if label else f"cap_{ts}.jpg"
    path = os.path.join(CAPTURE_DIR, name)
    print("  [재연결 중...]")
    frame = grab_fresh()
    if frame is None:
        print("  (프레임 획득 실패)")
        return None
    rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    cv2.imwrite(path, rotated)
    print(f"  저장됨: {os.path.abspath(path)}")
    return path


def show_screen():
    """재연결 후 화면 OCR 결과를 y좌표 순으로 출력."""
    print("  [재연결 + 화면 읽는 중...]")
    reconnect()
    results = read_screen_text(flush=3, roi=None)
    if not results:
        print("  (텍스트 없음 / 프레임 실패)")
        return
    for text, conf, (cx, cy) in sorted(results, key=lambda x: x[2][1]):
        print(f"    conf={conf:.2f}  ({cx:4d},{cy:4d})  '{text}'")


def main():
    # 카메라 사용 여부: 기본 OFF. 'cam' 인자 주면 ON.
    use_cam = "cam" in sys.argv[1:]

    init_esp()
    if use_cam:
        init_camera(STREAM_URL)
        print("\n연결됨. (카메라 ON)")
    else:
        print("\n연결됨. (카메라 OFF — s/goto/search 화면확인은 카메라 필요)")
        print("  카메라 쓰려면: python probe.py cam")
    print("명령: t/e/le/u/d/l/r=키, b=뒤로가기, home=홈으로, s=화면확인, c [라벨]=jpg저장,")
    print("      m x y=MOVE, c x y=CLICK(숫자2개), remove=검색어 지우기(X버튼),")
    print("      type <텍스트>, swipe x1,y1,x2,y2, goto=Settings진입, search <키워드>, h=히스토리, q=종료\n")

    try:
        while True:
            raw = input("> ").strip()
            if not raw:
                continue
            if raw == 'q':
                break

            # 히스토리 출력
            if raw == 'h':
                print("  히스토리:", " → ".join(history) if history else "(없음)")
                continue

            # remove: 검색창 X(지우기) 버튼 클릭 (qa between의 remove 단계)
            if raw == 'remove':
                print(f"  [remove] {SEARCH_CLEAR_CLICK} (검색어 지움)")
                send(SEARCH_CLEAR_CLICK, wait=0)
                history.append("[remove]")
                continue

            # 절대좌표 MOVE/CLICK (calibrate.py m/c 포팅) — 좌표 탐색용 (예: remove 버튼 찾기)
            # 'c x y'(숫자 2개)는 클릭, 'c'/'c <라벨>'은 아래 화면캡처로 분기
            _p = raw.split()
            if (len(_p) == 3 and _p[0] in ('m', 'c')
                    and _p[1].lstrip('-').isdigit() and _p[2].lstrip('-').isdigit()):
                x, y = _p[1], _p[2]
                op = "MOVE" if _p[0] == 'm' else "CLICK"
                print(f"  [{_p[0]}] {op}:{x},{y}")
                send(f"{op}:{x},{y}", wait=0)
                history.append(f"{op}:{x},{y}")
                continue

            # 화면 확인 (카메라 필요)
            if raw == 's':
                if not use_cam:
                    print("  ⚠ 카메라 OFF. 화면확인하려면 python probe.py cam 으로 재실행.")
                    continue
                show_screen()
                history.append("[shot]")
                continue

            # jpg 캡처 저장 (카메라 필요)
            if raw == 'c' or raw.startswith('c '):
                if not use_cam:
                    print("  ⚠ 카메라 OFF. 캡처하려면 python probe.py cam 으로 재실행.")
                    continue
                label = raw[2:].strip() if raw.startswith('c ') else ""
                path = capture_screen(label)
                if path:
                    history.append(f"[cap:{os.path.basename(path)}]")
                continue

            # 네비게이션 버튼 (카메라 무관)
            if raw == 'b':
                print(f"  [back] {NAV_BACK}")
                send(NAV_BACK, wait=0)
                history.append("[back]")
                continue

            if raw == 'home':
                print(f"  [home] {NAV_HOME}")
                send(NAV_HOME, wait=0)
                history.append("[home]")
                continue

            # 묶음 동작: 홈 → Settings (진입확인은 카메라 필요)
            if raw == 'goto':
                if not use_cam:
                    print("  ⚠ 카메라 OFF: 키 시퀀스는 보내지만 진입 확인(OCR)은 못 함.")
                print("  [goto] 홈 → Settings 진입...")
                ok = open_settings()
                print(f"  [goto] {'성공' if ok else '미확인/실패'}")
                history.append("[goto_settings]")
                continue

            # 묶음 동작: 검색 (결과확인은 카메라 필요)
            if raw.startswith('search '):
                kw = raw[len('search '):].strip()
                if not use_cam:
                    print("  ⚠ 카메라 OFF: 검색 타이핑은 하지만 결과 확인(OCR)은 못 함.")
                print(f"  [search] '{kw}' 검색...")
                ok = settings_search(kw)
                print(f"  [search] {'결과 확인됨' if ok else '결과 미확인'}")
                history.append(f"[search:{kw}]")
                continue

            # 타이핑 (명령어와 충돌 방지: 명시적 'type ' 접두사)
            if raw.startswith('type '):
                text = raw[len('type '):]
                print(f"  [type] '{text}'")
                send(f"TYPE:{text}", wait=0)
                history.append(f"TYPE:{text}")
                continue

            # 스와이프
            if raw.startswith('swipe '):
                args = raw[len('swipe '):].strip()
                print(f"  [swipe] {args}")
                send(f"SWIPE:{args}", wait=0)
                history.append(f"SWIPE:{args}")
                continue

            # 단일 키 명령
            if raw in KEY_CMD:
                cmd = KEY_CMD[raw]
                print(f"  [key] {cmd}")
                send(cmd, wait=0)
                history.append(cmd)
                continue

            # 위에 안 걸리면 안내 (실수로 명령 친 경우 타이핑 방지)
            print(f"  ⚠ 알 수 없는 명령: '{raw}'")
            print("    타이핑하려면 'type {텍스트}' 형식으로. 키는 t/e/le/u/d/l/r.")

    finally:
        close_esp()
        if history:
            fn = f"probe_{int(time.time())}.txt"
            with open(fn, "w", encoding="utf-8") as f:
                f.write(" → ".join(history))
            print(f"\n저장됨: {fn}")
        print("종료")


if __name__ == "__main__":
    main()