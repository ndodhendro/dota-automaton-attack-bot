# Automaton Attack Bot

Bot untuk mini-game **Automaton Attack** di event Dota 2 Dark Carnival. Bot memotret papan permainan, membaca label yang jatuh ke arah Hoodwink, lalu mengetiknya.

Ini proyek iseng di komputer sendiri. Bot tidak menyuntik proses Dota. Tetap ada risiko akun, karena otomatisasi bisa melanggar aturan Valve.

## Cara mini-gamenya

Satu ronde berjalan 1 menit. Label berisi nama hero, item, atau ability Dota jatuh menuju Hoodwink. Ketik label itu sebelum kena. Beberapa label bisa muncul bersamaan.

- Spasi dan tanda baca tidak perlu diketik. `Anti-Mage` diketik `antimage`, `Ring of Protection` diketik `ringofprotection`.
- Huruf kecil diterima.
- Label yang lolos menghapus multiplier. Rangkaian yang tidak putus menaikkan skor.
- Label yang lebih panjang memberi lebih banyak poin. Skor di screenshot kamu (225, multiplier x2.0, high score 2.555) mengikuti aturan ini. Ambang hadiah yang umum dipakai event: 1.000 dan 2.500.

Urutan ketik bot:

1. Label yang sudah rendah di layar diketik dulu, supaya kombo tidak putus.
2. Label yang masih aman diketik dari yang paling pendek, supaya multiplier naik sebelum label panjang dihabisi.

## Menjalankan

Perlu Windows dan Python 3.12. Dota borderless atau fullscreen di monitor utama.

Klik dua kali `run.bat`, atau:

```bat
cd /d C:\Ndod\Softwares\Tools\dota-automaton-attack-bot
run.bat
```

Pertama kali bot mengunduh model OCR (sekitar 10–20 MB).

1. Buka Automaton Attack.
2. Tekan **F7** untuk preview. Label yang terbaca punya kotak kuning.
3. Kalau kotaknya meleset, tekan **F9**, tarik area papan mini-game, lalu Enter.
4. Klik jendela Dota, mulai ronde, tekan **F8**.

| Tombol | Fungsi |
| --- | --- |
| F8 | Mulai atau berhenti mengetik |
| F7 | Preview deteksi, tanpa mengetik |
| F9 | Kalibrasi area layar |
| F10 | Simpan gambar debug ke folder `debug` |
| End | Keluar |
| Mouse ke pojok kiri-atas | Berhenti darurat |

Jangan klik jendela console saat bot sedang mengetik. Klik di console Windows bisa membekukan proses, dan ketikan akan masuk ke console, bukan ke Dota.

Area default diambil dari screenshot 1920x1080 yang kamu kirim: papan kira-kira dari 24,6% sampai 75,8% lebar layar, dan 4,9% sampai 95,0% tinggi layar. Resolusi atau UI scale lain perlu kalibrasi sekali. Hasilnya tersimpan di `config.json`.

## Kalau hasilnya kurang

`config.json`:

| Kunci | Default | Kegunaan |
| --- | --- | --- |
| `key_hold_ms` | 6 | Lama tombol ditekan |
| `key_interval_ms` | 8 | Jeda antarhuruf |
| `inter_word_ms` | 20 | Jeda antarlabel |
| `retries` | 1 | Ketik ulang sekali kalau label masih ada |
| `danger_y_ratio` | 0.58 | Batas "hampir kena" dari atas area |
| `raw_confidence` | 0.80 | Ambang OCR untuk kata di luar kamus |
| `min_confidence` | 0.40 | Ambang minimum, termasuk kata kamus |

Kalau huruf ada yang tertelan, naikkan `key_interval_ms` ke 12 atau 16. Kalau terasa lambat dan tidak ada huruf yang hilang, turunkan ke 4.

Kata yang sering salah baca bisa ditambah di `automaton_bot/lexicon.txt`, satu label per baris, ditulis seperti di Dota. Bot tetap mengetik kata di luar kamus kalau OCR-nya yakin.

Cek apa yang dilihat bot tanpa mengetik:

```bat
.venv\Scripts\python.exe -m automaton_bot --test-image "C:\path\screenshot.png"
.venv\Scripts\python.exe -m automaton_bot --self-test
```

Kalau Dota dijalankan sebagai administrator, bot juga harus dijalankan sebagai administrator. Kalau tidak, Windows memblokir ketikannya.

## Yang sengaja tidak dilakukan

Bot tidak membaca memori Dota, tidak mengubah kecepatan game, dan tidak menekan pause. Skor tinggi datang dari membaca label dan mengetiknya lebih cepat daripada tangan, sambil menjaga kombo.
