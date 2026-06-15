import requests

# [수정] /video가 없는 기본 서버 주소(베이스 URL)를 정의합니다.
BASE_URL = "http://192.168.1.205:8080"
# 만약 나중에 cv2.VideoCapture 등에서 스트리밍 주소가 필요하다면 아래 변수를 사용하세요.
# STREAM_URL = f"{BASE_URL}/video"

def cam(path, **params):
    # [수정] 요청 주소를 BASE_URL 기준으로 조합하여 /video가 중간에 끼지 않도록 합니다.
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=5)
    r.raise_for_status()
    return r.text

def lock_focus():
    """한 번 오토포커스 → 고정. 캘리브레이션 시작 전에 1회만 호출."""
    cam("/settings/focusmode", set="auto")  # 이제 정상적으로 http://192.168.1.205:8080/settings/focusmode 로 요청이 갑니다.
    cam("/focus")                             # 1회 초점 트리거
    import time; time.sleep(1.5)              # 렌즈가 자리 잡을 시간
    print("focus locked")

# 사용 예
lock_focus()
# ... 이후 캡처/OCR 진행 (초점 안 건드림) ...