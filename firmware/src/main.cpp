// RF Controller: remot RC 4CH (GA-4H-RX) -> gamepad/keyboard/mouse USB lewat ESP32-S3.
// Semua logika jalan di sini. Aplikasi Windows hanya untuk setting dan monitor,
// lewat kabel USB (utama), WiFi serumah (TCP 8266), atau Bluetooth LE (Nordic UART).
#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <U8g2lib.h>
#include <USB.h>
#include <USBHIDGamepad.h>
#include <USBHIDKeyboard.h>
#include <USBHIDMouse.h>
#include <WiFi.h>
#include <string>
#include "esp_system.h"
#include "soc/rtc_cntl_reg.h"

#define RFC_FW_VERSION "1.4.0"
#include "rfc_logic.h"

#ifndef PIN_CH1
#define PIN_CH1 4
#define PIN_CH2 5
#define PIN_CH3 6
#define PIN_CH4 7
#endif

#define TCP_PORT 8266
#define NUS_SERVICE "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  // aplikasi menulis ke sini
#define NUS_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  // ESP32 mengirim lewat notify

// ------------------------------------------------------------ pembaca pulsa
static const uint8_t PINS[4] = {PIN_CH1, PIN_CH2, PIN_CH3, PIN_CH4};
static volatile uint32_t gRise[4], gWidth[4], gStamp[4];
static volatile uint32_t gPvMin = 400, gPvMax = 2800;  // jendela pulsa yang dianggap sah (diatur dari aplikasi)

static void IRAM_ATTR onEdge(int i) {
  uint32_t now = micros();
  if (digitalRead(PINS[i])) {
    gRise[i] = now;
  } else {
    uint32_t w = now - gRise[i];
    if (w >= gPvMin && w <= gPvMax) { gWidth[i] = w; gStamp[i] = now; }
  }
}
static void IRAM_ATTR isr0() { onEdge(0); }
static void IRAM_ATTR isr1() { onEdge(1); }
static void IRAM_ATTR isr2() { onEdge(2); }
static void IRAM_ATTR isr3() { onEdge(3); }

// ------------------------------------------------------------ USB HID
USBHIDKeyboard Keyboard;
USBHIDMouse Mouse;
USBHIDGamepad Gamepad;
Preferences prefs;

// Mesin logika hanya menulis KEADAAN YANG DIINGINKAN. Task HID terpisah yang mengirim laporan USB,
// karena SendReport() memblokir sampai host membaca laporan. Dengan begitu loop utama tidak tersendat.
class HidSink : public rfc::Sink {
 public:
  volatile uint8_t want[256];
  volatile uint8_t have[256];
  volatile uint32_t pad = 0;
  volatile uint8_t mouseWant = 0;
  volatile int mouseAcc = 0;
  volatile int8_t ax = 0, arx = -127, ary = -127;

  HidSink() { memset((void*)want, 0, sizeof(want)); memset((void*)have, 0, sizeof(have)); }

  void press(int a) override { apply(a, true); }
  void release(int a) override { apply(a, false); }
  void axes(int steer, int gas, int brake) override {
    upd(ax, (int8_t)(steer * 127 / 100));
    upd(arx, (int8_t)(-127 + brake * 254 / 100));  // pedal kiri: rem
    upd(ary, (int8_t)(-127 + gas * 254 / 100));    // pedal kanan: gas
  }
  void mouse(int dx) override { __atomic_fetch_add(&mouseAcc, dx, __ATOMIC_RELAXED); }

 private:
  static void upd(volatile int8_t& cur, int8_t v) {
    if (v == cur) return;
    if (abs(v - cur) >= 2 || v == 0 || v >= 127 || v <= -127) cur = v;  // abaikan goyangan 1 langkah
  }
  void apply(int a, bool down) {
    int t = rfc::actType(a), c = rfc::actCode(a);
    if (t == rfc::AT_KEY) want[c] = down ? 1 : 0;
    else if (t == rfc::AT_PAD && c >= 1 && c <= 32) { if (down) pad |= (1UL << (c - 1)); else pad &= ~(1UL << (c - 1)); }
    else if (t == rfc::AT_MOUSE && c >= 1 && c <= 3) { uint8_t bit = (uint8_t)(1 << (c - 1)); if (down) mouseWant |= bit; else mouseWant &= (uint8_t)~bit; }
  }
};

static rfc::Config cfg;
static HidSink sink;
static rfc::Engine engine(cfg, sink);

