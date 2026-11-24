// Logika inti RF Controller. Tanpa dependensi Arduino supaya bisa diuji di PC.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

namespace rfc {

enum ParamIdx {
#define P(n, d, mi, ma) PI_##n,
#include "params.def"
#undef P
  PI_COUNT
};

struct ParamInfo {
  const char* name;
  int32_t def, mn, mx;
};

static const ParamInfo PARAMS[PI_COUNT] = {
#define P(n, d, mi, ma) {#n, d, mi, ma},
#include "params.def"
#undef P
};

enum ActType { AT_NONE = 0, AT_KEY = 1, AT_PAD = 2, AT_MOUSE = 3, AT_SYS = 4 };
enum SysCode { SYS_GUP = 1, SYS_GDN = 2, SYS_MODE = 3, SYS_LOCK = 4, SYS_OUT = 5, SYS_OLED = 6 };
enum State { ST_NEUTRAL = 0, ST_FWD = 1, ST_BRK_F = 2, ST_REV = 3, ST_BRK_R = 4, ST_SHIFTR = 5 };

static const int ACT_MAX = 1280;
inline int actType(int a) { return a >> 8; }
inline int actCode(int a) { return a & 255; }
inline int makeAct(int t, int c) { return t * 256 + c; }

struct Config {
  int32_t v[PI_COUNT];
  Config() { defaults(); }
  void defaults() {
    for (int i = 0; i < PI_COUNT; i++) v[i] = PARAMS[i].def;
  }
  int find(const char* n) const {
    for (int i = 0; i < PI_COUNT; i++)
      if (!strcmp(PARAMS[i].name, n)) return i;
    return -1;
  }
  bool set(const char* n, long x) {
    int i = find(n);
    if (i < 0) return false;
    if (x < PARAMS[i].mn) x = PARAMS[i].mn;
    if (x > PARAMS[i].mx) x = PARAMS[i].mx;
    v[i] = (int32_t)x;
    return true;
  }
  int32_t operator[](int i) const { return v[i]; }
  // Format teks "nama=nilai;nama=nilai;" tahan terhadap perubahan versi.
  size_t serialize(char* buf, size_t cap) const {
    size_t n = 0;
    for (int i = 0; i < PI_COUNT; i++) {
      int w = snprintf(buf + n, cap - n, "%s=%ld;", PARAMS[i].name, (long)v[i]);
      if (w < 0 || (size_t)w >= cap - n) break;
      n += (size_t)w;
    }
    return n;
  }
  void parse(const char* s) {
    char name[24];
    while (*s) {
      const char* eq = strchr(s, '=');
      const char* end = strchr(s, ';');
      if (!eq || !end || eq > end) break;
      size_t len = (size_t)(eq - s);
      if (len > 0 && len < sizeof(name)) {
        memcpy(name, s, len);
        name[len] = 0;
        set(name, strtol(eq + 1, nullptr, 10));
      }
      s = end + 1;
    }
  }
};

struct Sink {
  virtual void press(int act) = 0;
  virtual void release(int act) = 0;
  virtual void axes(int steer, int gas, int brake) = 0;
  virtual void mouse(int dx) = 0;
  virtual ~Sink() {}
};

struct Gesture {
  bool init = false, lvl = false, candidate = false;
  bool longOn = false, ignoreRel = false, baselineReady = false;
  uint32_t candidateSince = 0, tPress = 0, tLast = 0;
  float baseline = 0.0f;
  int clicks = 0;
  int click = 0;
  bool longStart = false, longEnd = false;

  static const uint32_t DEBOUNCE_MS = 35;
  static const int PRESS_DELTA_US = 150;
  static const int RELEASE_DELTA_US = 130;

  void reset() {
    init = false; lvl = false; candidate = false;
    longOn = false; ignoreRel = false; baselineReady = false;
    candidateSince = tPress = tLast = 0;
    baseline = 0.0f;
    clicks = 0; click = 0; longStart = longEnd = false;
  }

