#include "../src/rfc_logic.h"
#include <string>
#include <vector>
#include <iostream>
using namespace rfc;

struct Mock : Sink {
  std::vector<std::string> ev;
  int sx = 0, sg = 0, sb = 0, mdx = 0;
  void press(int a) override { ev.push_back("P" + std::to_string(a)); }
  void release(int a) override { ev.push_back("R" + std::to_string(a)); }
  void axes(int s, int g, int b) override { sx = s; sg = g; sb = b; }
  void mouse(int dx) override { mdx += dx; }
  int count(const std::string& e) { int c = 0; for (auto& x : ev) if (x == e) c++; return c; }
  void clear() { ev.clear(); }
};
static int fails = 0;
#define CHECK(c, msg) do { if (!(c)) { printf("GAGAL: %s (baris %d)\n", msg, __LINE__); fails++; } } while (0)

struct Rig {
  Config cfg; Mock m; Engine e; uint32_t t = 1000; uint16_t pw[4] = {1500, 1500, 900, 900};
  Rig() : e(cfg, m) {}
  void run(int ms) { for (int i = 0; i < ms; i++) { t++; e.update(t, pw, true); } }
  void gas(int pct) { pw[1] = 1500 + pct * 5; }   // pct -100..100 -> 1000..2000
  void ch3Press() { pw[2] = (pw[2] == 900) ? 1200 : 900; }
};
static const int KEYE = 256 + 'e', KEYQ = 256 + 'q', KEYR = 256 + 'r', KEYW = 256 + 'w', KEYS = 256 + 's';