static void hidTask(void*) {
  uint32_t lastPad = 0, sentPad = 0;
  int8_t sx = 0, srx = -127, sry = -127;
  uint8_t mHave = 0;
  bool first = true;
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(2));
    for (int k = 1; k < 256; k++) {
      uint8_t w = sink.want[k];
      if (w != sink.have[k]) {
        if (w) Keyboard.press((uint8_t)k); else Keyboard.release((uint8_t)k);
        sink.have[k] = w;
      }
    }
    uint8_t mw = sink.mouseWant;
    if (mw != mHave) {
      for (int b = 0; b < 3; b++) {
        uint8_t bit = (uint8_t)(1 << b), code = b == 0 ? MOUSE_LEFT : b == 1 ? MOUSE_RIGHT : MOUSE_MIDDLE;
        if ((mw & bit) && !(mHave & bit)) Mouse.press(code);
        if (!(mw & bit) && (mHave & bit)) Mouse.release(code);
      }
      mHave = mw;
    }
    int dx = __atomic_exchange_n(&sink.mouseAcc, 0, __ATOMIC_RELAXED);
    while (dx > 127) { Mouse.move(127, 0); dx -= 127; }
    while (dx < -127) { Mouse.move(-127, 0); dx += 127; }
    if (dx) Mouse.move((int8_t)dx, 0);
    uint32_t now = millis();
    uint32_t pb = sink.pad;
    int8_t x = sink.ax, rx = sink.arx, ry = sink.ary;
    if ((first || pb != sentPad || x != sx || rx != srx || ry != sry) && now - lastPad >= 8) {
      if (Gamepad.send(x, 0, 0, 0, rx, ry, 0, pb)) {   // kalau gagal, dicoba lagi di putaran berikutnya
        sentPad = pb; sx = x; srx = rx; sry = ry; first = false;
      }
      lastPad = now;
    }
  }
}

// ------------------------------------------------------------ jaringan
static String gSsid, gPass;
static bool wifiStarted = false, tcpStarted = false;
static WiFiServer tcpServer(TCP_PORT);

static void saveCfg() {
  static char buf[3072];
  cfg.serialize(buf, sizeof(buf));
  prefs.putString("cfg", buf);
}

// Satu objek per jalur komunikasi; semuanya memakai penangan perintah yang sama.
class Chan : public rfc::Host {
 public:
  bool live = false;
  void feed(char c) {
    if (c == '\n') {
      buf[len] = 0;
      rfc::handleLine(buf, cfg, engine, *this, live);
      len = 0;
    } else if (c != '\r' && len < sizeof(buf) - 1) {
      buf[len++] = c;
    }
  }
  void save() override { saveCfg(); }
  void bootloader() override {
    delay(80);
    REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
    esp_restart();
  }
  void wifiSet(const char* ssid, const char* pass) override {
    if (ssid) { gSsid = ssid; prefs.putString("ssid", gSsid); }
    if (pass) { gPass = pass; prefs.putString("pass", gPass); }
  }
  void wifiClear() override { gSsid = ""; gPass = ""; prefs.remove("ssid"); prefs.remove("pass"); }
  void wifiInfo(char* b, size_t cap) override {
    int state = 0;
    if (cfg[rfc::PI_wifi_en]) state = gSsid.length() == 0 ? 3 : (WiFi.status() == WL_CONNECTED ? 2 : 1);
    String ip = state == 2 ? WiFi.localIP().toString() : String("-");
    snprintf(b, cap, "W %d %s %s", state, ip.c_str(), gSsid.length() ? gSsid.c_str() : "-");
  }
  void reboot() override { delay(80); ESP.restart(); }
 private:
  char buf[128];
  size_t len = 0;
};

class UsbChan : public Chan {
 public:
  void write(const char* s) override { Serial.print(s); }
} usbChan;

class TcpChan : public Chan {
 public:
  WiFiClient cli;
  void write(const char* s) override { if (cli.connected()) cli.print(s); }
} tcpChan;

static BLECharacteristic* bleTx = nullptr;
static volatile bool bleConnected = false;

class BleChan : public Chan {
 public:
  std::string out;
  std::string inbox;
  void write(const char* s) override { if (bleConnected && out.size() < 6000) out += s; }
  void pump() {
    if (!bleConnected) { out.clear(); return; }
    if (out.empty() || !bleTx) return;
    size_t n = out.size() < 20 ? out.size() : 20;
    bleTx->setValue((uint8_t*)out.data(), n);
    bleTx->notify();
    out.erase(0, n);
  }
} bleChan;