  // type 0 = momentary: one click is finalized on release;
  // type 1 = multi-click counted on each press edge;
  // type 2 = multi-click counted on every stable transition.
  // Baseline is learned from the first valid receiver pulse, so either
  // 900->1900 or 1900->900 can represent a press. This avoids fixed-polarity
  // assumptions when the transmitter channel is reversed.
  void update(uint32_t now, int pw, int /*thr*/, int type,
              int clickMs, int longMs, int /*hys*/ = 40) {
    click = 0;
    longStart = longEnd = false;

    if (pw <= 0) {
      // Lost channel data must not leave a virtual button held forever.
      if (init && lvl) {
        lvl = candidate = false;
        if (type == 0 && !ignoreRel && !longOn) {
          if (clicks < 3) clicks++;
          tLast = now;
        }
        if (longOn) { longOn = false; longEnd = true; }
      }
      if (clicks > 0 && (uint32_t)(now - tLast) >= (uint32_t)clickMs) {
        click = clicks > 3 ? 3 : clicks;
        clicks = 0;
      }
      return;
    }

    if (!baselineReady) {
      baseline = (float)pw;
      baselineReady = true;
      init = true;
      lvl = candidate = false;
      candidateSince = tLast = now;
      return;
    }

    float delta = (float)pw - baseline;
    float magnitude = fabsf(delta);
    bool raw = lvl ? (magnitude >= RELEASE_DELTA_US)
                   : (magnitude >= PRESS_DELTA_US);

    // Slowly follow harmless receiver drift only while released and near baseline.
    if (!lvl && magnitude < RELEASE_DELTA_US) {
      baseline += ((float)pw - baseline) * 0.025f;
    }

    if (raw != candidate) {
      candidate = raw;
      candidateSince = now;
    }

    if (candidate != lvl && (uint32_t)(now - candidateSince) >= DEBOUNCE_MS) {
      lvl = candidate;
      if (lvl) {
        tPress = now;
        longOn = false;
        if (type == 1 || type == 2) {
          if (clicks < 3) clicks++;
          tLast = now;
        }
      } else {
        if (type == 2) {
          if (clicks < 3) clicks++;
          tLast = now;
        } else if (type == 0) {
          if (ignoreRel) ignoreRel = false;
          else if (longOn) { longOn = false; longEnd = true; }
          else { if (clicks < 3) clicks++; tLast = now; }
        }
      }
    }

    if (type == 0 && lvl && !longOn && !ignoreRel &&
        (uint32_t)(now - tPress) >= (uint32_t)longMs) {
      longOn = true;
      longStart = true;
      clicks = 0;
    }

    // Only finalize after release; this keeps the last press in a multi-click
    // sequence from being emitted early while the button is still held.
    if (clicks > 0 && (type != 0 || !lvl) &&
        (uint32_t)(now - tLast) >= (uint32_t)clickMs) {
      click = clicks > 3 ? 3 : clicks;
      clicks = 0;
    }
  }
};

inline int normAxis(int p, int mn, int mid, int mx, int dz, int ex, int inv) {
  if (p <= 0) return 0;
  float v;
  if (p >= mid) v = (mx > mid) ? (float)(p - mid) / (float)(mx - mid) : 0.f;
  else v = (mid > mn) ? -(float)(mid - p) / (float)(mid - mn) : 0.f;
  if (v > 1.f) v = 1.f;
  if (v < -1.f) v = -1.f;
  if (inv) v = -v;
  float a = fabsf(v), d = dz / 100.f;
  if (a <= d) return 0;
  a = (a - d) / (1.f - d);
  float e = ex / 100.f;
  a = (1.f - e) * a + e * a * a * a;
  int r = (int)lroundf(a * 100.f);
  return v < 0 ? -r : r;
}

class Engine {
 public:
  Engine(Config& c, Sink& s) : cfg(c), sink(s) { memset(cnt, 0, sizeof(cnt)); resetAll(); }

