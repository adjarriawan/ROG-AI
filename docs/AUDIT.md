# Audit Arsitektur — Agentic RAG

Status: **audit saja, belum ada perubahan kode.** Semua temuan diverifikasi
langsung terhadap sumber dan sistem yang berjalan. Rujukan `file:baris` merujuk
commit `217afa9` di branch `fix/ocr-rapidocr-nonblocking`.

Ukuran nyata: 13 modul Python (~700 baris), 8 komponen React (~400 baris),
2 tabel, 3 tool, 9 endpoint, 20 tes. Ini MVP yang berfungsi, bukan sistem
enterprise — dan sebagian besar temuan di bawah adalah konsekuensi wajar dari
itu, bukan kesalahan.

---

## 1. Current Architecture

```
Browser (React 19 + Vite, :5173)
  │  axios, timeout 180 s, tanpa auth
  ▼
FastAPI (:8001) — 9 endpoint, CORS satu origin, tanpa middleware lain
  │  asyncio.to_thread
  ▼
LangChain AgentExecutor (create_tool_calling_agent)
  │  max_iterations=4, max_execution_time=240
  ├── rag_search  → pgvector cosine, top-4
  ├── sql_query   → engine read-only, allowlist 2 tabel
  └── image_ocr   → ProcessPoolExecutor(1), RapidOCR, deadline 180 s
  ▼
Ollama (:11434) — qwen2.5:7b + nomic-embed-text
  ▼
PostgreSQL 16 + pgvector (:5433) — 2 tabel, 56 chunk, 154 pesan
```

Tidak ada: planner, tool registry, context manager, guard, cache, metrik,
tracing, evaluation, migrasi DB, auth.

## 2–6. Current Flows

**Data flow (chat):** `POST /chat` → simpan pesan user → ambil 10 giliran
terakhir → `asyncio.to_thread(run_agent)` → executor → jawaban → simpan →
respons. Sinkron penuh dari sisi klien; tidak ada streaming.

**Agent flow:** pemilihan tool 100% diserahkan LLM. Tidak ada klasifikasi
intent, tidak ada planner, tidak ada retry. Multi-step hanya efek samping loop
executor. `tool_used` melaporkan tool **terakhir** saja — `tools_used[-1]`
(`backend/agent.py:69`), jadi eksekusi dua tool tampak sebagai satu.

**RAG flow:** embed query → satu query SQL `ORDER BY embedding <=> :q LIMIT 4`
→ saring jarak ≤ 0,6 di Python → gabungkan teks → kirim ke LLM.
Vector-only. Tanpa keyword, tanpa hybrid, tanpa reranker, tanpa kompresi.

**OCR flow:** hanya dipanggil agent, **tidak pernah dipakai saat ingestion**.
PDF hasil pindai menghasilkan 0 chunk lalu ditolak HTTP 400
(`backend/main.py:166`).

**SQL flow:** LLM menulis SQL → validator regex → eksekusi via engine
`rag_readonly` (`statement_timeout=5000`, `default_transaction_read_only=on`)
→ `fetchmany(50)`.

---

## 7. Problems Found

| # | Temuan | Bukti | Dampak |
|---|---|---|---|
| P1 | `rag_tool.last_sources` adalah **global mutable** | `tools/rag_tool.py:22` | Dua `/chat` bersamaan saling mencuri citation. Bukan teoretis: `/chat` jalan di threadpool. |
| P2 | `tool_used` membuang semua tool kecuali yang terakhir | `agent.py:69` | Jejak audit tidak lengkap |
| P3 | Nomor halaman hilang saat ingestion | `services/document_service.py:30` — halaman digabung `"\n\n"` sebelum split | Citation tidak bisa menyebut halaman. Ini memblokir target §13. |
| P4 | Scanned PDF ditolak, bukan di-OCR | `main.py:166` | Dokumen pindai tidak bisa masuk knowledge base sama sekali |
| P5 | OCR membuang confidence dan bbox | `tools/ocr_tool.py:48` — hanya `box[1]` diambil | Target §8 (confidence tersimpan) tidak terpenuhi |
| P6 | ivfflat `lists=100` dibangun di tabel kosong | `sql/init.sql:20` | Recall buruk pada 56 baris; index tidak pernah di-`REINDEX` |
| P7 | Tidak ada tool registry | `agent.py:11` — list hardcoded | Menambah tool = menyunting agent |
| P8 | Ingestion sinkron di dalam request | `main.py:160` | PDF besar memblokir satu worker; tidak ada status dokumen |
| P9 | Tidak ada migrasi DB | hanya entrypoint Docker | `models.py` dan `init.sql` bisa menyimpang diam-diam |
| P10 | Logger tak pernah dikonfigurasi | `main.py:28` | Tidak ada handler/format/level; jalur sukses tidak dicatat sama sekali |
| P11 | Cache LLM & executor tak berbatas | `agent.py:22`, `llm_service.py:37` | Klien bisa menumbuhkan memori dengan nama model sembarang |
| P12 | Berkas gambar tidak pernah dihapus | tidak ada sweeper | Disk tumbuh tanpa batas |
| P13 | `langchain-text-splitters` dipakai tapi tak didaftarkan | `document_service.py:6` vs `requirements.txt` | Rusak saat upgrade langchain |