class BleServerCb : public BLEServerCallbacks {
  void onConnect(BLEServer*) override { bleConnected = true; }
  void onDisconnect(BLEServer*) override {
    bleConnected = false;
    bleChan.live = false;
    BLEDevice::startAdvertising();
  }
};

class BleRxCb : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* c) override {
    auto v = c->getValue();
    for (size_t i = 0; i < v.length(); i++) bleChan.inbox += (char)v[i];
  }
};

static void startBle() {
  BLEDevice::init("RF CONTROL");
  BLEServer* srv = BLEDevice::createServer();
  srv->setCallbacks(new BleServerCb());
  BLEService* svc = srv->createService(NUS_SERVICE);
  bleTx = svc->createCharacteristic(NUS_TX, BLECharacteristic::PROPERTY_NOTIFY);
  bleTx->addDescriptor(new BLE2902());
  BLECharacteristic* rx = svc->createCharacteristic(NUS_RX, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  rx->setCallbacks(new BleRxCb());
  svc->start();
  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(NUS_SERVICE);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}

static void startWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("rfcontroller");
  WiFi.setSleep(false);  // tanpa hemat daya supaya latensi kecil
  WiFi.setAutoReconnect(true);
  WiFi.begin(gSsid.c_str(), gPass.c_str());
}

static void serviceWifi() {
  if (!wifiStarted || WiFi.status() != WL_CONNECTED) { tcpChan.live = false; return; }
  if (!tcpStarted) {
    MDNS.begin("rfcontroller");
    MDNS.addService("rfc", "tcp", TCP_PORT);
    tcpServer.begin();
    tcpServer.setNoDelay(true);
    tcpStarted = true;
  }
  WiFiClient c = tcpServer.accept();
  if (c) {
    if (tcpChan.cli && tcpChan.cli.connected()) c.stop();
    else { tcpChan.cli = c; tcpChan.cli.setNoDelay(true); tcpChan.live = false; }
  }
  if (tcpChan.cli && tcpChan.cli.connected()) {
    while (tcpChan.cli.available()) tcpChan.feed((char)tcpChan.cli.read());
  } else {
    tcpChan.live = false;
  }
}

// ------------------------------------------------------------ LED RGB
static int ledPin = -1;
static rfc::Rgb ledLast{255, 255, 255};

static void serviceLed(uint32_t now, bool sig) {
  static uint32_t last = 0;
  if (now - last < 20) return;
  last = now;
  int pin = cfg[rfc::PI_led_pin];
  if (pin == 19 || pin == 20) return;  // pin USB, jangan disentuh
  rfc::Rgb c = rfc::ledColor(cfg, now, sig, engine.st, engine.gas, engine.rev);
  if (pin != ledPin) {
    if (ledPin >= 0) rgbLedWrite(ledPin, 0, 0, 0);
    ledPin = pin;
    ledLast = rfc::Rgb{255, 255, 255};
  }
  if (c.r != ledLast.r || c.g != ledLast.g || c.b != ledLast.b) {
    rgbLedWrite(pin, c.r, c.g, c.b);
    ledLast = c;
  }
}

// ------------------------------------------------------------ OLED (SSD1306 / SH1106, I2C)
static U8G2* oled = nullptr;
static volatile uint16_t gPw[4];
static volatile bool gSig = false;

static bool wifiUp() { return wifiStarted && WiFi.status() == WL_CONNECTED; }

static void oledBar(int x, int y, int w, int h, int pct, bool center) {
  oled->drawFrame(x, y, w, h);
  if (center) {
    int mid = x + w / 2;
    int len = abs(pct) * (w / 2 - 2) / 100;
    if (pct >= 0) oled->drawBox(mid, y + 2, len, h - 4);
    else oled->drawBox(mid - len, y + 2, len, h - 4);
    oled->drawVLine(mid, y, h);
  } else {
    int len = constrain(pct, 0, 100) * (w - 4) / 100;
    if (len > 0) oled->drawBox(x + 2, y + 2, len, h - 4);
  }
}