  // keadaan yang bisa dibaca (untuk tampilan live)
  int steer = 0, thr = 0, gas = 0, brk = 0, gear = 0, st = ST_NEUTRAL;
  bool rev = false, lock = false;
  // kejadian gestur terakhir (untuk diagnosa di aplikasi)
  unsigned evSeq = 0;
  int evCh = 0, evKind = 0, evAct = 0;
  void testAct(int a) { tap(a); ev(0, 0, a); }
  int eventLine(char* buf, size_t cap) const { return snprintf(buf, cap, "E %d %d %d\n", evCh, evKind, evAct); }

  void resetAll() {
    releaseAll();
    steer = thr = gas = brk = 0; st = ST_NEUTRAL;
    fa[0] = fa[1] = 0;
    g3.reset(); g4.reset();
    inNz = false; longAct = 0; npend = 0; wasSig = false;
    seqLeft = 0; pHeld = pArmed = false;
    lastOm = cfg[PI_out_mode];
    memset(ruleOn, 0, sizeof(ruleOn)); memset(kbOn, 0, sizeof(kbOn));
  }

  void update(uint32_t now, const uint16_t pw[4], bool sig) {
    tnow = now;
    dtF = (lastUpd && now - lastUpd < 100) ? (float)(now - lastUpd) : 0.f;
    lastUpd = now;
    if (!sig) {
      if (wasSig) failsafe();
      wasSig = false;
      return;
    }
    wasSig = true;
    int om = cfg[PI_out_mode];
    if (om != lastOm) { releaseAll(); lastOm = om; }

    for (int i = 0; i < npend;) {
      if ((int32_t)(tnow - pend[i].due) >= 0) { dec(pend[i].act); pend[i] = pend[--npend]; }
      else i++;
    }

    int q0 = cond(pw[0], 0), q1 = cond(pw[1], 1);
    steer = normAxis(q0, cfg[PI_c1_min], cfg[PI_c1_mid], cfg[PI_c1_max], cfg[PI_dz1], cfg[PI_ex1], cfg[PI_inv1]) * cfg[PI_st_limit] / 100;
    thr = normAxis(q1, cfg[PI_c2_min], cfg[PI_c2_mid], cfg[PI_c2_max], cfg[PI_dz2], cfg[PI_ex2], cfg[PI_inv2]) * cfg[PI_thr_limit] / 100;

    buttons(pw);
    pulseRules(pw);
    drive();
    autoGear();
    emit();
  }

  void doSys(int code) {
    int gm = cfg[PI_gear_mode];
    switch (code) {
      case SYS_GUP:
        if (gm != 2 || rev) break;
        if (gear == 0) engageFirst(false);
        else if (gear < cfg[PI_g_max] && !lock) shiftTo(gear + 1);
        break;
      case SYS_GDN:
        if (gm != 2 || rev) break;
        if (gear > 1) shiftTo(gear - 1);
        break;
      case SYS_MODE: cfg.v[PI_gear_mode] = (gm == 0) ? 3 : (gm == 3 ? 1 : (gm == 1 ? 2 : 3)); break;
      case SYS_LOCK: lock = !lock; break;
      case SYS_OUT: cfg.v[PI_out_mode] = (cfg[PI_out_mode] + 1) % 3; break;
      case SYS_OLED: cfg.v[PI_oled_page] = (cfg[PI_oled_page] + 1) % 4; break;
      default: break;
    }
  }

  int liveLine(char* buf, size_t cap, const uint16_t* pw, bool sig) const {
    return snprintf(buf, cap, "L %u %u %u %u %d %d %d %d %d %d %d %d %d %d %d\n", pw[0], pw[1], pw[2], pw[3], sig ? 1 : 0,
                    steer, thr, gas, brk, gear, st, (int)cfg[PI_gear_mode], lock ? 1 : 0, (int)cfg[PI_out_mode], rev ? 1 : 0);
  }

