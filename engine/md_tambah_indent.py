"""
engine/md_tambah_indent.py — Tambah indentasi ke Markdown hasil MinerU
=======================================================================
MinerU menghasilkan .md tanpa indentasi — semua baris rata kiri.
Modul ini mendeteksi pola penomoran/huruf dokumen legal Indonesia
dan menambahkan indentasi Markdown (spasi prefix) agar:
  1. Bisa dibaca lebih jelas sebelum diupload ke chatbot
  2. Setelah chatbot fix typo, md_ke_docx.py bisa render indent dengan benar

Pola yang dideteksi (dokumen SP/kontrak pemerintah Indonesia):
  Level 0: ## heading, ### heading
  Level 1: a. b. c. ...       huruf kecil titik
  Level 2: 1) 2) 3) ...       angka tutup kurung
  Level 3: (a) (b) (c) ...    huruf kurung
  Level 4: (1) (2) (3) ...    angka kurung

Cara pakai:
    from engine.md_tambah_indent import tambah_indent_ke_md, md_indent_ke_bytes
"""

import re
from pathlib import Path


# ─────────────────────────────────────────────
# POLA PENOMORAN DOKUMEN LEGAL INDONESIA
# ─────────────────────────────────────────────

# Setiap tuple: (regex_pattern, indent_level, spasi_markdown)
# Urutan pengecekan: dari level terdalam ke terluar agar tidak salah match

POLA_INDENT = [
    # Level 4 — (1) (2) — paling dalam
    (re.compile(r"^\((\d{1,2})\)\s"), 4),
    # Level 3 — (a) (b) (c)
    (re.compile(r"^\(([a-z])\)\s"), 3),
    # Level 2 — 1) 2) 3) (angka diikuti kurung tutup, bukan titik)
    (re.compile(r"^(\d{1,2})\)\s"), 2),
    # Level 1 — a. b. c. (huruf kecil titik, bukan awal kalimat biasa)
    (re.compile(r"^([a-z])\.\s"), 1),
]

# Jumlah spasi per level indent di Markdown
SPASI_PER_LEVEL = 4   # 4 spasi = 1 level indent (kompatibel semua renderer)


def _deteksi_level(baris: str) -> int:
    """
    Deteksi level indentasi dari prefix baris.
    Return 0 jika bukan baris list/indented.
    """
    baris_stripped = baris.strip()
    for pola, level in POLA_INDENT:
        if pola.match(baris_stripped):
            return level
    return 0


def tambah_indent_ke_md(teks_md: str) -> str:
    """
    Tambahkan indentasi spasi ke teks Markdown berdasarkan deteksi pola.

    Heading (#, ##) tidak diubah.
    Baris kosong tidak diubah.
    Paragraf biasa (level 0) tidak diubah.
    Baris dengan pola list → ditambah spasi prefix sesuai level.

    Returns:
        str — Markdown dengan indentasi
    """
    baris_baris = teks_md.splitlines()
    hasil = []

    for baris in baris_baris:
        stripped = baris.strip()

        # Heading — tidak diubah
        if stripped.startswith("#"):
            hasil.append(baris)
            continue

        # Baris kosong — tidak diubah
        if not stripped:
            hasil.append(baris)
            continue

        # Deteksi level dari prefix
        level = _deteksi_level(baris)

        if level > 0:
            indent = " " * (SPASI_PER_LEVEL * level)
            hasil.append(indent + stripped)
        else:
            hasil.append(baris)

    return "\n".join(hasil)


def md_indent_ke_bytes(teks_md: str) -> bytes:
    """
    Convert Markdown + tambah indent → bytes UTF-8 untuk st.download_button.
    """
    return tambah_indent_ke_md(teks_md).encode("utf-8")
