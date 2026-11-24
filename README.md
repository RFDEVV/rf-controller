# RF CONTROL

Remot RC 4 channel (GA-4H-TX / receiver GA-4H-RX) jadi controller game lewat ESP32-S3.
Otaknya di firmware ESP32 (delay kecil). Aplikasi Windows hanya untuk setting dan monitor,
seperti software mouse gaming.

```
Remot -> receiver GA-4H-RX -> ESP32-S3 -> USB HID (gamepad / keyboard / mouse) -> game
                                  ^
                                  |  setting dan monitor: kabel USB, WiFi serumah, atau Bluetooth LE
                          Aplikasi Windows
```

## Isi repo

| Folder | Isi |
|---|---|
| `firmware/` | Firmware ESP32-S3 (PlatformIO, Arduino-ESP32 3.x). Logika inti ada di `src/rfc_logic.h` dan diuji di PC |
| `app/` | Aplikasi Windows (Python + PySide6), UI terang/gelap, splash dan animasi |
| `tools/make_icon.py` | Pembuat ikon aplikasi |
| `.github/workflows/build.yml` | Build otomatis: tes, firmware, lalu satu file `RFController.exe` |

## Wiring

| Receiver GA-4H-RX | ESP32-S3 | Fungsi |
|---|---|---|
| CH1 sinyal (S) | GPIO4 | Setir (roda samping) |
| CH2 sinyal (S) | GPIO5 | Gas dan rem (trigger) |
| CH3 sinyal (S) | GPIO6 | Tombol CH3 |
| CH4 sinyal (S) | GPIO7 | Tombol CH4 |
| Pin + (V+) salah satu channel | 3V3 | Daya receiver 3,3 V |
| Pin - (GND) salah satu channel | GND | Ground bersama |
| OLED SDA | GPIO1 | Data I2C layar |
| OLED SCL | GPIO2 | Clock I2C layar |
| OLED VCC / GND | 3V3 / GND | Daya layar 3,3 V (alamat I2C 0x3C) |
| Port USB-C berlabel **USB** | Kabel ke PC | Input game dan setting |
| Port USB-C berlabel **UART** | Kabel ke PC (opsional) | Flash dan log |

Catatan penting:

- Pakai **3V3**, bukan 5V. Dengan daya 3,3 V sinyal receiver juga 3,3 V, aman untuk GPIO ESP32. Receiver boleh 3,3 sampai 6 V, jangan lebih dari 6 V.
- Urutan pin receiver umumnya S, +, -. Cocokkan dengan tanda yang tercetak di receiver sebelum menyambung.
- Jangan sambungkan receiver ke ESC atau servo sekaligus, supaya tidak ada dua sumber daya.
- Hindari GPIO19 dan GPIO20 (USB), GPIO0, 3, 45, 46 (boot), GPIO26 sampai 32 (flash), GPIO33 sampai 37 (PSRAM pada tipe N8R8/N16R8). GPIO48 (atau 38) dipakai LED RGB.
- Pin channel bisa diubah lewat `-DPIN_CH1=..` di `platformio.ini`.
- Binding remot: tekan tombol SW di receiver sampai LED berkedip cepat, lalu nyalakan remot.

Halaman **Wiring** di aplikasi menampilkan diagram yang sama.

## Memasang firmware

Otomatis dari aplikasi: halaman **Firmware**, pilih port, tekan **Flash firmware bawaan**.
Manual: tahan BOOT, tekan RESET, lepas BOOT, lalu flash `rf-controller-merged.bin` di alamat `0x0`
(misalnya dengan `esptool --chip esp32s3 write_flash 0x0 rf-controller-merged.bin`).

Atau build sendiri: `cd firmware && pio run`. `platformio.ini` memakai pioarduino 54.03.21-2 (Arduino-ESP32 3.2.1) karena build dengan rilis 3.3.x gagal di `USBHostMSC/FS.h`.

## Fitur