## 8. Security Risks

| # | Risiko | Bukti | Tingkat |
|---|---|---|---|
| S1 | **Tanpa auth sama sekali** — `session_id` string bebas dari klien, tidak terikat identitas | `schemas.py:7` | Tinggi. Siapa pun bisa membaca riwayat sesi orang lain, mengenumerasi semua sesi beserta isinya (`GET /sessions`), menghapus dokumen mana pun. Ini keputusan Anda di awal MVP — dicatat, bukan dikritik. |
| S2 | `chat_history` ada di allowlist SQL | `tools/sql_tool.py:14` | Tinggi. Agent bisa diarahkan `SELECT message FROM chat_history` lintas sesi — kebocoran data antar pengguna lewat tool yang sah. |
| S3 | Kredensial hard-coded di sumber terlacak | `sql/init.sql:29` `'readonlypassword'`; `docker-compose.yml:8` `mysecretpassword` | Tinggi. Melanggar kriteria §26 secara langsung. `.env` sendiri bersih (0 hasil di seluruh riwayat Git). |
| S4 | Pesan galat mentah diteruskan ke klien dan ke LLM | `main.py:95,123,164`; `sql_tool.py:89,91` | Sedang. Galat Postgres membocorkan nama kolom/tipe ke konteks LLM. |
| S5 | Batas ukuran diperiksa **setelah** `await file.read()` | `main.py:142` | Sedang. Unggahan 2 GB habis di memori sebelum ditolak. |
| S6 | Tidak ada batas piksel gambar | `ocr_tool.py` | Sedang. Bom dekompresi lolos batas 25 MB. |
| S7 | Regex `_FORBIDDEN` cocok di dalam literal string | `sql_tool.py:17` | Rendah (false positive, bukan bypass). `WHERE message = 'please update'` ditolak. |
| S8 | Tanpa rate limiting | — | Sedang. Satu klien bisa menjenuhkan Ollama. |

Yang **sudah benar** dan jangan dibongkar: peran DB read-only terverifikasi
empiris (`permission denied for table documents` pada DELETE), nama berkas
di-UUID-kan, magic-byte dicek, chunk RAG dipagari "DATA, bukan instruksi",
OCR terisolasi di proses terpisah.

## 9. Performance Risks

- Embedding query dihitung ulang setiap panggilan RAG, tanpa cache.
- `MAX_ROWS=50` diterapkan di sisi klien (`fetchmany`) — DB tetap menghitung
  hasil penuh.
- Tidak ada indeks pada `documents.filename` meski dipakai `GROUP BY` dan
  `DELETE WHERE` (`main.py:199`, `:208`).
- Embedding satu PDF besar dikirim dalam satu panggilan, tanpa batching.
- `/chat` 1–100 detik tergantung jumlah giliran tool; tidak ada streaming, jadi
  pengguna menatap spinner.

## 10. Technical Debt

- `python-magic` terdaftar tapi **tidak pernah diimpor** — validasi magic byte
  ditulis tangan di `uploads.py:20`.
- `paddleocr 2.9.1` + `paddlepaddle 2.6.2` masih terpasang di venv (**297 MB**),
  tidak diimpor kode mana pun, tidak jadi dependensi paket lain. Sisa migrasi.
- Komentar basi: `requirements.txt:16` ("paddle imports it at runtime"),
  `run.sh:38`, `run.sh:101`.
- `pytest` disematkan di requirements runtime.
- Dua endpoint mengembalikan dict tanpa anotasi (`main.py:213`, `:244`).
- `run_agent() -> dict` menyeberangi batas modul tanpa tipe (`agent.py:55`).
- Tidak ada linter/type-checker Python (oxlint frontend lolos bersih).

---

# Proposal

## 11. Proposed Architecture

Menambah lapisan, **tanpa membongkar yang ada**. Semua kotak baru bisa
dipasang bertahap; endpoint dan perilaku existing tetap.