 private:
  Config& cfg;
  Sink& sink;
  uint32_t tnow = 0, lastShift = 0, nzT = 0, mouseT = 0;
  bool inNz = false, wasSig = false;
  int lastOm = 0, longAct = 0, mouseAcc = 0;
  uint8_t cnt[ACT_MAX];
  uint32_t brkT = 0;
  int seqLeft = 0, seqAct = 0;
  uint32_t seqNext = 0;
  bool pHeld = false, pArmed = false;
  uint32_t pHeldT = 0, pRelT = 0;
  int sdAcc[4] = {0, 0, 0, 0};
  bool sdOut[4] = {false, false, false, false};
  uint32_t sdSlot[4] = {0, 0, 0, 0};
  void ev(int ch, int kind, int act) { evSeq++; evCh = ch; evKind = kind; evAct = act; }
  struct Pend { int act; uint32_t due; } pend[16];
  int npend = 0;
  Gesture g3, g4;
  bool ruleOn[6]; int ruleAct[6];
  bool kbOn[4]; int kbAct[4];

  void inc(int a) {
    if (a <= 0 || a >= ACT_MAX) return;
    int t = actType(a);
    if (t == AT_NONE) return;
    if (t == AT_SYS) { doSys(actCode(a)); return; }
    if (cnt[a] == 0) sink.press(a);
    if (cnt[a] < 250) cnt[a]++;
  }
  void dec(int a) {
    if (a <= 0 || a >= ACT_MAX || actType(a) == AT_SYS || actType(a) == AT_NONE) return;
    if (cnt[a] == 0) return;
    if (--cnt[a] == 0) sink.release(a);
  }
  void tap(int a) {
    if (a <= 0 || a >= ACT_MAX) return;
    if (actType(a) == AT_SYS) { doSys(actCode(a)); return; }
    if (actType(a) == AT_NONE) return;
    inc(a);
    if (npend < 16) { pend[npend].act = a; pend[npend].due = tnow + (uint32_t)cfg[PI_tap_ms]; npend++; }
    else dec(a);
  }
  void releaseAll() {
    for (int i = 1; i < ACT_MAX; i++)
      if (cnt[i]) { cnt[i] = 0; sink.release(i); }
    npend = 0;
    memset(ruleOn, 0, sizeof(ruleOn)); memset(kbOn, 0, sizeof(kbOn));
    longAct = 0; mouseAcc = 0;
    for (int i = 0; i < 4; i++) { sdAcc[i] = 0; sdOut[i] = false; }
  }
  void failsafe() {
    releaseAll();
    steer = thr = gas = brk = 0;
    st = ST_NEUTRAL; inNz = false; fa[0] = fa[1] = 0;
    seqLeft = 0; pHeld = pArmed = false;
    g3.reset(); g4.reset();
    sink.axes(0, 0, 0);
  }

  // Penghalus (EMA) dan pita netral dalam mikrodetik supaya posisi diam tetap tepat di tengah.
  float fa[2] = {0, 0};
  float dtF = 0;
  uint32_t lastUpd = 0;
  int cond(int p, int i) {
    if (p <= 0) { fa[i] = 0; return 0; }
    float tau = cfg.v[PI_flt1 + i] * 2.f;  // konstanta waktu penghalus dalam ms
    float a = tau <= 0 ? 1.f : dtF / (tau + dtF);
    fa[i] = (fa[i] <= 0) ? (float)p : fa[i] + a * ((float)p - fa[i]);
    int v = (int)lroundf(fa[i]);
    int mid = i == 0 ? cfg[PI_c1_mid] : cfg[PI_c2_mid];
    if (abs(v - mid) <= cfg.v[PI_nb1 + i]) v = mid;
    return v;
  }

