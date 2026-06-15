//main.cpp
#include <Arduino.h>
#include "USB.h"
#include "USBHIDMouse.h"
#include "USBHIDKeyboard.h"
USBHIDKeyboard Keyboard;
USBHIDMouse Mouse;

// ===== 가속 방지 핵심 설정 =====
#define STEP_SIZE 20
#define STEP_DELAY_US 800
#define RESET_STEP 100
#define RESET_DELAY_US 500

// 슬라이드(드래그)용 - 누른 채 이동하는 속도
#define SWIPE_STEP 15          // 슬라이드 한 스텝 픽셀
#define SWIPE_DELAY_MS 8       // 슬라이드 스텝 간 딜레이(ms). 너무 빠르면 인식 안될 수 있어 약간 줌

void smoothMove(int totalX, int totalY) {
    int remX = totalX, remY = totalY;
    while (remX != 0 || remY != 0) {
        int8_t sx = (int8_t)constrain(remX, -STEP_SIZE, STEP_SIZE);
        int8_t sy = (int8_t)constrain(remY, -STEP_SIZE, STEP_SIZE);
        Mouse.move(sx, sy, 0);
        remX -= sx; remY -= sy;
        if (STEP_DELAY_US > 0) delayMicroseconds(STEP_DELAY_US);
    }
}

// 누른 채로 이동 (슬라이드용) - 버튼은 누르지/떼지 않음, 이동만
void dragMove(int totalX, int totalY) {
    int remX = totalX, remY = totalY;
    while (remX != 0 || remY != 0) {
        int8_t sx = (int8_t)constrain(remX, -SWIPE_STEP, SWIPE_STEP);
        int8_t sy = (int8_t)constrain(remY, -SWIPE_STEP, SWIPE_STEP);
        Mouse.move(sx, sy, 0);
        remX -= sx; remY -= sy;
        delay(SWIPE_DELAY_MS);
    }
}

void resetBottomLeft() {
    for (int i = 0; i < 30; i++) { Mouse.move(-RESET_STEP, RESET_STEP, 0); delayMicroseconds(RESET_DELAY_US); }
    delay(300);
}
void resetBottomRight() {
    for (int i = 0; i < 30; i++) { Mouse.move(RESET_STEP, RESET_STEP, 0); delayMicroseconds(RESET_DELAY_US); }
    delay(300);
}
void resetTopLeft() {
    for (int i = 0; i < 30; i++) { Mouse.move(-RESET_STEP, -RESET_STEP, 0); delayMicroseconds(RESET_DELAY_US); }
    delay(300);
}

void moveTo(int x, int y)   { resetBottomLeft();  smoothMove(x, -y);  delay(100); }
void moveToBR(int x, int y) { resetBottomRight(); smoothMove(-x, -y); delay(100); }
void moveToTL(int x, int y) { resetTopLeft();     smoothMove(x, y);   delay(100); }
void moveRel(int dx, int dy){ smoothMove(dx, dy); delay(100); }

// ===== 슬라이드 =====
// 절대: 좌하단기준 (x1,y1)으로 이동 -> 누름 -> (x2,y2)로 드래그 -> 뗌
void swipe(int x1, int y1, int x2, int y2) {
    moveTo(x1, y1);          // 시작점으로 (안 누르고 이동)
    delay(200);
    Mouse.press(MOUSE_LEFT); // 누름
    delay(150);
    dragMove(x2 - x1, -(y2 - y1));  // 목표까지 누른 채 이동 (y는 화면좌표라 부호 반전)
    delay(150);
    Mouse.release(MOUSE_LEFT); // 뗌
    delay(200);
}
// 상대: 현재 위치에서 누름 -> dx,dy 드래그 -> 뗌
void swipeRel(int dx, int dy) {
    Mouse.press(MOUSE_LEFT);
    delay(150);
    dragMove(dx, dy);
    delay(150);
    Mouse.release(MOUSE_LEFT);
    delay(200);
}

void setup() {
    Mouse.begin(); Keyboard.begin(); USB.begin();
    Serial.begin(115200); delay(500);
    Serial.println("READY");
}