```
UI → FastAPI → Input Guard → Orchestrator
                               ├── Planner (hanya untuk query kompleks)
                               └── Tool Registry
                                     ├── rag_search   (hybrid + rerank)
                                     ├── sql_query    (allowlist diperketat)
                                     ├── ocr_extract  (confidence + bbox)
                                     └── calculator   (baru, deterministik)
                               ↓
                          Tool Guard (validate → permission → timeout → audit)
                               ↓
                          Context Manager (merge, dedup, rank, budget token)
                               ↓
                          LLM Service → Output Guard → Citation Validator
```

## 12–16. Proposed Flows

- **Agent:** intent sederhana → jawab tanpa tool (sudah jalan, AGENT-001 lulus).
  Kompleks → planner memecah jadi langkah. `tool_used` jadi `tools_used: list`.
- **RAG:** vector top-30 ∥ keyword `tsvector` top-30 → merge → rerank → top-5.
  Metadata per chunk diperluas (halaman, seksi, tahun, organisasi, tipe) dan
  bisa jadi filter.
- **OCR:** `ocr/base.py` (`OCRService` abstrak) + `ocr/rapidocr_service.py`.
  Tool memanggil antarmuka, bukan RapidOCR langsung. Output berstruktur
  `pages[].blocks[]{text, confidence, bbox}`.
- **Ingestion:** deteksi text layer → native extract; kalau kosong → OCR
  fallback (ini yang membuka P4). Status dokumen dilacak eksplisit.
- **SQL:** parser sungguhan (`sqlglot`) menggantikan regex; `chat_history`
  dikeluarkan dari allowlist default.

## 17–19. Dampak Berkas

**Dibuat (~14):** `tools/registry.py`, `tools/base.py`, `tools/calculator_tool.py`,
`ocr/{base,rapidocr_service,models,postprocessor}.py`, `services/context_manager.py`,
`services/planner.py`, `guards/{input,output,tool}_guard.py`,
`observability/{logging,metrics}.py`, `migrations/` (Alembic), `evaluation/`.

**Diubah (~10):** `agent.py` (pakai registry), `tools/*.py` (skema I/O),
`main.py` (envelope + request_id), `document_service.py` (halaman + OCR
fallback), `sql_tool.py` (parser), `models.py`+`init.sql` (kolom metadata),
`schemas.py`, `requirements.txt`, `README-DEV.md`, `run.sh`.

**Dihapus:** tidak ada berkas. Hanya dependensi (`paddleocr`, `paddlepaddle`,
`python-magic`) dan komentar basi.

## 20. Database Changes

Semua **aditif dan backward-compatible** — tidak ada `DROP`, tidak ada data
existing yang hilang:

- `documents`: tambah `page`, `section`, `doc_type`, `organization`, `year`,
  `status`, `content_tsv` (generated, untuk keyword search) + indeks GIN.
- `documents`: indeks btree pada `filename`.
- Tabel baru: `agent_runs`, `tool_runs`, `citations`, `feedback`,
  `evaluation_cases`.
- Alembic diperkenalkan dengan baseline = skema saat ini, jadi 56 chunk dan
  154 pesan yang ada tetap utuh.
- `init.sql`: kata sandi dari variabel lingkungan, bukan literal.

## 21–22. Dependensi

**Tambah** — masing-masing dengan alasan:

| Paket | Tujuan | Alternatif | Alasan dipilih |
|---|---|---|---|
| `sqlglot` | Parser SQL sungguhan menggantikan regex | `sqlparse`, regex | Memahami AST, mengenali CTE/subquery dengan benar; regex saat ini punya celah nyata |
| `alembic` | Migrasi | manual SQL | Sudah standar SQLAlchemy, tanpa dependensi baru |
| `rank-bm25` **atau** `tsvector` bawaan Postgres | Keyword search | Elasticsearch | `tsvector` **direkomendasikan**: nol dependensi baru, nol layanan baru |
| `structlog` | Logging terstruktur | `logging` + JSON formatter | Opsional; `logging` bawaan cukup kalau ingin minimal |
| `pytest-asyncio`, `httpx` (sudah ada) | Tes endpoint | — | `httpx` sudah terpasang |

**Buang:** `paddleocr`, `paddlepaddle` (297 MB, tidak dipakai), `python-magic`
(tidak pernah diimpor). Pindahkan `pytest` ke `requirements-dev.txt`.
Daftarkan `langchain-text-splitters` secara eksplisit.

**Reranker** memerlukan keputusan Anda — lihat Keputusan Terbuka di bawah.

## 23. Migration Strategy

Setiap fase berdiri sendiri, bisa dihentikan di mana saja tanpa merusak:
baseline Alembic dulu, lalu kolom aditif, lalu backfill opsional (dokumen lama
tetap berfungsi dengan metadata kosong), lalu tabel observability.
Tidak ada migrasi destruktif.

## 24. Testing Strategy

Dari 20 tes sekarang (validator SQL, validasi upload, caching) menuju cakupan
25 skenario. Prioritas berdasarkan risiko, bukan urutan daftar:

1. **Keamanan dulu:** `_safe_path` traversal (kontrol keamanan yang saat ini
   **tidak diuji sama sekali**), penegakan peran read-only terhadap DB nyata,
   percobaan prompt injection, akses lintas sesi.
2. **Regresi:** tes HTTP untuk 9 endpoint (belum ada satu pun).
3. **Konkurensi:** balapan `last_sources` (P1) — tes yang gagal sebelum
   perbaikan, lulus sesudahnya.
4. Jalur galat: timeout tool, LLM timeout, DB mati, hasil SQL kosong.

## 25. Implementation Phases

Urutan ini mendahulukan keamanan dan integritas data sesuai prioritas Anda,
bukan urutan A–R apa adanya:

| # | Fase | Isi | Risiko regresi |
|---|---|---|---|
| 1 | **Kebersihan & keamanan cepat** | Buang 297 MB paddle + `python-magic`, kredensial ke env, sanitasi pesan galat, batas ukuran sebelum baca, keluarkan `chat_history` dari allowlist | Rendah |
| 2 | **Perbaikan korektness** | P1 (global `last_sources`), P2 (`tools_used` jamak), P13 | Rendah |
| 3 | **Observability** | request_id, logging terstruktur, `agent_runs`/`tool_runs` | Rendah |
| 4 | **Tool Registry + Tool Guard** | `base.py`, `registry.py`, skema I/O bertipe, calculator | Sedang |
| 5 | **Abstraksi OCR + ingestion** | `ocr/`, confidence+bbox, deteksi text layer, OCR fallback (P4, P5) | Sedang |
| 6 | **RAG** | metadata halaman (P3), hybrid search, reranker, Context Manager | Tinggi — perlu baseline evaluasi lebih dulu |
| 7 | **Guard & citation validation** | Input/Output Guard, validator citation | Sedang |
| 8 | **Planner** | multi-step untuk query kompleks | Tinggi |
| 9 | **Evaluation + testing** | dataset, 25 skenario | Rendah |
| 10 | **Cache, metrics, performance** | setelah bottleneck terukur | Rendah |

Fase 6 sebaiknya **didahului** fase 9 sebagian: tanpa baseline evaluasi,
perubahan chunking/reranker tidak bisa dibuktikan memperbaiki apa pun.

---

## Keputusan Terbuka

Empat hal tidak bisa saya putuskan sendiri karena mengubah karakter sistem.

### K1 — Reranker

**Problem:** reranking butuh model kedua.
**Options:** (a) cross-encoder ONNX lokal (~90 MB, ~50 ms/kandidat);
(b) rerank pakai qwen2.5:7b lewat Ollama (tanpa dependensi, tapi +5–15 detik
per query dan non-deterministik); (c) tanpa reranker, andalkan hybrid + top-k.
**Trade-off:** (a) akurasi terbaik, dependensi baru; (b) nol dependensi, lambat;
(c) paling sederhana, peningkatan paling kecil.
**Rekomendasi:** (a) — latensi CPU sudah jadi masalah, opsi (b) memperburuknya.
**Impact:** +1 dependensi, +90 MB, +~0,5 detik per query.

### K2 — Nasib `chat_history` di allowlist SQL

**Problem:** SQL-001 ("ada berapa dokumen") butuh allowlist, tapi
`chat_history` berisi percakapan semua pengguna.
**Options:** (a) keluarkan sepenuhnya; (b) ganti dengan view teragregasi
(`chat_stats`) tanpa kolom `message`; (c) biarkan sampai auth ada.
**Rekomendasi:** (b) — statistik tetap bisa dijawab, isi pesan tidak bocor.
**Impact:** satu view baru; pertanyaan seperti "berapa chat hari ini" tetap jalan.

### K3 — Auth

Anda memilih tanpa JWT untuk MVP. Target §10 dan §11 (RBAC per-OPD) tidak bisa
dipenuhi tanpanya, dan S1/S2 tetap terbuka sampai itu ada. Saya tidak akan
menambahkannya tanpa permintaan eksplisit — tapi perlu dicatat bahwa
"Authorization diterapkan sebelum akses data" (kriteria §10) **tidak akan
tercapai** selama ini berlaku.

### K4 — Cakupan

Daftar 36 fase ini realistis berbulan-bulan untuk tim, bukan satu sesi. Fase
1–3 (kebersihan, korektness, observability) bisa saya kerjakan dan buktikan
dengan tes dalam waktu wajar dan risikonya rendah. Fase 6 dan 8 mengubah
kualitas jawaban dan butuh baseline evaluasi lebih dulu.

Saya menyarankan mulai dari fase 1–3, lalu tinjau ulang.