  void buttons(const uint16_t* pw) {
    g3.update(tnow, pw[2], cfg[PI_c3_thr], cfg[PI_c3_type], cfg[PI_click_ms], cfg[PI_long_ms], cfg[PI_btn_hys]);
    g4.update(tnow, pw[3], cfg[PI_c4_thr], cfg[PI_c4_type], cfg[PI_click_ms], cfg[PI_long_ms], cfg[PI_btn_hys]);
    if (g3.click) { int a = cfg.v[PI_a_c3_1 + g3.click - 1]; ev(3, g3.click, a); tap(a); }
    if (g4.click) { int a = cfg.v[PI_a_c4_1 + g4.click - 1]; ev(4, g4.click, a); tap(a); }
    if (g4.longStart) { longAct = cfg[PI_a_c4_l]; ev(4, 9, longAct); inc(longAct); }
    if (g4.longEnd && longAct) { dec(longAct); longAct = 0; }
  }

  void pulseRules(const uint16_t* pw) {
    for (int r = 0; r < 6; r++) {
      int b = PI_pr1_ch + r * 4;
      int ch = cfg[b], lo = cfg[b + 1], hi = cfg[b + 2], a = cfg[b + 3];
      bool on = ch >= 1 && ch <= 4 && a > 0 && pw[ch - 1] >= lo && pw[ch - 1] <= hi;
      if (on && !ruleOn[r]) { ruleOn[r] = true; ruleAct[r] = a; inc(a); }
      else if (!on && ruleOn[r]) { ruleOn[r] = false; dec(ruleAct[r]); }
    }
  }

  int T(int n) const { return cfg.v[PI_g_t1 + n - 1]; }

  void shiftTo(int n) {
    if (cfg[PI_gear_mode] == 0) return;
    if (cfg[PI_g_direct]) tap(cfg.v[PI_gk1 + n - 1]);
    else if (n > gear) tap(cfg[PI_a_gup]);
    else tap(cfg[PI_a_gdn]);
    gear = n; lastShift = tnow;
  }
  void engageFirst(bool fromRev) {
    if (cfg[PI_gear_mode] == 0) { gear = 1; return; }
    if (fromRev && cfg[PI_a_gdrive]) tap(cfg[PI_a_gdrive]);
    else if (cfg[PI_g_direct]) tap(cfg[PI_gk1]);
    else tap(cfg[PI_a_gup]);
    gear = 1; lastShift = tnow;
  }
  void enterFwd() {
    st = ST_FWD;
    int gm = cfg[PI_gear_mode];
    if (rev) { rev = false; gear = 0; engageFirst(true); }          // masih R: naik sendiri ke gigi 1
    else if (gear == 0 && (gm == 2 || gm == 3)) engageFirst(false);  // masih netral: naik sendiri
  }
  // Mulai mundur. Dengan r_seq=1, tombol Turun gigi ditekan sebanyak gigi sekarang (jeda seq_delay_ms) sampai gigi R.
  void enterRev() {
    if (rev) { st = ST_REV; return; }
    if (cfg[PI_gear_mode] == 0) { rev = true; gear = 0; st = ST_REV; return; }
    if (cfg[PI_r_seq] && !cfg[PI_g_direct]) {
      seqLeft = gear > 0 ? gear : 1;
      seqAct = cfg[PI_a_gdn];
      seqNext = tnow;
      st = ST_SHIFTR;
      return;
    }
    tap(cfg[PI_a_gr]);
    rev = true; gear = 0; st = ST_REV;
  }

  void settle(int state) {
    uint32_t need = (uint32_t)cfg[PI_settle_ms];
    if (!inNz) { inNz = true; nzT = tnow; }
    else if (tnow - nzT >= need) { st = state; inNz = false; }
  }

