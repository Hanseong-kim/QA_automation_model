"""
coord_mapper.py
태블릿 화면 픽셀좌표 -> ESP32 좌표 변환기.

카메라 없이, "ESP 좌표를 보내 커서를 화면의 아는 지점에 맞추고 저장"하는 방식으로
점 쌍을 모은다. 3쌍 이상 모이면 affine 변환을 학습하고, 검증 모드로 정확도를 확인한다.

전제(테스트로 확인할 것):
  1) MOVE:x,y 재현성 - 같은 값 보내면 매번 같은 픽셀로 가야 함
  2) 포인터 가속 - 켜져 있으면 affine 오차가 커질 수 있음 (report에서 확인)

실행: python coord_mapper.py
"""

import json
import time

import numpy as np

try:
    import serial
except ImportError:
    serial = None  # 시리얼 없이 클래스 테스트만 할 때 대비


# ============================================================
# 설정 - 본인 환경에 맞게 수정
# ============================================================
COM_PORT = "COM7"
BAUD = 115200
SAVE_PATH = "C:/hansung/project/radius-auto/mapper.json"


# ============================================================
# 변환기
# ============================================================
class CoordinateMapper:
    """태블릿 픽셀 (px, py) -> ESP (ex, ey) affine 변환."""

    def __init__(self):
        self.pairs = []   # [((px, py), (ex, ey)), ...]
        self.A = None     # 2x3 affine 행렬
        self.offset = (0, 0)  # 픽셀 보정 (검증으로 찾은 계통 오차 상쇄용)

    def add_pair(self, pixel, esp):
        self.pairs.append((tuple(pixel), tuple(esp)))

    def fit(self):
        if len(self.pairs) < 3:
            raise ValueError(f"최소 3쌍 필요 (현재 {len(self.pairs)}쌍)")
        P = np.array([[px, py, 1.0] for (px, py), _ in self.pairs])
        E = np.array([list(e) for _, e in self.pairs], dtype=float)
        X, *_ = np.linalg.lstsq(P, E, rcond=None)   # P @ X = E
        self.A = X.T                                 # 2x3
        return self.A

    def pixel_to_esp(self, px, py):
        if self.A is None:
            raise RuntimeError("fit()를 먼저 호출하세요")
        px += self.offset[0]   # 계통 오차 보정
        py += self.offset[1]
        v = self.A @ np.array([px, py, 1.0])
        return int(round(v[0])), int(round(v[1]))

    def residuals(self):
        """각 점의 변환 오차(ESP 단위). offset 제외한 순수 affine 품질."""
        errs = []
        for (px, py), (ex, ey) in self.pairs:
            v = self.A @ np.array([px, py, 1.0])
            qx, qy = int(round(v[0])), int(round(v[1]))
            errs.append(((qx - ex) ** 2 + (qy - ey) ** 2) ** 0.5)
        return errs

    def report(self):
        e = self.residuals()
        mean, mx = np.mean(e), np.max(e)
        print(f"\n[품질] 점 {len(e)}개 | 평균오차 {mean:.1f} | 최대 {mx:.1f} (ESP 단위)")
        # 점별 오차 (큰 순으로) - 범인 점 찾기용
        order = sorted(range(len(e)), key=lambda i: e[i], reverse=True)
        print("  점별 오차(큰 순):")
        for i in order:
            (px, py), (ex, ey) = self.pairs[i]
            mark = "  <-- 의심" if e[i] > mean * 1.8 else ""
            print(f"    #{i}: 픽셀{(px,py)} <-> ESP{(ex,ey)} | 오차 {e[i]:.1f}{mark}")
        if mean < 15:
            print("  -> 양호. affine으로 충분.")
        elif mean < 40:
            print("  -> 보통. '의심' 점을 delete로 지우고 다시 찍으면 개선됨.")
        else:
            print("  -> 큼. 포인터 가속이거나 MOVE 재현성, 또는 특정 점 오입력.")
            print("     (가속이 원인이면 선형 매핑으론 한계 -> 다음 단계에서 보정 논의)")
        return mean

    def save(self, path):
        json.dump(
            {"pairs": self.pairs,
             "A": (self.A.tolist() if self.A is not None else None),
             "offset": list(self.offset)},
            open(path, "w"),
        )
        print(f"[저장] {path}  (offset={self.offset})")

    def load(self, path):
        d = json.load(open(path))
        self.pairs = [tuple(map(tuple, p)) for p in d["pairs"]]
        self.A = np.array(d["A"]) if d["A"] is not None else None
        self.offset = tuple(d.get("offset", (0, 0)))
        return self


# ============================================================
# ESP 시리얼 제어
# ============================================================
class ESP:
    def __init__(self, port, baud):
        if serial is None:
            raise RuntimeError("pyserial 미설치: pip install pyserial")
        self.ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)  # ESP 리셋 대기

    def move(self, x, y, settle=0.4):
        # 펌웨어 프로토콜에 맞게 이 한 줄만 고치면 됨
        self.ser.write(f"MOVE:{x},{y}\n".encode())
        time.sleep(settle)

    def close(self):
        self.ser.close()


