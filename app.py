"""
V25 PDF Extractor — Streamlit App
===================================
Pipeline: Ekstrak PDF → Parse Field Pengadaan → AI Analisis → Simpan Supabase
Port: 8507

Jalankan via: Buka PDF Extractor.bat
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# ─── Setup path ───
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from engine.ekstraksi import ekstrak_pdf, simpan_uploaded_pdf
from engine.parser_field import parse_field_pengadaan, export_ke_lpse_json, hitung_kelengkapan
from engine.supabase_uploader import simpan_ke_supabase, cek_koneksi_supabase
from engine.md_ke_docx import md_ke_bytes

# ─────────────────────────────────────────────
# KONFIGURASI HALAMAN
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="V25 PDF Extractor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    h1 { padding-top: 0; }
    .stTabs [data-baseweb="tab"] { font-size: 1rem; }
    .status-card {
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────

def _init_state():
    for k, v in {
        "hasil_ekstraksi": {},   # {nama_file: {success, markdown_text, tipe_pdf, ...}}
        "hasil_parse": {},       # {nama_file: dict field}
        "file_paths": {},        # {nama_file: Path}
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Pengaturan")
    st.divider()

    metode_ocr = st.selectbox(
        "Metode Ekstraksi",
        options=["auto", "txt", "ocr"],
        index=0,
        help="auto: otomatis, txt: teks saja, ocr: paksa OCR (untuk PDF scan)"
    )

    lang_ocr = st.selectbox(
        "Bahasa OCR",
        options=["en", "ch", "latin"],
        index=0,
        format_func=lambda x: {"ch": "ch — Mandarin/Latin (Default)", "en": "en — Inggris/Indonesia", "latin": "latin — Latin umum"}[x],
        help="Bahasa untuk OCR. 'ch' juga mengenali teks Latin termasuk Bahasa Indonesia."
    )

    st.divider()

    # Status Supabase
    with st.expander("Status Supabase", expanded=False):
        if st.button("Test Koneksi"):
            with st.spinner("Menghubungkan..."):
                hasil_koneksi = cek_koneksi_supabase()
            if hasil_koneksi["success"]:
                if hasil_koneksi.get("tabel_belum_ada"):
                    st.warning("Koneksi OK, tapi tabel `dokumen_pdf` belum ada.")
                    st.code(hasil_koneksi.get("sql_create", ""), language="sql")
                else:
                    st.success(f"Terhubung: {hasil_koneksi['url'][:40]}...")
            else:
                st.error(f"Gagal: {hasil_koneksi['error']}")

    st.divider()
    st.caption("V25 PDF Extractor · MinerU 3.0.8")
    st.caption(f"Python {sys.version.split()[0]}")

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────

st.title("📄 V25 PDF Extractor")
st.caption("Ekstrak teks dari PDF (native & scan) menggunakan MinerU · Pipeline terpisah per tahap")

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📄 1. Ekstrak PDF",
    "🔍 2. Parse Field Pengadaan",
    "🤖 3. AI Analisis",
    "☁️ 4. Simpan Supabase",
])

# ══════════════════════════════════════════════
# TAB 1: EKSTRAK PDF
# ══════════════════════════════════════════════

with tab1:
    st.subheader("Upload & Ekstrak PDF")
    st.info(
        "Upload satu atau beberapa file PDF. MinerU akan mengekstrak teks menggunakan "
        "**pipeline backend (CPU)** — mendukung PDF native maupun PDF hasil scan (OCR otomatis).",
        icon="ℹ️"
    )

    uploaded_files = st.file_uploader(
        "Pilih file PDF",
        type=["pdf"],
        accept_multiple_files=True,
        key="uploader_pdf",
    )

    if uploaded_files:
        st.write(f"**{len(uploaded_files)} file** siap diproses:")
        for f in uploaded_files:
            st.write(f"  - `{f.name}` ({f.size / 1024:.1f} KB)")

    col_btn, col_clear = st.columns([1, 1])
    with col_btn:
        mulai = st.button(
            "▶️ Mulai Ekstraksi",
            disabled=not uploaded_files,
            type="primary",
            use_container_width=True,
        )
    with col_clear:
        if st.button("🗑️ Bersihkan Hasil", use_container_width=True):
            st.session_state["hasil_ekstraksi"] = {}
            st.session_state["hasil_parse"] = {}
            st.session_state["file_paths"] = {}
            st.rerun()

    if mulai and uploaded_files:
        temp_input = BASE_DIR / "temp_input"
        output_dir = BASE_DIR / "output_md"
        temp_input.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)

        progress_bar = st.progress(0)
        status_placeholder = st.empty()

        for idx, uf in enumerate(uploaded_files):
            status_placeholder.write(f"⏳ Memproses **{uf.name}** ({idx+1}/{len(uploaded_files)})...")

            # Reset read position
            uf.seek(0)

            # Simpan ke temp
            pdf_path = simpan_uploaded_pdf(uf, temp_input)
            st.session_state["file_paths"][uf.name] = pdf_path

            log_msgs = []
            def _on_progress(msg):
                log_msgs.append(msg)
                status_placeholder.markdown(f"⏳ **{uf.name}**: {msg}")

            hasil = ekstrak_pdf(
                pdf_path=pdf_path,
                output_dir=output_dir,
                on_progress=_on_progress,
                metode=metode_ocr,
                lang=lang_ocr,
            )
            st.session_state["hasil_ekstraksi"][uf.name] = hasil
            progress_bar.progress((idx + 1) / len(uploaded_files))

        status_placeholder.success(f"✅ Semua file selesai diproses!")
        progress_bar.progress(1.0)

    # Tampilkan hasil
    if st.session_state["hasil_ekstraksi"]:
        st.divider()
        st.subheader("Hasil Ekstraksi")

        for nama_file, hasil in st.session_state["hasil_ekstraksi"].items():
            tipe_icon = {"native": "📝", "scan": "🖼️", "mixed": "📑", "unknown": "❓"}.get(hasil.get("tipe_pdf", ""), "❓")

            if hasil["success"]:
                with st.expander(f"{tipe_icon} **{nama_file}** — Berhasil (tipe: {hasil.get('tipe_pdf', '-')})", expanded=False):
                    teks = hasil.get("markdown_text", "")
                    st.metric("Panjang teks", f"{len(teks):,} karakter")
                    st.markdown("**Preview (500 karakter pertama):**")
                    st.code(teks[:500], language=None)
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button(
                            label="⬇️ Download Markdown",
                            data=teks.encode("utf-8"),
                            file_name=f"{Path(nama_file).stem}.md",
                            mime="text/markdown",
                            key=f"dl_md_{nama_file}",
                        )
                    with col_dl2:
                        try:
                            docx_bytes = md_ke_bytes(teks, judul=Path(nama_file).stem)
                            st.download_button(
                                label="⬇️ Download DOCX",
                                data=docx_bytes,
                                file_name=f"{Path(nama_file).stem}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"dl_docx_{nama_file}",
                            )
                        except Exception as e:
                            st.error(f"Gagal konversi DOCX: {e}")
            else:
                with st.expander(f"❌ **{nama_file}** — Gagal", expanded=True):
                    st.error(hasil.get("error", "Error tidak diketahui"))
                    st.info(
                        "Pastikan model MinerU sudah terdownload. "
                        "Jalankan: `mineru-models-download -s huggingface -m pipeline`"
                    )


# ══════════════════════════════════════════════
# TAB 2: PARSE FIELD PENGADAAN
# ══════════════════════════════════════════════

with tab2:
    st.subheader("Parse Field Dokumen Pengadaan")

    hasil_ekstraksi = st.session_state.get("hasil_ekstraksi", {})
    file_berhasil = {k: v for k, v in hasil_ekstraksi.items() if v.get("success")}

    if not file_berhasil:
        st.warning("Belum ada hasil ekstraksi. Lakukan ekstraksi di Tab 1 terlebih dahulu.", icon="⚠️")
    else:
        st.info(
            f"{len(file_berhasil)} file siap diparsing. Klik tombol di bawah untuk mengekstrak "
            "field-field standar dokumen pengadaan (HPS, Pagu, Nama Paket, dll).",
            icon="ℹ️"
        )

        if st.button("🔍 Parse Field Otomatis", type="primary", use_container_width=True):
            for nama_file, hasil in file_berhasil.items():
                teks = hasil.get("markdown_text", "")
                field = parse_field_pengadaan(teks)
                st.session_state["hasil_parse"][nama_file] = field
            st.success(f"Parsing selesai untuk {len(file_berhasil)} file.")

        if st.session_state.get("hasil_parse"):
            st.divider()

            for nama_file, field in st.session_state["hasil_parse"].items():
                terisi, total = hitung_kelengkapan(field)
                with st.expander(
                    f"📋 **{nama_file}** — {terisi}/{total} field terdeteksi",
                    expanded=True,
                ):
                    # Tampilkan field sebagai tabel
                    rows = []
                    for k, v in field.items():
                        if v is not None and v != "":
                            label = k.replace("_", " ").title()
                            rows.append({"Field": label, "Nilai": str(v)})

                    if rows:
                        import pandas as pd
                        df = pd.DataFrame(rows)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.warning("Tidak ada field yang berhasil diekstrak dari dokumen ini.")
                        st.caption("Kemungkinan format dokumen tidak standar atau OCR kurang akurat.")

                    # Export JSON
                    json_str = export_ke_lpse_json(field)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="⬇️ Export _import_lpse.json",
                            data=json_str.encode("utf-8"),
                            file_name="_import_lpse.json",
                            mime="application/json",
                            key=f"dl_json_{nama_file}",
                        )
                    with col2:
                        st.download_button(
                            label="⬇️ Export semua field (JSON)",
                            data=json.dumps(field, ensure_ascii=False, indent=2).encode("utf-8"),
                            file_name=f"{Path(nama_file).stem}_field.json",
                            mime="application/json",
                            key=f"dl_field_{nama_file}",
                        )


# ══════════════════════════════════════════════
# TAB 3: AI ANALISIS (PLACEHOLDER)
# ══════════════════════════════════════════════

with tab3:
    st.subheader("AI Analisis Dokumen")

    st.info(
        "Fitur ini memerlukan LLM lokal (Ollama + Qwen) yang belum dikonfigurasi. "
        "Setelah Ollama terinstall dan model Qwen tersedia, sambungkan ke URL di bawah.",
        icon="🤖"
    )

    with st.expander("📖 Cara Setup Ollama + Qwen (klik untuk panduan)", expanded=False):
        st.markdown("""