  void drive() {
    int t = thr;
    gas = 0; brk = 0;
    if (!cfg[PI_rev_logic]) {
      gas = t > 0 ? t : 0; brk = t < 0 ? -t : 0;
      if (t > 0) st = ST_FWD; else if (t < 0) st = ST_BRK_F; else st = ST_NEUTRAL;
      return;
    }
    int bt = cfg[PI_brk_th], z = cfg[PI_nz];
    switch (st) {
      case ST_NEUTRAL:
        if (t > bt) { enterFwd(); gas = t; }
        else if (t < -bt) { enterRev(); gas = -t; }
        break;
      case ST_FWD:
        if (t < -bt) { st = ST_BRK_F; brkT = tnow; inNz = false; brk = -t; }
        else gas = t > 0 ? t : 0;
        break;
      case ST_BRK_F:
        if (t > z) { st = ST_FWD; inNz = false; gas = t; }
        else if (t < -z) {
          brk = -t; inNz = false;
          int ra = cfg[PI_rev_auto_ms];
          if (ra > 0 && tnow - brkT >= (uint32_t)ra) { enterRev(); if (st == ST_REV) { brk = 0; gas = -t; } }
        } else settle(ST_NEUTRAL);
        break;
      case ST_REV:
        if (t > bt) { st = ST_BRK_R; brkT = tnow; inNz = false; brk = t; }
        else {
          gas = t < 0 ? -t : 0;
          if (abs(t) <= z) settle(ST_NEUTRAL); else inNz = false;
        }
        break;
      case ST_SHIFTR: {
        brk = t < -z ? -t : 0;   // rem tetap ditahan selama pindah ke R
        if (seqLeft > 0 && (int32_t)(tnow - seqNext) >= 0) {
          tap(seqAct);
          seqLeft--;
          if (gear > 0) gear--;
          uint32_t d = (uint32_t)cfg[PI_seq_delay_ms];
          seqNext = tnow + (seqLeft > 0 ? d : (d < 300 ? d : 300));
        } else if (seqLeft == 0 && (int32_t)(tnow - seqNext) >= 0) {
          gear = 0; rev = true; inNz = false;
          if (t < -bt) { st = ST_REV; brk = 0; gas = -t; } else st = ST_NEUTRAL;
        }
        break;
      }
      case ST_BRK_R:
        if (t < -z) { st = ST_REV; inNz = false; gas = -t; }
        else if (t > z) {
          brk = t; inNz = false;
          int fa2 = cfg[PI_fwd_auto_ms];
          if (fa2 > 0 && tnow - brkT >= (uint32_t)fa2) { enterFwd(); brk = 0; gas = t; }
        } else settle(ST_NEUTRAL);
        break;
    }
  }

  // Mode "lepas-gas": gas ditahan, dilepas ke netral, lalu digas lagi = naik satu gigi.
  void pump() {
    if (st != ST_FWD) { pHeld = false; pArmed = false; return; }
    int bt = cfg[PI_brk_th], z = cfg[PI_nz];
    bool pulling = thr > bt, released = abs(thr) <= z;
    if (pulling) {
      if (!pHeld) {
        pHeld = true; pHeldT = tnow;
        if (pArmed) {
          uint32_t rel = tnow - pRelT;
          if (rel >= (uint32_t)cfg[PI_pump_rel_ms] && rel <= (uint32_t)cfg[PI_pump_win_ms] &&
              gear >= 1 && gear < cfg[PI_g_max] && !lock)
            shiftTo(gear + 1);
          pArmed = false;
        }
      }
    } else if (released) {
      if (pHeld) {
        pHeld = false;
        if (tnow - pHeldT >= (uint32_t)cfg[PI_pump_hold_ms]) { pArmed = true; pRelT = tnow; } else pArmed = false;
      }
    }
  }

  void autoGear() {
    if (cfg[PI_gear_mode] == 3) { pump(); return; }
    if (cfg[PI_gear_mode] != 1 || st != ST_FWD) return;
    if (tnow - lastShift < (uint32_t)cfg[PI_g_dwell]) return;
    int gmax = cfg[PI_g_max];
    if (gear == 0) { if (gas >= T(1)) engageFirst(false); }
    else if (gear < gmax && gas >= T(gear + 1) && !lock) shiftTo(gear + 1);
    else if (gear > 1 && gas < T(gear) - cfg[PI_g_hyst]) shiftTo(gear - 1);
  }