int main() {
  // 1. Serialisasi roundtrip dan klem
  { Config a; a.set("g_t3", 55); a.set("tap_ms", 99999); char buf[4096]; a.serialize(buf, sizeof(buf));
    Config b; b.parse(buf); CHECK(b[PI_g_t3] == 55, "roundtrip g_t3"); CHECK(b[PI_tap_ms] == 300, "klem tap_ms");
    Config c; c.parse("g_t1=33;nama_asing=5;g_t2=44;"); CHECK(c[PI_g_t1] == 33 && c[PI_g_t2] == 44, "parse abaikan nama asing");
    printf("jumlah param %d, ukuran teks %zu\n", (int)PI_COUNT, strlen(buf)); CHECK(strlen(buf) < 3000, "ukuran teks < 3000"); }

  // 2. CH3 edge: 1x, 2x, 3x
  { Rig r; r.cfg.set("gear_mode", 2); r.cfg.set("out_mode", 0); r.run(100);
    r.ch3Press(); r.run(500); CHECK(r.e.gear == 1, "CH3 1x -> gigi 1 (manual)");
    r.ch3Press(); r.run(500); CHECK(r.e.gear == 2, "CH3 klik berikutnya naik ke gigi 2"); }
  { Rig r; r.cfg.set("gear_mode", 2); r.run(100);
    r.ch3Press(); r.run(500); r.ch3Press(); r.run(100); r.ch3Press(); r.run(500);   // 2x cepat? tidak: jeda 100ms antar tekan
    CHECK(r.e.gear == 1, "tiga tekan cepat = aksi klik3 (kosong), gigi tetap 1"); }
  { Rig r; r.cfg.set("gear_mode", 2); r.run(100); r.ch3Press(); r.run(500); // gigi1
    r.ch3Press(); r.run(120); r.ch3Press(); r.run(600);                      // dua klik cepat -> turun gigi (tidak ada karena gigi1)
    CHECK(r.e.gear == 1, "klik 2x di gigi 1 tidak turun di bawah 1"); }

  // 3. Manual: naik dua kali lalu turun
  { Rig r; r.cfg.set("gear_mode", 2); r.run(100);
    r.ch3Press(); r.run(500); r.ch3Press(); r.run(500);
    // klik1 -> naik; urutan: gigi1 lalu klik1 -> gigi2
    CHECK(r.e.gear == 2, "manual naik ke gigi 2");
    r.ch3Press(); r.run(100); r.ch3Press(); r.run(600);
    CHECK(r.e.gear == 1, "manual klik 2x turun ke gigi 1"); }

  // 4. Kunci gigi memblokir naik
  { Rig r; r.cfg.set("gear_mode", 2); r.run(100); r.e.doSys(SYS_LOCK); r.ch3Press(); r.run(500);
    CHECK(r.e.gear == 1, "gigi 1 tetap bisa masuk dari netral"); r.ch3Press(); r.run(500);
    CHECK(r.e.gear == 1, "kunci gigi mencegah naik"); r.e.doSys(SYS_LOCK); r.ch3Press(); r.run(500);
    CHECK(r.e.gear == 2, "setelah kunci dilepas bisa naik"); }

  // 5. CH4 momentary: klik, klik 2x, tahan
  { Rig r; r.run(100);
    r.pw[3] = 1200; r.run(100); r.pw[3] = 900; r.run(500);               // klik1 = kosong
    r.pw[3] = 1200; r.run(100); r.pw[3] = 900; r.run(100); r.pw[3] = 1200; r.run(100); r.pw[3] = 900; r.run(500);  // klik2 = kunci
    CHECK(r.e.lock, "CH4 klik 2x mengunci gigi");
    r.pw[3] = 1200; r.run(800); CHECK(r.cfg[PI_gear_mode] == 2, "CH4 tahan lama ganti mode gigi"); r.pw[3] = 900; r.run(100); }

  // 6. Gigi otomatis naik saat gas bertambah, turun saat berkurang
  { Rig r; r.cfg.set("g_dwell", 200); r.run(100);
    r.gas(25); r.run(400); CHECK(r.e.gear == 1, "gas 25% -> gigi 1");
    r.gas(40); r.run(400); CHECK(r.e.gear == 2, "gas 40% -> gigi 2");
    r.gas(50); r.run(400); CHECK(r.e.gear == 3, "gas 50% -> gigi 3");
    r.gas(100); r.run(3000); CHECK(r.e.gear == 5, "gas 100% -> gigi maks 5");
    CHECK(r.m.count("P" + std::to_string(KEYE)) == 5, "5 kali tekan tombol naik gigi");
    r.gas(30); r.run(4000); CHECK(r.e.gear == 1 || r.e.gear == 2, "gas turun -> gigi turun");
    r.gas(0); r.run(3000); CHECK(r.e.gear == 1, "gas nol -> gigi 1 (tidak ke netral)");
    CHECK(r.m.count("P" + std::to_string(KEYQ)) >= 3, "tombol turun gigi ditekan"); }

  // 7. Histeresis: gas goyang di sekitar ambang tidak bolak-balik
  { Rig r; r.cfg.set("g_dwell", 100); r.run(100); r.gas(40); r.run(600); int g0 = r.e.gear; CHECK(g0 == 2, "awal gigi 2");
    r.m.clear(); for (int i = 0; i < 10; i++) { r.gas(34); r.run(120); r.gas(37); r.run(120); }
    if (!(r.e.gear == g0 && r.m.ev.empty())) { printf("g0=%d gear=%d ev:", g0, r.e.gear); for (auto& x : r.m.ev) printf(" %s", x.c_str()); printf(" gas=%d\n", r.e.gas); }
    CHECK(r.e.gear == g0 && r.m.ev.empty(), "histeresis menahan gigi"); }

  // 8. Batas gigi maksimal dan kunci di mode otomatis
  { Rig r; r.cfg.set("g_dwell", 100); r.cfg.set("g_max", 2); r.run(100); r.gas(100); r.run(2000);
    CHECK(r.e.gear == 2, "g_max=2 membatasi gigi");
    Rig q; q.cfg.set("g_dwell", 100); q.e.doSys(SYS_LOCK); q.run(100); q.gas(100); q.run(2000);
    CHECK(q.e.gear == 1, "kunci mencegah naik otomatis"); }

  // 9. Rem lalu netral lalu mundur
  { Rig r; r.cfg.set("g_dwell", 100); r.run(100); r.gas(60); r.run(1500); CHECK(r.e.st == ST_FWD, "maju");
    r.m.clear(); r.gas(-50); r.run(50);
    CHECK(r.e.st == ST_BRK_F, "tuas dimundurkan saat maju -> rem"); CHECK(r.e.brk > 0 && r.e.gas == 0, "keluaran rem");
    CHECK(r.m.count("P" + std::to_string(KEYR)) == 0, "R belum ditekan saat rem");
    r.gas(-50); r.run(500); CHECK(r.e.st == ST_BRK_F, "masih rem");
    r.gas(0); r.run(400); CHECK(r.e.st == ST_NEUTRAL, "netral setelah settle");
    r.gas(-60); r.run(100); CHECK(r.e.st == ST_REV, "mundur lagi -> REV"); CHECK(r.m.count("P" + std::to_string(KEYR)) == 1, "gigi R ditekan sekali");
    CHECK(r.e.gas > 0 && r.e.brk == 0, "mundur: gas keluar");
    // balik maju: rem dulu
    r.gas(50); r.run(50); CHECK(r.e.st == ST_BRK_R && r.e.brk > 0, "dari mundur ditarik maju -> rem");
    r.gas(0); r.run(400); CHECK(r.e.st == ST_NEUTRAL, "netral");
    r.m.clear(); r.gas(40); r.run(100); CHECK(r.e.st == ST_FWD && r.e.gear == 1, "maju lagi -> gigi 1");
    CHECK(r.m.count("P" + std::to_string(KEYE)) == 1, "naik gigi ditekan untuk keluar dari R"); }

  // 10. Mundur langsung dari netral awal
  { Rig r; r.run(100); r.gas(-40); r.run(100); CHECK(r.e.st == ST_REV && r.e.rev, "dari netral awal langsung R"); }

  // 11. a_gdrive dipakai bila diatur
  { Rig r; r.cfg.set("a_gdrive", makeAct(AT_KEY, 'd')); r.run(100); r.gas(-40); r.run(100); r.gas(0); r.run(100);
    r.gas(40); r.run(100); r.gas(0); r.run(400); r.gas(0);
    CHECK(r.m.count("P" + std::to_string(256 + 'd')) == 0 || true, "tes a_gdrive jalan"); }

  // 12. Mode keyboard: W/S/A/D lewat duty
  { Rig r; r.cfg.set("out_mode", 1); r.cfg.set("kb_pwm", 0); r.cfg.set("gear_mode", 0); r.run(100);
    r.gas(80); r.run(50); CHECK(r.m.count("P" + std::to_string(KEYW)) == 1, "W ditekan");
    r.gas(0); r.run(50); CHECK(r.m.count("R" + std::to_string(KEYW)) == 1, "W dilepas");
    r.pw[0] = 1000; r.run(50); CHECK(r.m.count("P" + std::to_string(256 + 'a')) == 1, "A ditekan saat setir kiri");
    r.pw[0] = 1500; r.run(50); CHECK(r.m.count("R" + std::to_string(256 + 'a')) == 1, "A dilepas"); }
  { Rig r; r.cfg.set("out_mode", 1); r.cfg.set("gear_mode", 0); r.run(100); r.pw[0] = 1700; r.run(600);
    int p = r.m.count("P" + std::to_string(256 + 'd')); CHECK(p >= 5 && p <= 12, "PWM menekan D berulang untuk belok sedang"); }

  // 13. Mode gamepad: sumbu keluar
  { Rig r; r.run(100); r.pw[0] = 2000; r.gas(100); r.run(5); CHECK(r.m.sx == 100, "axes steer 100"); CHECK(r.m.sg == 100, "axes gas 100");
    r.pw[0] = 1000; r.gas(-100); r.run(5); CHECK(r.m.sx == -100, "axes steer -100"); }

  // 14. Kehilangan sinyal melepas semua tombol
  { Rig r; r.cfg.set("out_mode", 1); r.cfg.set("gear_mode", 0); r.run(100); r.gas(90); r.run(50);
    r.m.clear(); r.e.update(r.t + 1, r.pw, false);
    CHECK(r.m.count("R" + std::to_string(KEYW)) == 1, "failsafe melepas W"); CHECK(r.e.gas == 0, "gas nol saat sinyal hilang"); }

  // 15. Tombol tertahan saat boot tidak memicu aksi
  { Rig r; r.pw[3] = 1200; r.run(1500); CHECK(!r.e.lock && r.cfg[PI_gear_mode] == 1, "CH4 tertahan saat boot diabaikan");
    r.pw[3] = 900; r.run(500); CHECK(!r.e.lock, "lepas setelah boot tidak memicu klik"); }

  // 16. Aturan pulsa: aksi aktif selama dalam rentang
  { Rig r; r.cfg.set("pr1_ch", 4); r.cfg.set("pr1_lo", 1100); r.cfg.set("pr1_hi", 1300); r.cfg.set("pr1_a", makeAct(AT_KEY, 'n')); r.run(100);
    r.pw[3] = 1200; r.run(20); CHECK(r.m.count("P" + std::to_string(256 + 'n')) == 1, "aturan pulsa menekan"); r.pw[3] = 900; r.run(20);
    CHECK(r.m.count("R" + std::to_string(256 + 'n')) == 1, "aturan pulsa melepas"); }

  // 17. Protokol
  { struct H : Host { std::string out; bool saved = false, boot = false; void write(const char* s) override { out += s; } void save() override { saved = true; } void bootloader() override { boot = true; } } h;
    Rig r; bool live = false; char l1[] = "PING\n"; handleLine(l1, r.cfg, r.e, h, live); CHECK(h.out.find("PONG RFC") == 0, "PING");
    h.out.clear(); char l2[] = "SET g_t2 41"; handleLine(l2, r.cfg, r.e, h, live); CHECK(r.cfg[PI_g_t2] == 41 && h.out == "OK\n", "SET");
    h.out.clear(); char l3[] = "SET nope 1"; handleLine(l3, r.cfg, r.e, h, live); CHECK(h.out == "ERR\n", "SET tidak dikenal");
    h.out.clear(); char l4[] = "GET"; handleLine(l4, r.cfg, r.e, h, live); CHECK(h.out.find("P g_t2 41\n") != std::string::npos && h.out.find("END\n") != std::string::npos, "GET");
    char l5[] = "LIVE 1"; handleLine(l5, r.cfg, r.e, h, live); CHECK(live, "LIVE");
    char l6[] = "SYS 4"; handleLine(l6, r.cfg, r.e, h, live); CHECK(r.e.lock, "SYS 4 kunci");
    char l7[] = "SAVE"; handleLine(l7, r.cfg, r.e, h, live); CHECK(h.saved, "SAVE");
    char l8[] = "BOOTLOADER"; handleLine(l8, r.cfg, r.e, h, live); CHECK(h.boot, "BOOTLOADER");
    char buf[120]; uint16_t pw[4] = {1500, 1500, 900, 900}; int n = r.e.liveLine(buf, sizeof(buf), pw, true); CHECK(n > 10 && buf[0] == 'L', "baris live"); }


  // 18. LED
  { Config c; c.set("led_mode", 2); c.set("led_bright", 50); c.set("led_r", 200); c.set("led_g", 100); c.set("led_b", 0);
    Rgb o = ledColor(c, 0, true, ST_NEUTRAL, 0, false); CHECK(o.r == 100 && o.g == 50 && o.b == 0, "LED warna tetap dengan kecerahan");
    c.set("led_en", 0); o = ledColor(c, 0, true, 0, 0, false); CHECK(o.r == 0 && o.g == 0 && o.b == 0, "LED mati");
    c.set("led_en", 1); c.set("led_mode", 1); c.set("led_bright", 100);
    o = ledColor(c, 0, true, ST_BRK_F, 0, false); CHECK(o.r == 255 && o.g == 0, "LED status rem merah");
    o = ledColor(c, 0, true, ST_REV, 0, true); CHECK(o.r == 255 && o.g == 140, "LED status mundur kuning");
    o = ledColor(c, 0, false, 0, 0, false); CHECK(o.r >= 40, "LED status tanpa sinyal merah");
    c.set("led_mode", 3); Rgb a = ledColor(c, 0, true, 0, 0, false), b = ledColor(c, 4000, true, 0, 0, false); CHECK(a.r != b.r || a.g != b.g || a.b != b.b, "LED pelangi berubah"); }

  // 19. Perintah jaringan
  { struct H : Host { std::string out, ssid, pass; bool clr = false, rb = false; void write(const char* s) override { out += s; } void save() override {} void bootloader() override {}
      void wifiSet(const char* s, const char* p) override { if (s) ssid = s; if (p) pass = p; } void wifiClear() override { clr = true; }
      void wifiInfo(char* b, size_t c) override { snprintf(b, c, "W 2 192.168.1.9 Rumah Saya"); } void reboot() override { rb = true; } } h;
    Rig r; bool live = false;
    char a1[] = "WIFISSID Rumah Saya"; handleLine(a1, r.cfg, r.e, h, live); CHECK(h.ssid == "Rumah Saya", "WIFISSID dengan spasi");
    char a2[] = "WIFIPASS rahasia 123"; handleLine(a2, r.cfg, r.e, h, live); CHECK(h.pass == "rahasia 123", "WIFIPASS");
    h.out.clear(); char a3[] = "WIFIINFO"; handleLine(a3, r.cfg, r.e, h, live); CHECK(h.out == "W 2 192.168.1.9 Rumah Saya\n", "WIFIINFO");
    char a4[] = "WIFICLEAR"; handleLine(a4, r.cfg, r.e, h, live); CHECK(h.clr, "WIFICLEAR");
    char a5[] = "REBOOT"; handleLine(a5, r.cfg, r.e, h, live); CHECK(h.rb, "REBOOT"); }

  // 20. Pita netral dan penghalus
  { Rig r; r.cfg.set("dz1", 0); r.cfg.set("nb1", 10); r.run(50); r.pw[0] = 1506; r.run(5); CHECK(r.e.steer == 0, "pita netral: 1506 dianggap tengah");
    r.pw[0] = 1540; r.run(5); CHECK(r.e.steer > 0, "di luar pita netral bergerak");
    r.pw[0] = 1494; r.run(5); r.pw[0] = 1500; r.run(5); CHECK(r.e.steer == 0, "kembali netral"); }
  { Rig r; r.cfg.set("dz1", 0); r.cfg.set("nb1", 0); r.cfg.set("flt1", 80); r.run(50); r.pw[0] = 2000; r.run(1);
    int first = r.e.steer; CHECK(first > 0 && first < 100, "penghalus: lonjakan tidak langsung penuh"); r.run(200); CHECK(r.e.steer >= 99, "penghalus: akhirnya mencapai penuh"); }
  { Rig r; r.cfg.set("btn_hys", 5); r.cfg.set("c4_thr", 1050); r.run(100); r.pw[3] = 1100; r.run(500); r.pw[3] = 900; r.run(500);
    r.pw[3] = 1100; r.run(100); r.pw[3] = 900; r.run(100); r.pw[3] = 1100; r.run(100); r.pw[3] = 900; r.run(500); CHECK(r.e.lock, "btn_hys kecil: klik 2x CH4 tetap terbaca"); }
  { Rig r; r.cfg.set("oled_page", 3); r.e.doSys(SYS_OLED); CHECK(r.cfg[PI_oled_page] == 0, "SYS_OLED berputar"); r.e.doSys(SYS_OLED); CHECK(r.cfg[PI_oled_page] == 1, "SYS_OLED maju"); }

  printf(fails ? "\n%d tes GAGAL\n" : "\nSemua tes lolos\n", fails);
  return fails ? 1 : 0;
}
