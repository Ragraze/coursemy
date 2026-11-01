# Review tech stack

Ditinjau pada 29 Oktober 2026 sebelum implementasi.

## Keputusan

Stack Python pada prompt sesuai dengan katalog sekitar ribuan kursus. FastAPI dan Jinja2 memberi HTML yang langsung bisa dibuka; HTMX menangani pencarian dan pagination tanpa SPA. SQLAlchemy 2 dan Alembic memungkinkan penggunaan SQLite lokal dan PostgreSQL production dengan skema yang sama. Redis, Celery, dan framework frontend tambahan belum diperlukan.

| Komponen | Keputusan dan alasan |
| --- | --- |
| Python 3.12+ | Dipertahankan. Docker memakai Python 3.12. |
| FastAPI + Uvicorn | Dipertahankan. Resource HTTP dan scheduler dikelola melalui lifespan. |
| Jinja2 + HTMX + Alpine | Dipertahankan. Form GET dan tautan pagination tetap bekerja tanpa HTMX. Alpine menangani disclosure kategori pada viewport kecil. |
| Tailwind CLI standalone | Dipertahankan, v4.1.17. Sumber CSS dan script build disertakan tanpa project Node. |
| SQLAlchemy 2 + Alembic | Dipertahankan. Query ORM sinkron digunakan untuk operasi database kecil; HTTP upstream tetap asynchronous. |
| Pydantic v2 | Dipertahankan. Validasi data upstream dan response API memakai schema bertipe. |
| httpx AsyncClient | Dipertahankan. Timeout 15 detik per request, maksimal dua retry untuk transport error, 429, dan 5xx. |
| Pillow | Dipertahankan. JPEG lokal 640×360, batas ukuran unduhan dan dimensi, fallback placeholder. |
| APScheduler | Gunakan seri 3.x karena prompt meminta `BackgroundScheduler`. Scheduler embedded hanya dijalankan pada satu proses. |
| Gunicorn worker | Gunakan paket `uvicorn-worker` dan kelas `uvicorn_worker.UvicornWorker`; path `uvicorn.workers` di prompt sudah deprecated. |
| pytest + httpx | Dipertahankan. Respons upstream dan unduhan gambar ditiru secara deterministik di test. |

Dokumentasi resmi: [lifespan FastAPI](https://fastapi.tiangolo.com/advanced/events/), [deployment Uvicorn](https://www.uvicorn.org/deployment/), [batas multiprocess APScheduler](https://apscheduler.readthedocs.io/en/3.x/faq.html#how-do-i-share-a-single-job-store-among-one-or-more-worker-processes), [Tailwind CLI](https://tailwindcss.com/docs/installation/tailwind-cli).

## Konflik dan kekosongan prompt

1. **Refresh penuh dan halaman pertama mempunyai kontrak berbeda.** Startup dan scheduler melakukan crawl penuh. Endpoint manual default mengambil halaman pertama; `?full=true` memilih crawl penuh. `refreshedAt` dan `fullRefreshedAt` dipisahkan agar refresh halaman pertama tidak tampak sebagai sinkronisasi penuh.
2. **Kategori harus mempunyai kupon tetapi list tidak mempunyai detail.** Pemilihan kategori mengisi cache dari endpoint detail kategori terlebih dahulu. Setelahnya search, sorting, dan pagination tetap dijalankan di SQL lokal.
3. **SavedCourse belum mempunyai pemilik.** Ditambahkan `visitor_id` dan unique constraint pasangan visitor/kursus. Tanpa ini, seluruh pengunjung akan berbagi bookmark.
4. **Refresh tanpa token.** Tombol refresh dan endpoint sinkronisasi manual dapat dipakai tanpa autentikasi. Pengunci database tetap mencegah sinkronisasi berjalan bersamaan.
5. **Urutan kategori tidak disertakan.** Prompt menyebut `listCategories` tetapi tidak memberikan nilainya. Implementasi memakai 13 kategori standar Udemy sebagai asumsi yang belum diverifikasi. Endpoint kategori upstream yang tidak lengkap tidak dipakai sebagai sumber daftar filter.
6. **Katalog tidak boleh menunggu seluruh unduhan.** Startup memulai background task dan commit dilakukan per halaman. Kegagalan upstream meninggalkan katalog tersimpan tetap dapat dibaca.

## Batas operasional

- Sinkronisasi penuh dan cache kategori dapat berlangsung lama karena data dan cover berasal dari jaringan. Batas koneksi dan unduhan gambar dibatasi, namun waktu total tetap mengikuti upstream.
- Storage lokal membutuhkan volume persisten. Worker pada beberapa mesin harus berbagi file cover atau memakai storage terpusat sebelum scaling horizontal.
- SQLite dipakai untuk development. PostgreSQL adalah pilihan production yang disertakan pada Compose.
- Tidak ada autentikasi akun pengguna, verifikasi harga Udemy, atau klaim bahwa kupon masih berlaku saat checkout. Ketersediaan kupon mengikuti upstream dan Udemy.
- Integrasi produksi memakai VPS/Docker/Railway/Render sesuai prompt. Runtime hosting Sites berbasis Cloudflare Workers tidak sesuai untuk aplikasi FastAPI Python dan volume file lokal ini.

## Status lingkungan pengerjaan

Python sistem tersedia sebagai `python3` versi 3.13.5. Modul pip dan ensurepip tidak tersedia, pembuatan venv gagal, dan DNS terminal tidak dapat mengakses upstream. Peramban web dapat membaca halaman katalog, tetapi endpoint JSON tidak dapat diakses. Karena itu versi dependensi terpasang, kontrak JSON live, dan urutan `listCategories` belum dapat dikonfirmasi di lingkungan ini.