  // Sigma-delta: tombol ditekan/dilepas merata per slot waktu, rata-rata sesuai persen. Lebih halus dari satu blok per periode.
  bool sd(int i, int pct, bool pwm) {
    if (pct < cfg[PI_kb_dz]) { sdAcc[i] = 0; sdOut[i] = false; return false; }
    if (!pwm || pct >= 95) { sdAcc[i] = 0; sdOut[i] = true; return true; }
    uint32_t slot = tnow / (uint32_t)cfg[PI_kb_slot];
    if (slot != sdSlot[i]) {
      sdSlot[i] = slot;
      sdAcc[i] += pct;
      if (sdAcc[i] >= 100) { sdAcc[i] -= 100; sdOut[i] = true; } else sdOut[i] = false;
    }
    return sdOut[i];
  }
  void kbSet(int i, bool want, int code) {
    if (want && !kbOn[i]) { kbOn[i] = true; kbAct[i] = makeAct(AT_KEY, code); inc(kbAct[i]); }
    else if (!want && kbOn[i]) { kbOn[i] = false; dec(kbAct[i]); }
  }

  void emit() {
    int om = cfg[PI_out_mode];
    if (om == 0) {
      for (int i = 0; i < 4; i++) kbSet(i, false, 0);
      sink.axes(steer, gas, brk);
      return;
    }
    sink.axes(0, 0, 0);
    if (om == 1) {
      kbSet(0, steer < 0 && sd(0, -steer, cfg[PI_kb_pwm]), cfg[PI_k_left]);
      kbSet(1, steer > 0 && sd(1, steer, cfg[PI_kb_pwm]), cfg[PI_k_right]);
    } else {
      kbSet(0, false, 0); kbSet(1, false, 0);
      if (tnow - mouseT >= 8) {
        mouseT = tnow;
        mouseAcc += steer * cfg[PI_m_speed];
        int dx = mouseAcc / 100;
        mouseAcc -= dx * 100;
        if (dx) sink.mouse(dx);
      }
    }
    kbSet(2, gas > 0 && sd(2, gas, cfg[PI_kb_pwm_gas]), cfg[PI_k_fwd]);
    kbSet(3, brk > 0 && sd(3, brk, cfg[PI_kb_pwm_gas]), cfg[PI_k_back]);
  }
};


// ---------- LED RGB ----------
struct Rgb { uint8_t r, g, b; };

inline Rgb hsv2rgb(float h, float s, float v) {
  h = fmodf(h, 360.f); if (h < 0) h += 360.f;
  float c = v * s, x = c * (1 - fabsf(fmodf(h / 60.f, 2.f) - 1)), m = v - c, r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; } else if (h < 120) { r = x; g = c; } else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; } else if (h < 300) { r = x; b = c; } else { r = c; b = x; }
  return Rgb{(uint8_t)lroundf((r + m) * 255), (uint8_t)lroundf((g + m) * 255), (uint8_t)lroundf((b + m) * 255)};
}

// mode: 0 mati, 1 status, 2 warna tetap, 3 pelangi, 4 napas
inline Rgb ledColor(const Config& c, uint32_t now, bool sig, int st, int gas, bool rev) {
  if (!c[PI_led_en] || c[PI_led_mode] == 0) return Rgb{0, 0, 0};
  float k = c[PI_led_bright] / 100.f;
  float spd = c[PI_led_speed];
  Rgb o{0, 0, 0};
  switch (c[PI_led_mode]) {
    case 1:
      if (!sig) { o = ((now / 400) & 1) ? Rgb{255, 0, 0} : Rgb{40, 0, 0}; }
      else if (st == ST_BRK_F || st == ST_BRK_R) o = Rgb{255, 0, 0};
      else if (st == ST_REV || rev) o = Rgb{255, 140, 0};
      else if (st == ST_FWD) { float f = 0.35f + 0.65f * (gas > 100 ? 1.f : gas / 100.f); o = Rgb{0, (uint8_t)(255 * f), (uint8_t)(60 * f)}; }
      else o = Rgb{0, 80, 255};
      break;
    case 2: o = Rgb{(uint8_t)c[PI_led_r], (uint8_t)c[PI_led_g], (uint8_t)c[PI_led_b]}; break;
    case 3: o = hsv2rgb((float)((now * (uint32_t)spd) / 20 % 360), 1.f, 1.f); break;
    case 4: {
      float ph = (float)(now % 4000) / 4000.f * spd * 0.6f;
      float br = 0.5f + 0.5f * sinf(ph * 6.2831853f);
      o = Rgb{(uint8_t)(c[PI_led_r] * br), (uint8_t)(c[PI_led_g] * br), (uint8_t)(c[PI_led_b] * br)};
      break;
    }
  }
  return Rgb{(uint8_t)(o.r * k), (uint8_t)(o.g * k), (uint8_t)(o.b * k)};
}

