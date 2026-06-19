import cv2, time, threading
# import easyocr                       # rollback: uncomment this line
from rapidocr_onnxruntime import RapidOCR
from lib.config import STREAM_URL

_cap = None
_stream_url = None

print("RapidOCR 로딩...")
reader = RapidOCR()
# reader = easyocr.Reader(['en'])      # rollback: uncomment, comment RapidOCR line


def ocr_readtext(img):
    """OCR 결과를 [(bbox, text, conf), ...] 형태로 정규화.

    롤백 시 이 함수만 교체:
        return reader.readtext(img)    # EasyOCR 버전
    """
    results, _ = reader(img)
    if results is None:
        return []
    return [(item[0], item[1], float(item[2])) for item in results]


_CAM_RETRIES   = 3    # 연결 실패 시 최대 재시도 횟수
_CAM_RETRY_SEC = 1.0  # 재시도 간격 (초)


def init_camera(url=STREAM_URL):
    """카메라 스트림에 연결한다. 실패 시 최대 _CAM_RETRIES회 재시도."""
    global _cap, _stream_url
    _stream_url = url
    for attempt in range(1, _CAM_RETRIES + 1):
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, _ = cap.read()
        if ret:
            _cap = cap
            print(f"  [카메라] 연결 성공 (시도 {attempt}/{_CAM_RETRIES})")
            return _cap
        cap.release()
        print(f"  [카메라] 연결 실패 (시도 {attempt}/{_CAM_RETRIES}) — {_CAM_RETRY_SEC}초 후 재시도")
        time.sleep(_CAM_RETRY_SEC)
    raise RuntimeError(f"카메라 연결 실패: {_CAM_RETRIES}회 시도 후에도 프레임을 읽지 못했습니다. URL={url}")


def _grab_inner(flush):
    """cap.read()로 flush회 디코드·버림 → 마지막으로 성공한 프레임 반환."""
    if _cap is None:
        return None
    frame = None
    for _ in range(flush):
        ret, f = _cap.read()
        if ret and f is not None:
            frame = f
    return frame


def reconnect():
    """스트림 재연결. 성공 True, 실패 False."""
    global _cap
    if _cap is not None:
        _cap.release()
        _cap = None
    time.sleep(0.5)
    try:
        init_camera(_stream_url)
        return True
    except RuntimeError as e:
        print(f"  [재연결 실패] {e}")
        print("  → IP Webcam 스트리밍 상태를 확인하세요.")
        return False


def grab(flush=15):
    frame = _grab_inner(flush)
    if frame is not None:
        return frame
    print("  [grab] 프레임 획득 실패 → 재연결 시도...")
    if not reconnect():
        return None
    return _grab_inner(flush)


def fresh_grab():
    """재연결 후 프레임 반환 (하위 호환)."""
    reconnect()
    return _grab_inner(5)


def grab_fresh():
    """reconnect 후 첫 프레임 반환 — one-shot 캡처 전용.
    FFMPEG 버퍼를 완전히 우회하는 유일한 확실한 방법."""
    if not reconnect():
        return None
    return _grab_inner(3)


def release_camera():
    global _cap
    if _cap:
        _cap.release()
        _cap = None


class StreamGrabber:
    """백그라운드 스레드로 스트림을 계속 읽으며 '가장 최신 완전 프레임'만 보관."""
    def __init__(self, url):
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ret, f = self.cap.read()
            if ret and f is not None and f.size > 0:
                with self.lock:
                    self.frame = f
            else:
                time.sleep(0.005)

    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def release(self):
        self.running = False
        time.sleep(0.05)
        self.cap.release()