**Langkah Setup LLM Lokal:**

1. **Install Ollama** (Windows):
   - Download dari: https://ollama.ai/download
   - Jalankan installer, Ollama akan berjalan sebagai service di background

2. **Download model Qwen:**
   ```bash
   ollama pull qwen2.5:7b
   # Atau versi lebih kecil (lebih cepat, RAM lebih sedikit):
   ollama pull qwen2.5:3b
   ```

3. **Verifikasi Ollama berjalan:**
   - Buka browser: http://localhost:11434
   - Seharusnya tampil: `Ollama is running`

4. **Isi URL di bawah dan klik Simpan Config**

> **Catatan**: Qwen 2.5 7B membutuhkan ~8GB RAM. Qwen 2.5 3B ~4GB RAM.
        """)

    st.divider()

    ollama_url = st.text_input(
        "Ollama Base URL",
        value="http://localhost:11434",
        placeholder="http://localhost:11434",
    )

    ollama_model = st.text_input(
        "Model",
        value="qwen2.5:7b",
        placeholder="qwen2.5:7b",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔌 Test Koneksi Ollama"):
            import urllib.request
            try:
                req = urllib.request.urlopen(ollama_url, timeout=3)
                resp = req.read().decode()
                if "ollama" in resp.lower() or "running" in resp.lower():
                    st.success(f"Ollama terhubung! URL: {ollama_url}")
                else:
                    st.warning(f"URL merespons tapi format tidak dikenali: {resp[:100]}")
            except Exception as e:
                st.error(f"Gagal terhubung: {e}")

    with col2:
        st.button(
            "🤖 Analisis Dokumen",
            disabled=True,
            help="Sambungkan Ollama terlebih dahulu, lalu aktifkan fitur ini.",
        )

    st.divider()
    st.caption("Fitur yang akan tersedia setelah LLM dikonfigurasi:")
    st.markdown("""
