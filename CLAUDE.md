# CLAUDE.md — Alldocube Tablet QA Configuration Automation

## Project Overview

Automated pipeline for pre-shipment tablet configuration QA. A PC controls a Knox-restricted Android tablet **without touching it**: an ESP32-S3 acts as a USB HID mouse/keyboard, and an IP Webcam stream + OCR provides visual feedback for closed-loop verification.

**Why this architecture:** Knox blocks ADB, absolute HID positioning, and digitizer modes. The only available channel is physical-equivalent input (relative HID mouse + HID keyboard) and visual observation of the screen.

```
PC (Python)
 ├─ Serial COM7 ──→ ESP32-S3 ──→ USB HID ──→ Tablet (mouse/keyboard input)
 └─ HTTP http://192.168.1.205:8080/video ←── IP Webcam (tablet screen stream)
                └─ EasyOCR / OpenCV → decide next action
```

## Hardware & Environment

- **ESP32**: ESP32-S3, firmware in `main.cpp` (Arduino, USBHIDMouse + USBHIDKeyboard)
- **Serial**: `COM7`, 115200 baud. Every command is newline-terminated; ESP32 replies `DONE`.
- **Camera**: phone running IP Webcam at `http://192.168.1.205:8080/video`. Frames must be flushed (~12 grabs) before reading to avoid stale buffer. Frame is rotated 90° CW before OCR (`cv2.ROTATE_90_CLOCKWISE`).
- **OCR**: EasyOCR `['en']`, confidence threshold 0.4, fuzzy matching via `SequenceMatcher` (ratio ≥ 0.8 on words ≥ 4 chars).
- **Python deps**: `pyserial`, `opencv-python`, `easyocr`, `numpy`.

## Coordinate System (CRITICAL)

The HID mouse is **relative only**. Absolute positioning is emulated by ramming the cursor into a screen corner (guaranteed position) and then moving a known offset:

| Command | Origin corner | Y direction |
|---|---|---|
| `MOVE:` / `CLICK:` / `LONGPRESS:` / `SWIPE:` | bottom-left | +y goes UP from bottom |
| `MOVETL:` / `CLICKTL:` / `LONGPRESSTL:` | top-left | +y goes DOWN |
| `MOVEBR:` / `LONGPRESSBR:` | bottom-right | +x goes LEFT, +y goes UP |
| `*REL:` variants | current position | screen-natural (+y down) |

- Movement is chunked (`STEP_SIZE 20`, `STEP_DELAY_US 800`) to defeat OS pointer acceleration. **Never bypass smoothMove/dragMove chunking** — large single deltas trigger acceleration and ruin repeatability.
- Drag/swipe uses slower stepping (`SWIPE_STEP 15`, `SWIPE_DELAY_MS 8`) so the OS registers it as a touch-drag.

## ESP32 Firmware Command Reference

```
MOVE:x,y          CLICK:x,y         LONGPRESS:x,y        (bottom-left origin)
MOVETL:x,y        CLICKTL:x,y       LONGPRESSTL:x,y      (top-left origin)
MOVEBR:x,y        LONGPRESSBR:x,y                        (bottom-right origin)
MOVEREL:dx,dy     CLICKREL:dx,dy    LONGPRESSREL:dx,dy   (relative)
SWIPE:x1,y1,x2,y2 (absolute, BL origin)   SWIPEREL:dx,dy (from current pos)
TYPE:text         KEY:TAB    KEY:ENTER    KEY:ESC
```

**Planned/encouraged additions** (add to firmware when needed):
```
KEY:UP  KEY:DOWN  KEY:LEFT  KEY:RIGHT    (D-pad focus navigation)
LONGENTER                                 (1.5s Enter hold = long-click on focused element)
```

## Navigation Strategy (priority order)