- **Output**: gamepad, keyboard, atau mouse. Pengiriman USB berjalan di task sendiri dan diulang bila gagal, jadi loop utama tidak tersendat. Di mode keyboard, setir halus memakai kedip merata (sigma-delta), gas dan rem ditahan terus.
- **Deteksi pulsa**: monitor semua channel (sekarang, terendah, tertinggi, rata-rata, goyangan, status), wizard deteksi otomatis (rekam diam lalu gerak penuh, hitung tengah, rentang, pita netral, zona mati, ambang tombol), dan rentang kustom per channel: min/tengah/maks, pita netral (µs), penghalus, histeresis tombol, jendela pulsa sah, batas sinyal hilang.
- **OLED** (SSD1306/SH1106, I2C): halaman status (gigi, mode, koneksi), bar, dan pulsa; otomatis bergantian atau dikunci; kecerahan, putar 180°, pin SDA/SCL. Aksi sistem "Ganti halaman OLED" bisa dipasang ke tombol remot.
- **Tombol dan gestur**: CH3 (pulsa bergantian tiap tekan) dan CH4 (momentary) bisa diatur untuk klik 1x, 2x, 3x, dan tahan lama (CH4). Tiap gestur bisa menekan tombol keyboard, tombol gamepad, klik mouse, atau aksi sistem.
- **Aturan pulsa**: 6 aturan, aksi aktif selama pulsa channel berada di rentang tertentu.
- **Gigi**, tiga mode selain mati:
  - **Lepas-gas** (bawaan): gas ditahan, dilepas ke netral, digas lagi = naik satu gigi. Saat gigi masih R atau netral, tarik trigger maju otomatis naik ke gigi 1.
  - **Ambang gas**: gigi naik dan turun mengikuti persentase gas, dengan histeresis dan jeda.
  - **Manual**: lewat aksi Naik/Turun gigi di tombol CH3 atau CH4.
  - Kunci gigi, tombol naik/turun atau tombol langsung per gigi.
- **Rem dan mundur**: trigger didorong saat melaju = rem. Setelah netral lalu didorong lagi, atau rem ditahan 1 detik (bisa diatur), ESP32 menekan **Turun gigi sebanyak gigi sekarang** (gigi 5 = 5 klik, jeda 500 ms) sampai gigi R, lalu mobil mundur. Dari R, trigger ditarik maju = otomatis naik ke gigi 1.
- **CH3 dan CH4**: polaritas pulsa dipelajari otomatis dari pulsa awal, jadi 975 ke 1965 maupun 1965 ke 975 sama-sama terbaca. Tiga jenis per channel: *Ditahan* (klik dihitung saat dilepas, ada tahan lama), *Klik per tekan*, dan *Bergantian* (setiap perubahan pulsa dihitung satu klik, cocok untuk tombol nyala-mati yang posisinya tidak tentu). Klik 1x, 2x, 3x bisa diatur untuk masing-masing.
- **Diagnosa tombol**: halaman Tombol menampilkan gestur terakhir yang terbaca ESP32, dan tombol Tes di samping tiap aksi mengirim tombolnya ke PC tanpa remot.
- **LED RGB board**: mati, status (merah/hijau/kuning/biru sesuai kondisi), warna, pelangi, napas; kecerahan, kecepatan, pilihan pin. Berjalan bersamaan dengan OLED.
- **Koneksi**: kabel USB (utama), WiFi serumah (TCP 8266, `rfcontroller.local`), Bluetooth LE (Nordic UART).
- **Profil**: simpan per game, impor/ekspor, preset.
- Failsafe: semua tombol dilepas jika sinyal remot hilang.

## Koneksi WiFi dan Bluetooth

1. Hubungkan lewat USB. Buka **Koneksi**, aktifkan WiFi dan/atau Bluetooth, isi nama dan sandi WiFi, **Kirim ke ESP32**.
2. Tekan **Simpan dan mulai ulang ESP32**.
3. Hubungkan lewat WiFi (alamat `rfcontroller.local` atau IP yang ditampilkan) atau cari perangkat Bluetooth "RF Controller".

Keterbatasan:

- WiFi dan Bluetooth hanya untuk setting dan monitor. Input game selalu lewat USB.
- Saat WiFi atau Bluetooth aktif, siapa pun di jaringan atau jangkauan itu bisa mengubah setting (belum ada sandi). Matikan jika tidak dipakai.
- Setting lewat WiFi/Bluetooth menambah sedikit delay pada monitor, tidak pada input game.

## Catatan kompatibilitas

- Gamepad yang tampil adalah HID generik. Sebagian game PC hanya mengenali gamepad gaya Xbox (XInput). Kalau begitu pakai mode keyboard.
- Game yang tidak mendukung stik analog bisa memakai mode keyboard halus.

## Menjalankan aplikasi dari sumber

```
cd app
pip install -r requirements.txt
python main.py
```

Tidak punya perangkat? Buka **Koneksi** lalu **Coba mode demo**.

## Tes

```
g++ -std=c++17 -fsanitize=address,undefined -o test_logic firmware/test/test_logic.cpp && ./test_logic
cd app && QT_QPA_PLATFORM=offscreen python tests/test_ui.py
```

## Status pengujian

Sudah diuji: logika firmware (gigi, rem/mundur, gestur, keyboard, LED, protokol) di PC; aplikasi (UI, semua halaman, tema,
mode demo) tanpa layar; komunikasi aplikasi ke logika firmware lewat TCP.
Belum diuji di perangkat asli: build firmware di PlatformIO (kodenya baru diperiksa sintaksnya dengan stub, bukan library asli), USB HID, WiFi, Bluetooth, OLED, flash dari aplikasi, dan
pembacaan pulsa. Kalau build CI melaporkan error, kirim lognya.
