# Cekin_plagiat

# Plagiarism Checker & Document Similarity System

Sistem pengecekan kemiripan dokumen berbasis web yang terinspirasi dari fungsionalitas Turnitin. Aplikasi ini dirancang menggunakan antarmuka interaktif Python Streamlit dan performa kueri berkecepatan tinggi dengan ClickHouse.

## Fitur Utama
* **Mode "No Repository":** Pengecekan draf dokumen tanpa menyimpan isi teks secara permanen ke dalam database, menjaga kerahasiaan dokumen pengguna.
* **Filter Khusus:** 
  * *Exclude Quotes* (Abaikan Kutipan)
  * *Exclude Bibliography* (Abaikan Daftar Pustaka)
* **Laporan Integritas (Integrity Overview):** Menampilkan metrik persentase kemiripan dan jumlah kata yang diproses.
* **Pratinjau Dokumen Interaktif:** Sorotan teks bermasalah lengkap dengan fitur *tooltip* berbasis CSS yang menampilkan sumber referensi saat kursor diarahkan.

## Teknologi yang Digunakan
* **Frontend/UI:** [Streamlit](https://streamlit.io/)
* **Database & Pencarian:** [ClickHouse](https://clickhouse.com/) via `clickhouse-connect`
* **Pemrosesan Dokumen:** `PyPDF2`
* **Deployment:** Streamlit Community Cloud & GitHub

## Panduan Konfigurasi Cepat

1. **Clone repositori ini** ke komputer lokal Anda (jika ingin melakukan pengembangan lokal).
2. **Pastikan file-file berikut tersedia di dalam repositori:**
   * `app.py` (File utama aplikasi)
   * `requirements.txt` (Daftar dependensi pustaka Python)
   * `.gitignore` (Pengaman file rahasia)
   * `README.md` (Dokumentasi ini)
3. **Konfigurasi Keamanan (Streamlit Secrets):**
   Karena aplikasi ini terhubung ke ClickHouse, Anda harus mendaftarkan kredensial akses di menu **Secrets** Streamlit Cloud dengan format berikut:
   ```toml
   [clickhouse]
   host = "url-host-clickhouse-anda.com"
   port = 8443
   username = "default"
   password = "password-rahasia-anda"
   secure = true
