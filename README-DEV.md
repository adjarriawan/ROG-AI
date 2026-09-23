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

## Hardening pass (Fase 1-3)

**Kredensial keluar dari repo.** `init.sql` tidak lagi memuat password. Password
role read-only masuk lewat `backend/sql/01-init.sh` (dijalankan lebih dulu
karena urut abjad) sebagai variabel psql, dibaca dari environment. `POSTGRES_PASSWORD`
dan `RAG_READONLY_PASSWORD` wajib ada di `.env`; `docker-compose.yml` gagal cepat
kalau kosong.

**`chat_history` tidak lagi bisa dibaca agent.** Tanpa auth, siapa pun bisa
menyuruh agent membaca sesi orang lain. Yang di-grant sekarang view agregat
`chat_stats` (session_id, role, day, message_count, first_at, last_at) - cukup
untuk "berapa chat hari ini", tanpa isi pesan. Batas ini ada di dua lapis:
GRANT di database, dan allowlist di `sql_tool.py`.

**Pesan error disanitasi.** `backend/errors.py`: detail exception masuk ke log
JSON (dengan request id), yang kembali ke client hanya kalimat umum + `ref:`.
Error driver bisa membawa connection string dan isi baris; untuk `tool_error`
teks itu juga akan masuk konteks LLM, jadi tidak boleh bocor ke sana.

**Batas ukuran upload dicek sebelum `file.read()`.** Membaca dulu baru memvalidasi
berarti body 1 GB sudah terlanjur di memori.

**Observability.** `backend/observability/`: middleware memberi tiap request satu
id (`x-request-id`, dihormati kalau klien mengirimnya), formatter JSON meredaksi
field bernama password/secret/token/api_key/authorization/credential, dan
exception dicatat sebagai `error_type` + 500 karakter pertama - bukan traceback
penuh, yang bisa memuat connection string.

**Citation berhalaman.** Chunking sekarang per halaman, bukan seluruh PDF
digabung dulu, sehingga `metadata.page` terisi dan `/chat` mengembalikan
`{filename, page, chunk_index}`. Chunk lama (55 baris dari 2 PDF) sudah
di-reindex. TXT/MD tetap `page: null` - menomori 1 akan menyesatkan.

**Konfigurasi.** `sql_max_rows`, `ocr_timeout_seconds`, `agent_max_iterations`,
`agent_timeout_seconds`, `log_level` pindah ke `config.py`/`.env`.

**Dependency.** `paddleocr`/`paddlepaddle` (297 MB) dan `python-magic` dicopot -
RapidOCR sudah jadi engine, dan signature file dicek manual di `uploads.py`.
`langchain-text-splitters` didaftarkan karena diimpor langsung.

### Jebakan yang ditemukan saat pengujian

`ContextVar.set()` di dalam tool LangChain hilang: tool sinkron dijalankan di
bawah `contextvars.copy_context()`, jadi binding baru mendarat di salinan.
`rag_tool` karena itu memutasi list-nya di tempat, bukan me-`set()` ulang.
Ada test yang mengunci perilaku ini (`test_sources_survive_a_copied_context`).

### Lint

```bash
backend/.venv/bin/pip install -r backend/requirements-dev.txt
cd backend && .venv/bin/ruff check .
```

Konfigurasi ada di `backend/ruff.toml` (bukan di venv) supaya hasilnya sama di
semua mesin: aturan default + `I` (urutan import), `B` (bugbear), `RUF`. Dua
aturan dimatikan dengan alasan: `B008` karena `Depends()`/`File()` di default
argumen memang cara FastAPI mendeklarasikan dependency, dan `BLE001` karena
batas tool serta health probe sengaja menangkap semua exception - dependency
yang gagal harus menurunkan kualitas jawaban, bukan mematikan request.

Satu temuan nyata dari lint pertama: `ContextVar("rag_sources", default=[])`
(B039). Default mutable itu satu objek yang dipakai bersama oleh setiap context
yang belum memanggil `reset_sources()` - persis kebocoran antar-request yang
seharusnya dicegah ContextVar. Sekarang `default=None` dengan list dibuat saat
pertama dipakai.
