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

Wajib **Python 3.12** — `paddlepaddle` belum punya wheel untuk 3.13.

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
- OCR pertama kali mengunduh model PaddleOCR (~10-50 MB), jadi panggilan pertama lambat.

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
