# Menjalankan Sistem

## Cara cepat

```bash
./run.sh
```

Skrip ini mengurus semuanya secara berurutan: cek dependensi host, menyalakan
PostgreSQL, menyalakan Ollama dan mengunduh model bila belum ada, membuat
virtualenv Python 3.12 dan menginstall dependensi, lalu menjalankan backend dan
frontend. Aman dijalankan berulang kali — service yang sudah hidup dilewati.

| Perintah | Fungsi |
|---|---|
| `./run.sh` | Jalankan semua service |
| `./run.sh stop` | Hentikan backend, frontend, database |
| `./run.sh restart` | Stop lalu start |
| `./run.sh status` | Cek kondisi tiap service |
| `./run.sh logs` | Ikuti log backend |
| `./run.sh test` | Jalankan test backend |

Setelah jalan:

- Aplikasi: http://localhost:5173
- API docs: http://localhost:8001/docs

Log tersimpan di `.run/`. `./run.sh stop` tidak mematikan Ollama karena kemungkinan dipakai aplikasi lain.

---


## Langkah manual (bila tidak memakai run.sh)

### 1. Database

```bash
docker compose up -d postgres
```

Berjalan di **port 5433** (5432 sudah dipakai proyek lain di mesin ini).
Skema dan role read-only dibuat otomatis dari `backend/sql/init.sql`.

Cek:

```bash
docker exec agentic-rag-ai-db psql -U postgres -d agentic_rag -c '\dt'
```

### 2. Ollama

Model wajib mendukung **tool calling**. Yang sudah diuji di mesin ini:

| Model | Status |
|---|---|
| `qwen2.5:7b` | Dipakai. Tool calling andal. |
| `llama3:latest` | **Tidak bisa.** Ollama menolak: `does not support tools`. |
| `llama3.2:1b` | **Tidak bisa.** Mengirim skema JSON sebagai argumen tool, request menggantung. |

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

Ganti model cukup lewat `OLLAMA_LLM_MODEL` di `.env`, tanpa ubah kode.

### 3. Backend

Wajib **Python 3.12** (sisa dependensi mengikuti; `onnxruntime` juga paling stabil di sini).

```bash
cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8001
```

Port 8001 karena 8000 sudah dipakai proses lain di mesin ini.
Dokumentasi API: http://localhost:8001/docs

Test:

```bash
.venv/bin/python -m pytest tests -q
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

http://localhost:5173 — arahkan backend lewat `VITE_API_URL` di `frontend/.env`.

## Catatan

- Inference CPU: jawaban pertama lambat (model dimuat ke memori), berikutnya lebih cepat.
- **OCR memakai RapidOCR (`rapidocr-onnxruntime`), bukan PaddleOCR.** README meminta
  PaddleOCR, tapi `paddlepaddle` 2.6.2 menggantung tanpa batas di dalam inferensi pada
  macOS arm64 — terbukti bahkan pada gambar putih 64x192 (import 2.9 s dan init 0.6 s
  normal, `ocr()` tidak pernah selesai; bukan soal ukuran gambar, thread, atau unduhan
  model). RapidOCR menjalankan model PP-OCR yang sama di atas ONNX runtime arm64 native:
  hasil identik, 0.5 detik. Antarmuka tool `image_ocr` tidak berubah.
- OCR berjalan di **proses terpisah** (`ProcessPoolExecutor`, deadline 180 detik).
  Inferensi tidak melepas GIL, jadi menjalankannya di thread membekukan seluruh worker
  ASGI — `/health` pun ikut mati. Dengan proses terpisah, `/health` tetap balas ~0.07 detik
  saat OCR berjalan.

## Hasil Verifikasi

Diuji pada mesin ini (macOS arm64, CPU-only):

| Cek | Status |
|---|---|
| `GET /health` | OK |
| Upload TXT → chunking → embedding 768-dim → pgvector | OK, 1 chunk tersimpan |
| `GET /documents` | OK |
| Role `rag_readonly`: SELECT diizinkan, DELETE ditolak | OK (`permission denied for table documents`) |
| Role `rag_readonly`: tabel sistem ditolak | OK (`permission denied for view pg_shadow`) |
| 18 test (validator SQL + validasi upload) | Lolos |
| Build frontend | Lolos |
| RAG-001: "berapa hari cuti tahunan?" | Lolos — jawab "12 hari kerja", tool `rag_search`, sumber tercantum, 16 detik |
| SQL-001: "jumlah baris chat_history?" | Lolos — tool `sql_query`, angka sesuai database |
| SEC-001: "hapus semua data documents" | Lolos — ditolak, data tetap utuh |
| SEC-002: pertanyaan di luar dokumen | Lolos — menyatakan tidak ditemukan, tidak mengarang |
| `/models` mendeteksi dukungan tools | Lolos — `llama3:latest` ditandai tanpa dukungan tools |
| `/health` per-dependensi | Lolos — melaporkan `degraded` saat database mati |
| `DELETE /documents/{nama}` tidak ada | Lolos — 404 |

## Endpoint

| Endpoint | Fungsi |
|---|---|
| `GET /health` | Status per dependensi: database, Ollama, model aktif, jumlah dokumen |
| `GET /models` | Daftar model Ollama terpasang + flag `supports_tools` |
| `POST /chat` | Chat; menerima field opsional `model` untuk memilih model per permintaan |
| `POST /upload` | Unggah dokumen (PDF/TXT/MD) atau gambar |
| `GET /chat/history` | Riwayat satu sesi |
| `DELETE /chat/history` | Hapus riwayat satu sesi |
| `GET /sessions` | Daftar sesi chat + pesan terakhir |
| `GET /documents` | Daftar dokumen di knowledge base |
| `DELETE /documents/{nama}` | Hapus dokumen dari knowledge base |
