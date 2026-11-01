# Status verifikasi

Pemeriksaan pada 29 Oktober 2026. Implementasi belum dinyatakan siap production karena dependensi runtime belum dapat dipasang di lingkungan pengerjaan.

| Pemeriksaan | Hasil dan bukti |
| --- | --- |
| Sintaks Python | PASS: `python3 -m compileall -q app alembic scripts tests`. |
| Sintaks JavaScript | PASS: `node --check app/static/js/main.js`. |
| Kupon dan URL enroll | PASS: 13 assert stdlib terhadap ekstraksi, URL tanpa kupon, encoding, domain palsu, HTTP, kredensial URL, port asing, URL malformed, dan batas panjang kode. |
| Flatten detail dan teks HTML | PASS: 5 pemeriksaan terisolasi terhadap fungsi asli `TextParser`, `plain_text`, dan `flatten_text`, dimuat melalui AST agar tidak memerlukan dependensi eksternal. |
| Metadata project | PASS: `pyproject.toml` dibaca dengan `tomllib`; constraint Python 3.12+ diperiksa. |
| Design source lint | PASS tanpa FAIL. Warning label kupon adalah penjelasan sumber kode; shadow hanya dipakai pada toast dan dialog yang mengambang. |
| pytest | BELUM BERJALAN: `python3 -m pytest -q` gagal karena modul pytest belum tersedia. |
| Pemasangan dependensi | TERHALANG: Python sistem tidak menyediakan pip/ensurepip. `python3 -m venv .venv` gagal. |
| Build Tailwind standalone | TERHALANG: unduhan GitHub gagal dengan `Temporary failure in name resolution`. Stylesheet bootstrap disertakan; CSS Tailwind final belum dihasilkan. |
| Integrasi upstream live | TERHALANG: DNS terminal gagal. Endpoint JSON juga tidak dapat dibaca melalui alat web. Bentuk respons dan urutan kategori belum diverifikasi live. |
| Jalankan Uvicorn dan migrasi | TERHALANG: `python3 -m uvicorn app.main:app` gagal karena modul Uvicorn tidak tersedia; migrasi menunggu dependensi. |
| Browser desktop/mobile | BELUM DIUJI: runtime belum tersedia; tidak ada klaim console bersih atau bebas overflow berdasarkan browser. |
| Konfigurasi Compose | PASS: `docker compose config --quiet` berhasil. |
| Docker / PostgreSQL | TERHALANG: akses API Docker pada `/var/run/docker.sock` ditolak. Container belum dibangun/dijalankan. |

## Pemeriksaan desain

- Hard gate: belum lengkap. Loading, empty state, error state, fallback gambar, label, focus state, native dialog, dan ukuran gambar tersedia di sumber; click-through, kontras hasil render, dan overflow belum diverifikasi di browser.
- Purpose gate: alasan warna, font, kartu, ikon, dan spacing tertulis di `DESIGN.md`. Tidak ada gradient atau statistik rekaan.
- Liveliness: ENERGY 1 / RHYTHM 2 / MOTION 1 tercatat. Cover kursus asli adalah fokus; katalog kosong menampilkan keadaan kosong.
- Craftsmanship: belum lengkap sampai runtime, test suite, dan browser QA berhasil.

Tidak ada laporan PASS untuk keseluruhan aplikasi. Jalankan langkah README dan `pytest -q`, lalu uji pencarian, kategori, sort, switch jenis kursus, hide expired, pagination, bookmark, copy coupon, enroll, refresh, serta tampilan 390/768/1440px sebelum deployment.
