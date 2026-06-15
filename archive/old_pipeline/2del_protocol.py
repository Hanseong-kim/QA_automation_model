"""
delete_protocol.py - 포커스 잠금 + Radius 제외 앱 삭제 (비전 기반, 라이브 스트림)

흐름:
  0. IP Webcam 포커스 1회 잠금 (HTTP)
  1. 라이브 스트림에서 여러 프레임 누적 OCR -> 슬롯별 앱 판별
  2. Radius인 슬롯만 건너뛰고 나머지 앱별 (dx,dy)로 Remove 클릭

핵심:
  - 라이브 스트림 유지 (WiFi 목록 등 실시간 갱신 화면 대응)
  - 백그라운드 스레드가 항상 '최신 완전 프레임' 보관 (버퍼 적체/깨짐 방어)
  - 프레임마다 한 라벨씩 들쭉날쭉 빠지는 문제 -> 여러 프레임 누적(union),
    4개(=슬롯 수) 다 모일 때까지 더 읽음

슬롯 (왼쪽->오른쪽, ESP 롱프레스 좌표):
  슬롯0: 40,320   슬롯1: 70,315   슬롯2: 100,310   슬롯3: 130,310

실행: python delete_protocol.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2, numpy as np, re, requests, time
from difflib import SequenceMatcher
from lib.config import COM_PORT, BASE_URL, STREAM_URL, OCR_CONF
from lib.esp import init, send, close
from lib.vision import StreamGrabber, reader

FUZZY = 0.72                               # 앱이름 퍼지매칭 임계값

# 슬롯 ESP 롱프레스 좌표 (왼쪽->오른쪽 순서)
SLOTS = [(40,320), (70,315), (100,310), (130,310)]

# 앱별 Remove 상대이동 (dx, dy)
REMOVE_REL = {
    "Radius":      (40, -30),
    "Knox Remote": (40, -30),
    "Files":       (40,  30),
    "Chrome":      (52,  30),
}

SKIP = "Radius"   # 삭제 안 할 앱

APP_KEYWORDS = {"radius":"Radius", "knox":"Knox Remote", "files":"Files", "chrome":"Chrome"}
BG_TOUCH = (500, 500)

init()
print("연결됨")

grabber = StreamGrabber(STREAM_URL)
time.sleep(1.0)   # 스레드가 첫 프레임 채울 시간

def cleanup():
    grabber.release()
    close()

# ───────── 포커스 (IP Webcam HTTP API) ─────────
def cam(path, **params):
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=5)
    r.raise_for_status()
    return r.text

def lock_focus():
    try:
        cam("/settings/focusmode", set="auto")
        cam("/focus")
        time.sleep(1.5)
        print("focus locked")
        return True
    except Exception as e:
        print(f"[경고] 포커스 제어 실패: {e}  (현재 초점 상태로 진행)")
        return False

def match_app(text):
    t = text.lower().strip()
    words = re.split(r'[\s\-_,./]+', t)
    for kw, name in APP_KEYWORDS.items():
        if kw in words or kw in t: return name
        for w in words:
            if len(w) >= 4 and SequenceMatcher(None, w, kw).ratio() >= FUZZY: return name
    return None

def ocr_one_frame():
    """한 프레임 OCR -> [(name, cx, cy, conf), ...] (한 줄만 필터링)."""
    frame = grabber.read()
    if frame is None: return []
    rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    raw = []
    for (bbox, text, conf) in reader.readtext(rot):
        if conf <= OCR_CONF: continue
        name = match_app(text)
        if name is None: continue
        cx = int((bbox[0][0]+bbox[2][0])/2)
        cy = int((bbox[0][1]+bbox[2][1])/2)
        raw.append((name, cx, cy, conf))
    if not raw: return []
    ys = sorted([r[2] for r in raw]); med = ys[len(ys)//2]
    return [r for r in raw if abs(r[2]-med) <= 120]

def detect_apps(max_frames=8):
    """여러 프레임을 누적해서 앱을 모음. 슬롯 수만큼 다 모이면 조기 종료.
       앱당 conf 최고값 유지 -> 위치(cx)도 가장 신뢰도 높은 인식 기준."""
    want = len(SLOTS)
    acc = {}   # name -> (cx, cy, conf)
    for attempt in range(max_frames):
        for (name, cx, cy, conf) in ocr_one_frame():
            if name not in acc or conf > acc[name][2]:
                acc[name] = (cx, cy, conf)
        print(f"  프레임 {attempt+1}: 누적 {sorted(acc.keys())}")
        if len(acc) >= want:
            break
        time.sleep(0.25)
    if not acc: return []
    apps = sorted(acc.items(), key=lambda kv: kv[1][0])   # cx = 왼쪽->오른쪽
    return [name for name, v in apps]

def delete_app_at_slot(slot_idx, app_name):
    lp = SLOTS[slot_idx]
    dx, dy = REMOVE_REL[app_name]
    print(f"\n=== 슬롯{slot_idx}({app_name}) 삭제 ===")
    print(f"[1] 롱프레스 {lp}")
    send(f"LONGPRESS:{lp[0]},{lp[1]}", wait=1.5)
    print(f"[2] Remove로 이동 ({dx},{dy})")
    send(f"MOVEREL:{dx},{dy}", wait=0.5)
    print(f"[3] Remove 클릭")
    send("CLICKREL:0,0", wait=2)
    print(f"[4] 배경 터치")
    send(f"CLICK:{BG_TOUCH[0]},{BG_TOUCH[1]}", wait=1.5)

def main():
    print("\n=== 포커스 잠금 ===")
    lock_focus()

    print("\n=== 앱 감지 ===")
    apps = detect_apps()
    if not apps:
        print("앱 감지 실패"); cleanup(); return

    print(f"감지된 앱 (슬롯 순서): {apps}")
    if len(apps) != len(SLOTS):
        print(f"[경고] 감지 {len(apps)}개 != 슬롯 {len(SLOTS)}개. 매칭 어긋날 수 있음.")
        ans = input("계속? (y/n) > ").strip().lower()
        if ans != 'y': cleanup(); return

    print("\n=== 삭제 계획 ===")
    for i, name in enumerate(apps):
        action = "건너뜀(보존)" if name == SKIP else "삭제"
        print(f"  슬롯{i}: {name} -> {action}")
    ans = input("\n실행? (y/n) > ").strip().lower()
    if ans != 'y': cleanup(); return

    for i, name in enumerate(apps):
        if name == SKIP:
            print(f"\n슬롯{i} {name}: 건너뜀")
            continue
        delete_app_at_slot(i, name)

    print("\n=== 완료 ===")
    cleanup()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨, 정리 중...")
        cleanup()
