// Simulator firmware untuk tes integrasi: baca perintah dari stdin, tulis balasan ke stdout.
#include "../src/rfc_logic.h"
#include <iostream>
#include <string>
using namespace rfc;
struct NullSink : Sink { void press(int) override {} void release(int) override {} void axes(int, int, int) override {} void mouse(int) override {} };
struct H : Host { void write(const char* s) override { fputs(s, stdout); fflush(stdout); } void save() override {} void bootloader() override {} };
int main() {
  Config cfg; NullSink s; Engine e(cfg, s); H h; bool live = false;
  uint16_t pw[4] = {1500, 1700, 900, 900}; uint32_t t = 1000;
  std::string line;
  while (std::getline(std::cin, line)) {
    std::vector<char> b(line.begin(), line.end()); b.push_back(0);
    handleLine(b.data(), cfg, e, h, live);
    for (int i = 0; i < 50; i++) e.update(t += 5, pw, true);
    if (live) { char buf[128]; e.liveLine(buf, sizeof(buf), pw, true); fputs(buf, stdout); fflush(stdout); }
  }
}
