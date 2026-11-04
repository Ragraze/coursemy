# Coursemy

Katalog kursus untuk orang yang ingin memilih topik, memeriksa kupon, dan melanjutkan belajar. Pertanyaan utama layar: kursus apa yang sesuai dengan pencarian dan kategori saya?

Arah visual memakai Accent ladder dari Design Taste, seed 477850068. Ground putih hangat, teks arang, dan aksen oranye pada pilihan aktif. Cover kursus asli menjadi identitas visual utama. Tidak ada statistik, ulasan, atau kursus rekaan pada katalog kosong.

ENERGY 1 / RHYTHM 2 / MOTION 1.

- Warna oranye membedakan filter aktif, kupon, dan tindakan utama; permukaan tetap terang agar cover mudah dibandingkan.
- DM Sans dipilih untuk judul kursus panjang dan metadata kecil yang tetap terbaca; fallback memakai font sistem saat CDN tidak tersedia.
- Sidebar kategori menjaga 13 kategori terlihat pada desktop. Disclosure kategori menyingkat kontrol pada ponsel.
- Grid kartu dipakai karena objek yang dibandingkan mempunyai jenis informasi setara: cover, judul, instruktur, rating, durasi, bahasa, dan status.
- Gap 24px dan grid tiga kolom pada desktop menjaga cover dan baseline kartu sejajar; ponsel menggunakan satu kolom.
- SVG Lucide inline mengikuti prompt: bookmark menandai tindakan simpan, jam menandai durasi, globe menandai bahasa, dan bintang menyatakan rating dari upstream.
- Gerak dibatasi pada feedback kontrol. Loading memakai skeleton statis agar tidak mengganggu pembacaan; reduced motion dihormati.
- Tema tetap terang mengikuti brief katalog dan memungkinkan perbandingan cover konsisten. Tidak ada mode warna tambahan.

Belum ditinjau melalui screenshot browser karena runtime dan dependensi belum tersedia. Arah ini merupakan keputusan implementasi dari brief, belum merupakan persetujuan desain terpisah dari pemilik proyek.

## Landing page

Landing `/` memakai arah editorial-report (The printed annual), seed 36403285, dengan warna dan DM Sans dari identitas yang ada. Cover kursus asli menjadi mosaik masthead; judul dan pencarian mengikuti sumbu editorial. Pencarian GET adalah interaksi utama dan tetap bekerja tanpa JavaScript. Katalog berada di `/courses`; Swagger di `/api/docs`.

ENERGY 2 / RHYTHM 3 / MOTION 1. Gerak hanya pada pembukaan mosaik dan feedback hover, dengan dukungan reduced motion. Tidak ada statistik atau testimoni rekaan. Pilihan kursus memakai cache aktif dengan variasi instruktur, tanpa klaim verifikasi harga checkout.

Inspector allowances: `eyebrow` salah mendeteksi label kategori cover sebagai eyebrow hero; label tersebut menjelaskan kursus yang ditautkan. `still-page` disengaja karena desain membatasi gerak pada mosaik dan kontrol, tanpa video dekoratif yang tidak berhubungan dengan katalog. Garis formulir dan navigasi footer mengikuti komponen proyek.

## Navbar

Navbar mengikuti referensi bersamateknologiunggul.id yang diperiksa langsung pada 1 November 2026: kapsul mengambang dengan lebar maksimum 940px, permukaan gelap transparan, menu aktif membulat, dan tombol terang di kanan. Menu Coursemy tetap Home dan Courses; tombol Cari kursus membuka input pencarian katalog. Di ponsel, disclosure native menyediakan hamburger, mendukung Escape dan klik di luar untuk menutup, serta tetap berfungsi tanpa JavaScript. Permukaan transparan dan backdrop blur membantu keterbacaan navbar ketika konten bergulir di belakangnya. Tema halaman tetap mengikuti identitas Coursemy.

Navbar selalu terlihat saat halaman digulir. Jarak 16px di desktop dan 12px di ponsel memisahkan kapsul dari tepi atas, sementara posisi sticky menjaga navigasi tetap terjangkau. Reduced motion menonaktifkan transisi.

## Tema dan perilaku navbar terbaru

Navbar memakai permukaan kaca yang mengikuti tema (opacity 90%, blur 24px). Pemilih Light/Dark/System menggantikan tombol Cari kursus dan menyimpan pilihan di localStorage; System mengikuti perubahan preferensi perangkat. Tema diterapkan sebelum stylesheet dimuat untuk menghindari kilatan warna. Dark mode memetakan token permukaan, teks, border, dan aksen, termasuk katalog dan detail kursus.

Animasi pembukaan dan hover zoom hero dihapus. Konten teratas dirapatkan melalui pengurangan jarak setelah navbar serta padding judul katalog. Navbar tetap menempel di atas dan tidak lagi bersembunyi saat scroll. Gerakan tidak mengubah tinggi atau alur tata letak halaman.

Pemilih tema kini berupa tiga tombol ikon SVG (matahari, bulan, monitor) dengan aria-label, title, dan aria-pressed untuk pilihan aktif. Hero memakai min-height berdasarkan 100svh setelah area navbar, dengan tinggi mosaik dan ukuran judul adaptif. Layar kecil tetap dapat bertambah tinggi jika kontennya memerlukan ruang, tanpa memotong konten. Pemeriksaan browser pada 1440×900, 1366×768, 768×1024, 390×844, dan 320×640 memastikan pencarian terlihat serta tidak ada overflow halaman atau navbar.

Logo header terbaru memakai buku terbuka pada bidang oranye lembut (#D77B43), bersama nama Coursemy tanpa subtitle. Aset SVG yang sama dipakai pada favicon dan header bersama untuk beranda, katalog, dan detail kursus. Navbar kini bersembunyi saat scroll turun melewati area atas dan muncul saat scroll naik; ambang 8px meredam perubahan kecil. Menu mobile terbuka dan fokus keyboard menjaga navigasi terlihat. Reduced motion menonaktifkan transisi. Pemeriksaan browser beranda dan katalog pada lebar 1440, 390, dan 320px memastikan logo tampil, tata letak tidak overflow, serta perilaku scroll turun/naik berjalan.

Navbar terbaru mengikuti alur halaman dengan position relative: langsung ikut bergulir tanpa sticky, ambang scroll, atau animasi sembunyi. Perubahan ini menggantikan perilaku scroll navbar sebelumnya.
