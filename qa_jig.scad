// ============================================================
// qa_jig.scad - 폰(카메라) <-> 태블릿 고정 지그
//   목적: 카메라-태블릿 거리/각도를 영구 고정 -> 좌표 캘리브 1회로 끝
//   단위: mm.  OpenSCAD에서 열고 F6 -> STL export.
//
// 배치: 폰과 태블릿을 세워서 마주봄. 폰 뒷면(카메라)이 태블릿 화면을 향함.
//       태블릿 받침이 폰보다 35mm 높음. 둘은 베이스 한 장으로 연결(기하 고정).
// ============================================================

$fn = 48;
eps = 0.1;

// ---------------- 폰 (Pixel 7 Pro) ----------------
phone_w  = 76;     // 폭
phone_h  = 162;    // 높이
phone_t  = 9;      // 두께
phone_port_x0 = 34;   // 바닥 USB-C 시작 (왼쪽에서)
phone_port_x1 = 43;   // 바닥 USB-C 끝
// 렌즈 위치(참고용 주석): 위에서 27mm, 왼쪽에서 32mm(근접 촬영용 렌즈)
//   ※ 폰을 뒤집어 장착하면 카메라 시점 기준 '오른쪽 32mm'가 됨 -> 센터링 시 반전 고려

// ---------------- 태블릿 (TODO: 실측값 입력!) ----------------
tablet_w  = 170;   // <<< 측정 필요
tablet_h  = 250;   // <<< 측정 필요 (받침 높이 차 3.5cm는 이 값과 무관하게 고정)
tablet_t  = 7;     // <<< 측정 필요
tablet_port_x0 = 60;  // <<< 바닥 USB-C 시작 (왼쪽에서, 카메라 시점 기준 확인)
tablet_port_x1 = 69;  // <<<

// ---------------- 기하 ----------------
gap        = 190;  // 촬영거리 Z: 폰 뒷면 ~ 태블릿 화면 (19cm)
tablet_rise = 35;  // 태블릿이 폰보다 높게 (3.5cm)

// ---------------- 공통 구조 파라미터 ----------------
slot_depth = 18;   // 기기 바닥이 슬롯에 들어가는 깊이
slot_tol   = 0.6;  // 끼움 여유(편면). 출력물 타이트하면 키워
wall       = 4;    // 슬롯 벽 두께
back_h_phone  = 55;  // 폰 뒷벽 높이(지지)
back_h_tablet = 70;  // 태블릿 뒷벽 높이(무거우니 더 높게)
front_lip  = 6;    // 앞턱 높이(화면 가리지 않게 낮게)
base_th    = 6;    // 베이스 두께
foot       = 22;   // 앞쪽 발 길이(넘어짐 방지)
cable_pad  = 3;    // 케이블 구멍 양옆 여유

JOIN_BASE  = true; // true=베이스로 연결(권장), false=받침 분리

// ============================================================
// 모듈: 기기 받침 (바닥 슬롯 + 뒷벽 + 앞턱 + 케이블 구멍)
//   기기는 X폭 방향으로 눕혀 세움. 슬롯은 Y두께 방향.
//   화면(또는 카메라)이 향하는 쪽 = +Y (앞), 뒷벽 = -Y (뒤)
// ============================================================
module device_holder(dev_w, dev_t, back_h, port_x0, port_x1) {
    holder_w = dev_w + 2*wall;
    holder_d = dev_t + 2*slot_tol + 2*wall + foot;  // 앞쪽 발 포함
    slot_w   = dev_w + 2*slot_tol;
    slot_t   = dev_t + 2*slot_tol;

    difference() {
        union() {
            // 받침 몸체(슬롯 깊이만큼)
            cube([holder_w, holder_d, slot_depth]);
            // 뒷벽(지지)
            translate([0, 0, 0])
                cube([holder_w, wall, slot_depth + back_h]);
            // 앞턱(낮게)
            translate([0, holder_d - wall, 0])
                cube([holder_w, wall, slot_depth + front_lip]);
        }
        // 슬롯(기기 끼우는 홈) - 뒷벽에서 wall만큼 떨어진 위치
        translate([wall, wall, slot_depth - slot_depth + base_th + eps])
            translate([0, 0, base_th])
            cube([slot_w, slot_t, slot_depth]);
        // 케이블 구멍: 슬롯 바닥을 관통 (포트 x위치)
        cw = (port_x1 - port_x0) + 2*cable_pad;
        translate([wall + port_x0 - cable_pad, -eps, -eps])
            cube([cw, holder_d + 2*eps, base_th + 2*eps]);
    }
}

// ============================================================
// 모듈: 높이 스페이서 (태블릿 받침 아래 끼워 35mm 올림 / 조절용)
// ============================================================
module spacer(w, d, h) {
    cube([w, d, h]);
}

// ============================================================
// 배치
// ============================================================
phone_holder_d  = phone_t  + 2*slot_tol + 2*wall + foot;
tablet_holder_d = tablet_t + 2*slot_tol + 2*wall + foot;

// 폰: 카메라(뒷면)가 +Y(태블릿) 쪽을 향하도록.
//   폰 뒷면 = 슬롯 앞면(+Y쪽). 폰 뒷면 Y좌표 = phone_holder_d - foot - wall
phone_back_y = phone_holder_d - foot - wall;
// 태블릿 화면면이 폰을 향함(-Y쪽). 태블릿 화면 Y = 폰뒷면 + gap
tablet_screen_y = phone_back_y + gap;
tablet_holder_y0 = tablet_screen_y - wall;  // 태블릿 받침 시작 위치

// X 중심 정렬
max_w = max(phone_w, tablet_w) + 2*wall;
phone_x  = (max_w - (phone_w  + 2*wall))/2;
tablet_x = (max_w - (tablet_w + 2*wall))/2;

// --- 베이스 ---
if (JOIN_BASE) {
    base_len = tablet_holder_y0 + tablet_holder_d + 10;
    color("LightGray")
    translate([-5, -5, -base_th])
        cube([max_w + 10, base_len + 10, base_th]);
}

// --- 폰 받침 ---
color("SkyBlue")
translate([phone_x, 0, 0])
    device_holder(phone_w, phone_t, back_h_phone, phone_port_x0, phone_port_x1);

// --- 태블릿 받침 (35mm 스페이서 위에) ---
color("Khaki")
translate([tablet_x, tablet_holder_y0, tablet_rise])
    device_holder(tablet_w, tablet_t, back_h_tablet, tablet_port_x0, tablet_port_x1);

// --- 태블릿 스페이서(35mm) ---
color("Salmon")
translate([tablet_x, tablet_holder_y0, 0])
    spacer(tablet_w + 2*wall, tablet_holder_d, tablet_rise);

// ============================================================
// 참고: 렌즈 광축 시각화 (출력 안 됨, %로 미리보기만)
// ============================================================
%translate([tablet_x + tablet_w/2, phone_back_y, tablet_rise + slot_depth + 60])
    rotate([90,0,0])
    cylinder(h=gap, r=1);