- **Ringkasan Eksekutif** — 3-5 kalimat inti dokumen
- **Persyaratan Kualifikasi** — Tabel: SBU, SIUJK, pengalaman, tenaga ahli
- **Identifikasi Red Flags** — Syarat yang terindikasi mengarah ke satu penyedia
- **Timeline Tender** — Jadwal terstruktur dari dokumen
    """)


# ══════════════════════════════════════════════
# TAB 4: SIMPAN SUPABASE
# ══════════════════════════════════════════════

with tab4:
    st.subheader("Simpan ke Supabase")

    hasil_ekstraksi = st.session_state.get("hasil_ekstraksi", {})
    hasil_parse = st.session_state.get("hasil_parse", {})
    file_berhasil = {k: v for k, v in hasil_ekstraksi.items() if v.get("success")}

    if not file_berhasil:
        st.warning("Belum ada hasil ekstraksi. Lakukan ekstraksi di Tab 1 terlebih dahulu.", icon="⚠️")
    else:
        st.info(
            f"Siap menyimpan **{len(file_berhasil)} dokumen** ke tabel `dokumen_pdf` di Supabase.",
            icon="☁️"
        )

        # Preview ringkasan
        st.subheader("Preview Data yang Akan Disimpan")
        for nama_file, hasil in file_berhasil.items():
            tipe = hasil.get("tipe_pdf", "unknown")
            teks = hasil.get("markdown_text", "")
            field = hasil_parse.get(nama_file, {})
            terisi, total = hitung_kelengkapan(field) if field else (0, 0)

            with st.expander(f"📄 {nama_file}", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Tipe Dokumen", tipe)
                col2.metric("Panjang Teks", f"{len(teks):,} karakter")
                col3.metric("Field Terisi", f"{terisi}/{total}")

                if field:
                    nama = field.get("nama_paket") or field.get("satuan_kerja") or "-"
                    hps = field.get("hps_teks") or "-"
                    st.write(f"**Nama Paket**: {nama}")
                    st.write(f"**HPS**: {hps}")

        st.divider()

        if st.button("☁️ Simpan ke Supabase", type="primary", use_container_width=True):
            progress_bar2 = st.progress(0)
            status2 = st.empty()
            sukses = 0
            gagal = 0
            errors = []

            file_list = list(file_berhasil.items())
            for idx, (nama_file, hasil) in enumerate(file_list):
                status2.write(f"⏳ Menyimpan **{nama_file}**...")
                field = hasil_parse.get(nama_file, {})

                resp = simpan_ke_supabase(
                    nama_file=nama_file,
                    tipe_dokumen=hasil.get("tipe_pdf", "unknown"),
                    teks_markdown=hasil.get("markdown_text", ""),
                    field_parsed=field,
                )
                if resp["success"]:
                    sukses += 1
                    status2.success(f"✅ {nama_file} → ID: {resp['id']}")
                else:
                    gagal += 1
                    errors.append(f"**{nama_file}**: {resp['error']}")

                progress_bar2.progress((idx + 1) / len(file_list))

            # Laporan akhir
            st.divider()
            if sukses:
                st.success(f"✅ **{sukses} dokumen** berhasil disimpan ke Supabase.")
            if gagal:
                st.error(f"❌ **{gagal} dokumen** gagal disimpan.")
                for err in errors:
                    with st.expander("Detail error"):
                        st.markdown(err)

        st.divider()
        st.caption("Dokumen tersimpan dapat dilihat di Supabase Dashboard → Table Editor → `dokumen_pdf`")
