//main.cpp — Radius 앱 자동 로그인 전용 펌웨어
//
// [사용법]
//   1. 태블릿에서 Radius 로그인 화면(이메일 입력칸)을 띄우고
//      이메일 입력칸을 한 번 탭해서 커서(포커스)를 둔다.
//   2. ESP32에 전원 인가(USB 연결) → BOOT_DELAY_MS 후 자동으로 로그인 시퀀스 실행.
//   3. PC 없이 동작. 시리얼 모니터는 진행상황 확인용(선택).
//
// [최종 배포 형태]
//   ESP32 → 안드로이드 폰(호스트) → USB HID → 태블릿
//   (지금 노트북 연결은 개발/검증용)

#include <Arduino.h>
#include "USB.h"
#include "USBHIDKeyboard.h"
USBHIDKeyboard Keyboard;

// ===== 설정 =====
#define BOOT_DELAY_MS   8000   // 전원 인가 후 로그인 시작까지 대기(태블릿 HID 인식 시간). 필요시 조정
#define TYPE_CHAR_MS    180    // 글자당 입력 간격(ms). 씹힘 있으면 더 키워(220~250)
#define KEY_HOLD_MS     60     // 키 누름 유지 시간(ms)

// ===== 키 입력 (천천히, 확실하게) =====
void typeSlow(const char* text) {
    for (int i = 0; text[i] != '\0'; i++) {
        Keyboard.press(text[i]);
        delay(KEY_HOLD_MS);
        Keyboard.release(text[i]);
        delay(TYPE_CHAR_MS - KEY_HOLD_MS);
    }
}

void tapKey(uint8_t key, int waitMs) {
    Keyboard.press(key);
    delay(KEY_HOLD_MS);
    Keyboard.release(key);
    delay(waitMs);
}

// ===== 로그인 시퀀스 =====
void runLogin() {
    // 키보드 워밍업: 첫 리포트 드롭 방지
    Keyboard.releaseAll(); delay(200);
    Keyboard.releaseAll(); delay(200);

    // ── 화면1: 이메일 ──
    // (이메일 입력칸에 이미 포커스가 있다고 가정. 없으면 아래 TAB 주석 해제)
    // tapKey(KEY_TAB, 400);
    typeSlow("test@radiusxr.com");   delay(500);
    tapKey(KEY_TAB, 400);
    tapKey(KEY_TAB, 400);
    tapKey(KEY_RETURN, 7000);        // 로그인 처리 + 화면전환 대기

    // ── 화면2: 비밀번호 ──
    tapKey(KEY_TAB, 400);
    typeSlow("production2023");       delay(2500);
    tapKey(KEY_TAB, 400);
    tapKey(KEY_TAB, 400);
    tapKey(KEY_RETURN, 7000);

    // ── 화면3: PIN ──
    tapKey(KEY_TAB, 400);
    tapKey(KEY_TAB, 400);
    tapKey(KEY_TAB, 400);
    typeSlow("5994");                 delay(500);
    // PIN이 자동제출 안 되면 아래 주석 해제:
    // tapKey(KEY_RETURN, 1000);
}

void setup() {
    Keyboard.begin();
    USB.begin();
    Serial.begin(115200);
    delay(500);
    Serial.println("READY");

    delay(BOOT_DELAY_MS);
    Serial.println("LOGIN START");
    runLogin();
    Serial.println("LOGIN DONE");
}

void loop() {
    // 로그인은 부팅 시 1회만. 재실행하려면 ESP32 리셋 버튼.
}