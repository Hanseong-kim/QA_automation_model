import cv2, easyocr, time, threading
from lib.config import STREAM_URL

_cap = None
_stream_url = None

print("EasyOCR 로딩...")
reader = easyocr.Reader(['en'])


def init_camera(url=STREAM_URL):
    global _cap, _stream_url
    _stream_url = url
    _cap = cv2.VideoCapture(url)
    _cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return _cap


def grab(flush=15):
    for _ in range(flush):
        _cap.grab()
    ret, f = _cap.read()
    return f if ret else None


def fresh_grab():
    global _cap
    _cap.release()
    time.sleep(0.3)
    _cap = cv2.VideoCapture(_stream_url)
    _cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    for _ in range(5):
        _cap.grab()
    ret, f = _cap.read()
    return f if ret else None


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