void loop() {
    if (!Serial.available()) return;
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("MOVETL:")) {
        int sep = cmd.indexOf(',', 7);
        if (sep > 0) { moveToTL(cmd.substring(7, sep).toInt(), cmd.substring(sep+1).toInt()); Serial.println("DONE"); }
    } else if (cmd.startsWith("LONGPRESSTL:")) {
        int sep = cmd.indexOf(',', 12);
        if (sep > 0) { moveToTL(cmd.substring(12, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.press(MOUSE_LEFT); delay(1500); Mouse.release(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("MOVEBR:")) {
        int sep = cmd.indexOf(',', 7);
        if (sep > 0) { moveToBR(cmd.substring(7, sep).toInt(), cmd.substring(sep+1).toInt()); Serial.println("DONE"); }
    } else if (cmd.startsWith("LONGPRESSBR:")) {
        int sep = cmd.indexOf(',', 12);
        if (sep > 0) { moveToBR(cmd.substring(12, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.press(MOUSE_LEFT); delay(1500); Mouse.release(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("MOVE:")) {
        int sep = cmd.indexOf(',', 5);
        if (sep > 0) { moveTo(cmd.substring(5, sep).toInt(), cmd.substring(sep+1).toInt()); Serial.println("DONE"); }
    } else if (cmd.startsWith("CLICK:")) {
        int sep = cmd.indexOf(',', 6);
        if (sep > 0) { moveTo(cmd.substring(6, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.click(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("CLICKTL:")) {
        int sep = cmd.indexOf(',', 8);
        if (sep > 0) { moveToTL(cmd.substring(8, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.click(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("LONGPRESS:")) {
        int sep = cmd.indexOf(',', 10);
        if (sep > 0) { moveTo(cmd.substring(10, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.press(MOUSE_LEFT); delay(1500); Mouse.release(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("SWIPEREL:")) {
        // SWIPEREL:dx,dy  현재위치에서 상대 슬라이드
        int sep = cmd.indexOf(',', 9);
        if (sep > 0) { swipeRel(cmd.substring(9, sep).toInt(), cmd.substring(sep+1).toInt()); Serial.println("DONE"); }
    } else if (cmd.startsWith("SWIPE:")) {
        // SWIPE:x1,y1,x2,y2  좌하단기준 절대 슬라이드
        int s1 = cmd.indexOf(',', 6);
        int s2 = cmd.indexOf(',', s1+1);
        int s3 = cmd.indexOf(',', s2+1);
        if (s1>0 && s2>0 && s3>0) {
            int x1 = cmd.substring(6, s1).toInt();
            int y1 = cmd.substring(s1+1, s2).toInt();
            int x2 = cmd.substring(s2+1, s3).toInt();
            int y2 = cmd.substring(s3+1).toInt();
            swipe(x1, y1, x2, y2);
            Serial.println("DONE");
        }
    } else if (cmd.startsWith("MOVEREL:")) {
        int sep = cmd.indexOf(',', 8);
        if (sep > 0) { moveRel(cmd.substring(8, sep).toInt(), cmd.substring(sep+1).toInt()); Serial.println("DONE"); }
    } else if (cmd.startsWith("CLICKREL:")) {
        int sep = cmd.indexOf(',', 9);
        if (sep > 0) { moveRel(cmd.substring(9, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.click(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("LONGPRESSREL:")) {
        int sep = cmd.indexOf(',', 13);
        if (sep > 0) { moveRel(cmd.substring(13, sep).toInt(), cmd.substring(sep+1).toInt()); Mouse.press(MOUSE_LEFT); delay(1500); Mouse.release(MOUSE_LEFT); Serial.println("DONE"); }
    } else if (cmd.startsWith("TYPE:")) {
        String text = cmd.substring(5);
        for (int i = 0; i < text.length(); i++) { Keyboard.print(text[i]); delay(100); }
        Serial.println("DONE");
    } else if (cmd == "KEY:TAB") {
        Keyboard.press(KEY_TAB); delay(50); Keyboard.release(KEY_TAB); Serial.println("DONE");
    } else if (cmd == "KEY:ENTER") {
        Keyboard.press(KEY_RETURN); delay(50); Keyboard.release(KEY_RETURN); Serial.println("DONE");
    } else if (cmd == "KEY:ESC") {
        Keyboard.press(KEY_ESC); delay(50); Keyboard.release(KEY_ESC); Serial.println("DONE");
    } else if (cmd == "KEY:UP") {
        Keyboard.press(KEY_UP_ARROW); delay(50); Keyboard.release(KEY_UP_ARROW); Serial.println("DONE");
    } else if (cmd == "KEY:DOWN") {
        Keyboard.press(KEY_DOWN_ARROW); delay(50); Keyboard.release(KEY_DOWN_ARROW); Serial.println("DONE");
    } else if (cmd == "KEY:LEFT") {
        Keyboard.press(KEY_LEFT_ARROW); delay(50); Keyboard.release(KEY_LEFT_ARROW); Serial.println("DONE");
    } else if (cmd == "KEY:RIGHT") {
        Keyboard.press(KEY_RIGHT_ARROW); delay(50); Keyboard.release(KEY_RIGHT_ARROW); Serial.println("DONE");
    } else if (cmd == "LONGENTER") {
        Keyboard.press(KEY_RETURN); delay(1500); Keyboard.release(KEY_RETURN); Serial.println("DONE");
    }
}