1. **Keyboard navigation first** (Tab / arrow keys / Enter / Esc). Deterministic, zero coordinates, immune to camera calibration drift. Settings screens are list UIs — arrow keys + Enter work reliably.
2. **Settings search**: after opening Settings, type into the search bar to jump directly to a setting instead of walking menu trees.
3. **OCR-guided mouse click** when keyboard focus is unavailable (e.g., custom UI elements that don't take focus).
4. **Hardcoded coordinates only as last resort**, and always behind a named constant with a comment describing what it points at.
5. Home-screen long-press context menus: keyboard `LONGENTER` on a focused icon if launcher supports D-pad focus; otherwise mouse `LONGPRESS`.

## Closed-Loop Verification Pattern (REQUIRED for every step)

Never fire-and-forget with fixed sleeps. After every action, verify the expected screen state via OCR before proceeding:

```python
def wait_for_text(keyword, timeout=8, flush=12):
    """Poll camera until `keyword` appears on screen. Returns True/False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = grab(flush)
        rot = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        for (_, text, conf) in reader.readtext(rot):
            if conf > OCR_CONF and matches(text, keyword):
                return True
    return False
```

- On verification failure: retry the action once, then **abort with a clear log line** identifying the step. Never continue past a failed verification — downstream coordinates/focus assumptions will be wrong.
- Toggle verification: read the toggle's ON/OFF state via OCR or pixel color *before* acting. A toggle step must be idempotent — if it's already in the desired state, skip the click.

## Existing Pipeline (execution order)

| Stage | Script | Status |
|---|---|---|
| 1 | `1remove_app.py` — delete Settings/Play Store shortcuts (hardcoded coords) | working |
| 2 | `2del_protocol.py` — OCR slot detection, delete all apps except Radius | working |
| 3 | `setting2radius.py` — Settings → Wi-Fi → connect to Radius SSID (uses `ymap.json` interpolation) | working; prepend `SWIPE:200,100,200,400` at start |
| 4 | `login.py` — Radius app login (email/password/PIN) | hardcoded coords; migrate to Tab/Enter |
| 5 | **QA configuration steps (this document, below)** | to build |

Utility scripts: `calibrate.py`, `measure_rel.py`, `test_esp32.py` (Python wrappers for all ESP32 commands), `ocr_check.py`, `detect_app.py`.

## QA Configuration Checklist (Stage 5 — to automate)

Each task lists: navigation path, action, and OCR verification target. Implement each as an idempotent function `step_NN_name()` returning True/False, logged to a per-device result report.

### A. System settings (all reachable via Settings app)

1. **Enable 3-button navigation**
   - Path: Settings → Accessibility → System Controls → Navigation mode
   - Action: select "3-button navigation"
   - Verify: radio/selection state on "3-button navigation"; also the nav bar appears at screen bottom (template match)

2. **Display battery percentage**
   - Path: Settings → Battery
   - Action: toggle "Show battery percentage" → ON
   - Verify: toggle state; status bar shows `%` digits

3. **Screen timeout = 5 minutes**
   - Path: Settings → Display → Screen timeout
   - Action: select "5 minutes"
   - Verify: OCR "5 minutes" marked selected / shown as current value

4. **Real-time network speed = OFF**
   - Path: Settings → Display → Real-time network speed
   - Action: toggle OFF
   - Verify: toggle state

5. **Double click to turn off screen = OFF**
   - Path: Settings → Display → Double click to turn off the screen
   - Action: toggle OFF
   - Verify: toggle state

6. **Lock screen clock size = Small**
   - Path: Settings → Wallpaper → Wallpaper & style → Clock color and size → Size
   - Action: set to "Small"
   - Verify: "Small" selected state

7. **Notification bubbles = OFF**
   - Path: Settings → Notifications → Bubbles
   - Action: toggle OFF
   - Verify: toggle state

8. **Enhanced notifications = OFF, Notification dot on app icon = OFF**
   - Path: Settings → Notifications → Enhanced notification / Notification dot on app
   - Action: toggle both OFF
   - Verify: both toggle states

### B. Keyboard layout (separate flow — opens from an active text field)

9. **Set keyboard to PC layout**
   - Default state: split layout. Desired: single-piece PC layout.
   - Path: open any text field to summon keyboard → top-left 4-squares icon → gear icon → Languages → tap "Qwerty" keyboard entry on the right
   - Action: **select PC, deselect QWERTY**
   - Verify: checkbox states (PC checked, QWERTY unchecked); reopen keyboard and template-match non-split layout
   - Note: requires a text field first — use the Settings search bar as the host text field.

### C. Home screen / launcher settings

10. **Launcher settings**
    - Path: Home → long-press empty space → "Settings" (bottom right)
    - Actions: "Show Google App" → OFF; "Show Recent Applications" → OFF
    - Verify: both toggle states
    - Note: long-press on *empty space* — use mouse `LONGPRESS` at a known-empty region (e.g., screen center after app removal stages).

11. **Move Radius app icon to home screen, positioned under the "U" and "I" of the wallpaper**
    - Action: long-press Radius icon → drag (press-hold + `dragMove`) to target region → release
    - Verify: OCR finds "Radius" label within expected bounding region of the frame
    - Note: target is defined visually by wallpaper letters — locate "U"/"I" via OCR/template match on the wallpaper first, then compute target coords. This is the most calibration-sensitive step; verify after drop and retry once.

### D. App first-run prompts

12. **Chrome prompts**
    - Action: open Chrome → tap "Use without signing in" (if shown)
    - Verify: prompt no longer on screen; Chrome main UI visible
    - Conditional: if the prompt text isn't found within timeout, treat as already-confirmed and pass.

13. **Knox Remote Support prompts**
    - Action: open Knox Remote Support → click "Allow"/"Allow all" for every permission prompt in sequence
    - Verify: loop — while any "Allow" text is on screen, click it; finish when none remain (with max-iteration guard)

### E. Verification-only checks (no input, OCR/visual only)

14. **Serial number match**
    - Read S/N from Settings → About tablet (OCR), compare against barcode value
    - Barcode on the tablet back/box is **not visible to the screen camera** — input source needed: operator scan (keyboard-wedge barcode scanner into PC) or manual entry. Pipeline should prompt for it and log PASS/FAIL.

15. **Android 16 on device**
    - Path: Settings → About tablet → Android version
    - Verify: OCR "16"

16. **Firmware version is latest** (must include serial-mismatch fix + wallpaper fix)
    - Path: Settings → About tablet → Build/firmware version
    - Verify: OCR version string == expected constant `EXPECTED_FIRMWARE` (keep in config, update per release)

## Output / Reporting

- Every run produces `qa_report_<serial>_<timestamp>.json`: per-step `{step, status: PASS/FAIL/SKIP, detail, screenshot_path}`.
- Save a camera frame on every FAIL for post-mortem.
- Exit non-zero if any step FAILs so the pipeline can halt the device.

## Code Conventions

- One file per stage, numbered (`1remove_app.py` … `5qa_config.py`); shared helpers in a module (serial `send()`, `grab()`, `wait_for_text()`, toggle helpers) — stop copy-pasting them per script.
- `send(cmd, wait, timeout)`: write command, block until `DONE`, then settle-wait. Always `ser.reset_input_buffer()` before writing.
- All coordinates and OCR keywords live in named constants at the top of the file — never inline magic numbers in logic.
- Logs in Korean or English are both fine; keep step numbers in log lines (`[3] ...`) so failures map to the checklist.
- Destructive/irreversible actions (deleting apps) must print a plan and require `y` confirmation when run standalone; allow `--yes` flag for full-pipeline runs.

## Obsidian Notes (project memory across sessions)

Notes live in the Obsidian vault at `C:\hansung\note\project\radius-auto\` (accessible via `additionalDirectories`):

- `00-overview.md` — pipeline stage status + QA checklist as checkboxes. **Update checkboxes when a step is implemented and verified.**
- `dev-log.md` — append a session entry at the end of every session: 완료 / 결정(이유 포함) / 사람 확인 필요.
- `troubleshooting.md` — append 증상 → 원인 → 해결 whenever a non-obvious problem is solved.

At the start of a session, read `dev-log.md` (latest entry) and `00-overview.md` to restore context before doing anything else. Filenames: never add `.md` manually when creating files in Obsidian (it auto-appends).

## Known Constraints & Gotchas

- Knox blocks ADB and absolute pointer input entirely. Do not suggest ADB-based solutions.
- OS pointer acceleration: always use chunked movement (firmware handles this — don't add host-side movement loops).
- Camera frames lag: always flush the capture buffer before OCR.
- OCR misreads are common at low contrast — prefer toggles' pixel-color state checks where text is unreliable.
- Slot positions on the home screen are fixed, but which app occupies which slot varies per device → always detect via OCR, never assume.
- "Remove" on home screen removes the shortcut only; "Uninstall" removes the app. The pipeline's intent for stages 1–2 is shortcut removal/home cleanup.


-참고: `py 코드/main.cpp`는 예전 동작 버전 백업이야. 실제 빌드/플래시되는 펌웨어는 src/main.cpp 하나뿐이니 앞으로 펌웨어 작업은 src/main.cpp만 건드려. py 코드 폴더는 무시해도 돼.

## Claude Code 작업 규칙

### 실기기 실행은 사용자가 직접
- `run_qa.py`, `probe.py` 등 실기기 연결 스크립트는 Claude Code가 실행하지 않는다.
- COM7(ESP32 시리얼)과 IP Webcam 카메라는 Claude Code 환경에서 접근 불가.
- Claude Code의 역할은 코드 작성 + 문법 검증(`.\venv\Scripts\python.exe -m py_compile <file>`)까지. "실행해서 확인해봐"는 하지 않는다.

### Python 인터프리터
- 항상 `.\venv\Scripts\python.exe` 사용. 시스템 `python`에는 `cv2`, `easyocr`, `pyserial` 등이 없다.
- py_compile 검증 명령: `.\venv\Scripts\python.exe -m py_compile <파일>`

### 좌표·키 시퀀스·임계값 보호
- 검증된 좌표, 키 시퀀스, OCR 임계값(RADIO_X_OFFSET, ON_PIX_RATIO 등)은 파일 상단 상수 블록에 보존한다.
- 동작하는 코드는 요청 없이 리팩토링하지 않는다. 버그 수정 범위를 넘는 구조 변경은 하지 않는다.

### 변경 전 plan 먼저
- 여러 함수·파일에 걸친 변경은 코드를 건드리기 전에 변경 계획(어느 함수, 무엇을, 왜)을 먼저 제시한다.
- 큰 변경(새 스테이지 추가, 모듈 재설계 등)은 계획을 확인받은 뒤 코드를 작성한다. 확인 전에 실행하지 않는다.