static void oledPageStatus(uint32_t now) {
  const char* om[] = {"PAD", "KEY", "MOUSE"};
  const char* gm[] = {"GIGI OFF", "AUTO", "MANUAL"};
  char buf[24];
  oled->setFont(u8g2_font_6x10_tf);
  oled->drawStr(0, 9, om[cfg[rfc::PI_out_mode] % 3]);
  oled->drawStr(36, 9, gm[cfg[rfc::PI_gear_mode] % 3]);
  if (engine.lock) oled->drawStr(92, 9, "LOCK");
  snprintf(buf, sizeof(buf), "%s%s%s", usbChan.live ? "U" : "", wifiUp() ? "W" : "", bleConnected ? "B" : "");
  oled->drawStr(128 - 6 * (int)strlen(buf), 9, buf);
  oled->drawHLine(0, 12, 128);
  if (!gSig) {
    if ((now / 500) & 1) { oled->setFont(u8g2_font_helvB10_tf); oled->drawStr(18, 42, "NO SIGNAL"); }
    oled->setFont(u8g2_font_6x10_tf);
    oled->drawStr(12, 60, "Nyalakan remot");
    return;
  }
  oled->setFont(u8g2_font_logisoso32_tf);
  static const char* GN[] = {"N", "1", "2", "3", "4", "5", "6"};
  const char* g = engine.rev ? "R" : GN[engine.gear < 0 ? 0 : (engine.gear > 6 ? 6 : engine.gear)];
  oled->drawStr(6, 54, g);
  oled->setFont(u8g2_font_6x10_tf);
  const char* stn[] = {"NETRAL", "MAJU", "REM", "MUNDUR", "REM", "KE R"};
  oled->drawStr(52, 25, stn[engine.st % 6]);
  oled->drawStr(52, 38, "GAS");
  oledBar(76, 30, 50, 9, engine.gas, false);
  oled->drawStr(52, 51, "REM");
  oledBar(76, 43, 50, 9, engine.brk, false);
  snprintf(buf, sizeof(buf), "STR %d", engine.steer);
  oled->drawStr(52, 63, buf);
}

static void oledPageBars() {
  char buf[16];
  oled->setFont(u8g2_font_6x10_tf);
  oled->drawStr(0, 11, "SETIR"); oledBar(40, 2, 60, 11, engine.steer, true);
  snprintf(buf, sizeof(buf), "%d", engine.steer); oled->drawStr(104, 11, buf);
  oled->drawStr(0, 31, "GAS"); oledBar(40, 22, 60, 11, engine.gas, false);
  snprintf(buf, sizeof(buf), "%d", engine.gas); oled->drawStr(104, 31, buf);
  oled->drawStr(0, 51, "REM"); oledBar(40, 42, 60, 11, engine.brk, false);
  snprintf(buf, sizeof(buf), "%d", engine.brk); oled->drawStr(104, 51, buf);
  snprintf(buf, sizeof(buf), "G%d  %s", engine.gear, engine.rev ? "R" : "D");
  oled->drawStr(0, 63, buf);
}

static void oledPagePulse() {
  char buf[24];
  oled->setFont(u8g2_font_6x10_tf);
  for (int i = 0; i < 4; i++) {
    int y = 12 + i * 16;
    uint16_t p = gPw[i];
    snprintf(buf, sizeof(buf), "CH%d %4u", i + 1, p);
    oled->drawStr(0, y, buf);
    oledBar(68, y - 9, 58, 10, p ? constrain(((int)p - 800) * 100 / 1400, 0, 100) : 0, false);
  }
}

static void oledTask(void*) {
  uint32_t lastSwitch = 0, born = millis();
  int autoPage = 0, lastContrast = -1, lastRot = -1;
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(100));
    uint32_t now = millis();
    if (!oled) continue;
    if (cfg[rfc::PI_oled_contrast] != lastContrast) { lastContrast = cfg[rfc::PI_oled_contrast]; oled->setContrast(lastContrast); }
    if (cfg[rfc::PI_oled_rot] != lastRot) { lastRot = cfg[rfc::PI_oled_rot]; oled->setFlipMode(lastRot); }
    oled->clearBuffer();
    if (now - born < 1500) {
      oled->setFont(u8g2_font_helvB10_tf);
      oled->drawStr(24, 30, "RF CONTROL");
      oled->setFont(u8g2_font_6x10_tf);
      oled->drawStr(34, 46, "v" RFC_FW_VERSION);
    } else {
      int mode = cfg[rfc::PI_oled_page], page;
      if (mode == 0) {
        if (now - lastSwitch >= (uint32_t)cfg[rfc::PI_oled_cycle] * 1000UL) { lastSwitch = now; autoPage = (autoPage + 1) % 3; }
        page = autoPage;
      } else page = mode - 1;
      if (page == 0) oledPageStatus(now);
      else if (page == 1) oledPageBars();
      else oledPagePulse();
    }
    oled->sendBuffer();
  }
}