# ============================================================
# 1) 점 쌍 수집
# ============================================================
def collect(mapper, esp):
    """
    ESP 좌표를 보내 커서를 '픽셀좌표를 아는 지점'에 맞추고 그 쌍을 저장.

    추천 지점: 화면 네 모서리 근처 + 중앙 (화면을 넓게 덮을수록 정확).
    예) 1920x1200 화면이면 (100,100) (1820,100) (100,1100) (1820,1100) (960,600)
    """
    print("\n=== 점 수집 ===")
    print("  x,y          : 그 ESP 좌표로 커서 이동")
    print("  s px,py      : 지금 커서가 닿은 화면 픽셀좌표로 쌍 저장")
    print("  del N        : N번 점 삭제 (list로 번호 확인)")
    print("  reset        : 모든 점 삭제")
    print("  list / q     : 목록 / 종료\n")

    last = None
    while True:
        cmd = input(f"[{len(mapper.pairs)}쌍] > ").strip()
        if cmd == "q":
            break
        if cmd == "list":
            for i, (px, e) in enumerate(mapper.pairs):
                print(f"  {i}: 픽셀{px} <-> ESP{e}")
            continue
        if cmd == "reset":
            mapper.pairs.clear()
            mapper.A = None
            print("  모든 점 삭제됨")
            continue
        if cmd.startswith("del "):
            try:
                idx = int(cmd[4:].strip())
                removed = mapper.pairs.pop(idx)
                mapper.A = None
                print(f"  삭제: #{idx} {removed}")
            except (ValueError, IndexError):
                print("  형식: del N  (list로 번호 확인)")
            continue
        if cmd.startswith("s "):
            if last is None:
                print("  먼저 x,y 로 커서를 이동시키세요")
                continue
            try:
                px, py = map(int, cmd[2:].split(","))
            except ValueError:
                print("  형식: s 픽셀x,픽셀y  (예: s 180,650)")
                continue
            mapper.add_pair((px, py), last)
            print(f"  저장: 픽셀({px},{py}) <-> ESP{last}")
            continue
        # 그 외 -> ESP 이동
        try:
            ex, ey = map(int, cmd.split(","))
        except ValueError:
            print("  형식: ESPx,ESPy  /  s 픽셀x,픽셀y  /  list  /  q")
            continue
        esp.move(ex, ey)
        last = (ex, ey)
        print(f"  ESP({ex},{ey}) 이동 -> 커서가 목표 픽셀에 정확히 닿았는지 눈으로 확인")


# ============================================================
# 2) 검증 (테스트하면서 정확도 확인)
# ============================================================
def verify(mapper, esp):
    """
    '닿게 하고 싶은 화면 픽셀'을 입력하면 -> ESP 좌표로 변환해 실제로 이동.
    커서가 그 픽셀에 실제로 닿는지 눈으로 확인 = affine 매핑의 실전 검증.
    """
    if mapper.A is None:
        print("먼저 fit 필요"); return
    print("\n=== 검증 ===  닿게 할 화면 픽셀 'px,py' 입력 (q=종료)")
    while True:
        cmd = input("픽셀 > ").strip()
        if cmd == "q":
            break
        try:
            px, py = map(int, cmd.split(","))
        except ValueError:
            print("  형식: px,py"); continue
        ex, ey = mapper.pixel_to_esp(px, py)
        print(f"  픽셀({px},{py}) -> ESP({ex},{ey}) 이동")
        esp.move(ex, ey)


# ============================================================
# 메인
# ============================================================
def main():
    mapper = CoordinateMapper()
    mapper.offset = (100, -100)   # 검증으로 찾은 계통 오차 보정 (메뉴 6에서 변경 가능)
    esp = ESP(COM_PORT, BAUD)
    try:
        while True:
            print(f"\n[메뉴] 1)수집  2)학습+품질  3)검증  4)저장  5)불러오기  6)offset({mapper.offset})  q)종료")
            sel = input("선택 > ").strip()
            if sel == "1":
                collect(mapper, esp)
            elif sel == "2":
                if len(mapper.pairs) < 3:
                    print("점이 3쌍 미만"); continue
                mapper.fit()
                mapper.report()
            elif sel == "3":
                verify(mapper, esp)
            elif sel == "4":
                mapper.save(SAVE_PATH)
            elif sel == "5":
                mapper.load(SAVE_PATH)
                print(f"불러옴: {len(mapper.pairs)}쌍, A={'있음' if mapper.A is not None else '없음'}, offset={mapper.offset}")
            elif sel == "6":
                try:
                    ox, oy = map(int, input("offset x,y > ").strip().split(","))
                    mapper.offset = (ox, oy)
                    print(f"offset = {mapper.offset}")
                except ValueError:
                    print("형식: x,y")
            elif sel == "q":
                break
    finally:
        esp.close()
        print("시리얼 닫음.")


if __name__ == "__main__":
    main()