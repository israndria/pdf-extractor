# V25 PDF Extractor — opendataloader-pdf

> **Infrastruktur Ekstraktor PDF Hybrid** untuk dokumen pengadaan/lelang  
> Menggunakan `opendataloader-pdf` v2.2.0 (Apache Tika / PDFBox backend via Java)

---

## 🏗️ Struktur Folder

```
V25_PDFExtractor/
├── venv/                  ← Virtual environment Python (di-gitignore)
├── data_lelang/           ← Folder PDF lelang sensitif (di-gitignore)
├── pdf_mentah/            ← PDF sumber belum diproses (di-gitignore)
├── output_md/             ← Hasil ekstraksi Markdown (di-gitignore)
├── .gitignore             ← Daftar file/folder yang tidak masuk Git
├── requirements.txt       ← Daftar pustaka Python
├── uji_ekstraksi.py       ← Script utama ekstraktor PDF → Markdown
└── README.md              ← Dokumentasi ini
```

---

## ⚙️ Cara Setup

### 1. Prerequisite: Java 11+
```bash
java -version
# Jika tidak ada: Download dari https://adoptium.net/temurin/releases/?version=17
```

### 2. Aktifkan Virtual Environment
```powershell
# Windows PowerShell
.\\venv\\Scripts\\Activate.ps1

# Atau Command Prompt
.\\venv\\Scripts\\activate.bat
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🚀 Cara Pakai

1. Letakkan file PDF di folder `pdf_mentah/`
2. Edit `PDF_TARGET_PATH` di `uji_ekstraksi.py`
3. Jalankan:
   ```bash
   python uji_ekstraksi.py
   ```
4. Hasil Markdown akan muncul di `output_md/`

---

## 📦 Dependencies

| Library | Versi | Fungsi |
|---|---|---|
| `opendataloader-pdf` | 2.2.0 | Ekstraktor PDF hybrid (Java backed) |
| `markdown` | 3.10.2 | Helper konversi teks ke MD |

---

## ⚠️ Catatan Penting

- **Java 11+ WAJIB** — Library menggunakan Apache Tika/PDFBox di balik layar
- Virtual environment (`venv/`) **sudah dikecualikan** dari Git via `.gitignore`
- Folder `data_lelang/` dan `pdf_mentah/` **JANGAN pernah di-commit** (berisi dokumen sensitif)