// ---------- Protokol baris teks ----------
struct Host {
  virtual void write(const char* s) = 0;
  virtual void save() = 0;
  virtual void bootloader() = 0;
  virtual void wifiSet(const char* ssid, const char* pass) { (void)ssid; (void)pass; }
  virtual void wifiClear() {}
  virtual void wifiInfo(char* buf, size_t cap) { snprintf(buf, cap, "W 0 - -"); }
  virtual void reboot() {}
  virtual ~Host() {}
};

#ifndef RFC_FW_VERSION
#define RFC_FW_VERSION "1.0.0"
#endif

inline void handleLine(char* line, Config& cfg, Engine& eng, Host& h, bool& live) {
  while (*line == ' ') line++;
  size_t n = strlen(line);
  while (n && (line[n - 1] == '\r' || line[n - 1] == '\n' || line[n - 1] == ' ')) line[--n] = 0;
  if (!n) return;
  char* arg = strchr(line, ' ');
  if (arg) { *arg++ = 0; while (*arg == ' ') arg++; }
  char buf[80];
  if (!strcmp(line, "PING")) {
    snprintf(buf, sizeof(buf), "PONG RFC %s %d\n", RFC_FW_VERSION, (int)PI_COUNT);
    h.write(buf);
  } else if (!strcmp(line, "GET")) {
    for (int i = 0; i < PI_COUNT; i++) {
      snprintf(buf, sizeof(buf), "P %s %ld\n", PARAMS[i].name, (long)cfg.v[i]);
      h.write(buf);
    }
    h.write("END\n");
  } else if (!strcmp(line, "SET") && arg) {
    char* val = strchr(arg, ' ');
    if (!val) { h.write("ERR\n"); return; }
    *val++ = 0;
    h.write(cfg.set(arg, strtol(val, nullptr, 10)) ? "OK\n" : "ERR\n");
  } else if (!strcmp(line, "SAVE")) {
    h.save(); h.write("OK\n");
  } else if (!strcmp(line, "RESET")) {
    cfg.defaults(); h.save(); h.write("OK\n");
  } else if (!strcmp(line, "LIVE")) {
    live = arg && atoi(arg) != 0; h.write("OK\n");
  } else if (!strcmp(line, "TEST") && arg) {
    eng.testAct(atoi(arg)); h.write("OK\n");
  } else if (!strcmp(line, "SYS") && arg) {
    eng.doSys(atoi(arg)); h.write("OK\n");
  } else if (!strcmp(line, "BOOTLOADER")) {
    h.write("OK\n"); h.bootloader();
  } else if (!strcmp(line, "WIFISSID") && arg) {
    h.wifiSet(arg, nullptr); h.write("OK\n");
  } else if (!strcmp(line, "WIFIPASS")) {
    h.wifiSet(nullptr, arg ? arg : ""); h.write("OK\n");
  } else if (!strcmp(line, "WIFICLEAR")) {
    h.wifiClear(); h.write("OK\n");
  } else if (!strcmp(line, "WIFIINFO")) {
    char wb[120]; h.wifiInfo(wb, sizeof(wb)); h.write(wb); h.write("\n");
  } else if (!strcmp(line, "REBOOT")) {
    h.write("OK\n"); h.reboot();
  } else {
    h.write("ERR\n");
  }
}

}  // namespace rfc