static void startOled() {
  uint8_t sda = (uint8_t)cfg[rfc::PI_oled_sda], scl = (uint8_t)cfg[rfc::PI_oled_scl];
  if (cfg[rfc::PI_oled_type]) oled = new U8G2_SH1106_128X64_NONAME_F_HW_I2C(U8G2_R0, U8X8_PIN_NONE, scl, sda);
  else oled = new U8G2_SSD1306_128X64_NONAME_F_HW_I2C(U8G2_R0, U8X8_PIN_NONE, scl, sda);
  oled->begin();
  oled->setBusClock(400000);
  xTaskCreatePinnedToCore(oledTask, "oled", 6144, nullptr, 1, nullptr, 0);
}

// ------------------------------------------------------------ setup dan loop
void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  prefs.begin("rfc", false);
  String s = prefs.getString("cfg", "");
  if (s.length() > 0) cfg.parse(s.c_str());
  gSsid = prefs.getString("ssid", "");
  gPass = prefs.getString("pass", "");
  engine.resetAll();

  for (int i = 0; i < 4; i++) pinMode(PINS[i], INPUT_PULLDOWN);
  attachInterrupt(PINS[0], isr0, CHANGE);
  attachInterrupt(PINS[1], isr1, CHANGE);
  attachInterrupt(PINS[2], isr2, CHANGE);
  attachInterrupt(PINS[3], isr3, CHANGE);

  USB.productName("RF CONTROL");
  USB.manufacturerName("RF CONTROL");
  Keyboard.begin();
  Mouse.begin();
  Gamepad.begin();
  USB.begin();
  xTaskCreatePinnedToCore(hidTask, "hid", 4096, nullptr, 3, nullptr, 1);

  if (cfg[rfc::PI_oled_en]) startOled();
  if (cfg[rfc::PI_ble_en]) startBle();
  if (cfg[rfc::PI_wifi_en] && gSsid.length()) { startWifi(); wifiStarted = true; }
}

static void sendLive(Chan& ch, const char* line, uint32_t now, uint32_t& last, uint32_t every) {
  if (ch.live && now - last >= every) { last = now; ch.write(line); }
}

void loop() {
  static uint32_t lastUsb = 0, lastTcp = 0, lastBle = 0, lastBlePump = 0;
  uint32_t nowMs = millis();
  uint32_t nowUs = micros();
  uint32_t limit = (uint32_t)cfg[rfc::PI_failsafe_ms] * 1000UL;

  uint16_t pw[4];
  for (int i = 0; i < 4; i++) {
    uint32_t w = gWidth[i], age = nowUs - gStamp[i];
    pw[i] = (w && age < limit) ? (uint16_t)w : 0;
  }
  bool sig = pw[0] && pw[1];
  for (int i = 0; i < 4; i++) gPw[i] = pw[i];
  gSig = sig;
  gPvMin = (uint32_t)cfg[rfc::PI_pv_min];
  gPvMax = (uint32_t)cfg[rfc::PI_pv_max];

  engine.update(nowMs, pw, sig);
  serviceLed(nowMs, sig);
  static unsigned lastEv = 0;
  if (engine.evSeq != lastEv) {
    lastEv = engine.evSeq;
    char eb[40];
    engine.eventLine(eb, sizeof(eb));
    if (usbChan.live) usbChan.write(eb);
    if (tcpChan.live) tcpChan.write(eb);
    if (bleChan.live) bleChan.write(eb);
  }

  while (Serial.available()) usbChan.feed((char)Serial.read());
  serviceWifi();
  if (!bleChan.inbox.empty()) {
    std::string in;
    in.swap(bleChan.inbox);
    for (char c : in) bleChan.feed(c);
  }
  if (nowMs - lastBlePump >= 6) { lastBlePump = nowMs; bleChan.pump(); }

  if (usbChan.live || tcpChan.live || bleChan.live) {
    char line[128];
    engine.liveLine(line, sizeof(line), pw, sig);
    sendLive(usbChan, line, nowMs, lastUsb, 50);
    sendLive(tcpChan, line, nowMs, lastTcp, 50);
    sendLive(bleChan, line, nowMs, lastBle, 120);
  }
  delay(1);
}
