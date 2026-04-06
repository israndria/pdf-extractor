"""
engine/ekstraksi.py — Wrapper MinerU CLI untuk ekstraksi PDF
=============================================================
Memanggil `mineru` CLI via subprocess dengan backend pipeline (CPU-only).
Mendukung PDF native (teks) dan PDF scan (OCR otomatis via MinerU).

Cara pakai:
    from engine.ekstraksi import ekstrak_pdf, deteksi_tipe_pdf
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Callable, Optional

# Path ke mineru CLI di venv
BASE_DIR = Path(__file__).parent.parent
VENV_BIN = BASE_DIR / "venv" / "Scripts"
MINERU_EXE = VENV_BIN / "mineru.exe"


def deteksi_tipe_pdf(pdf_path: Path) -> str:
    """
    Deteksi apakah PDF berisi teks native atau scan (gambar).
    Return: 'native' | 'scan' | 'mixed' | 'unknown'
    """
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(pdf_path))
        total = len(doc)
        if total == 0:
            return "unknown"
        teks_pages = 0
        sample = min(total, 5)  # cek 5 halaman pertama
        for i in range(sample):
            page = doc[i]
            textpage = page.get_textpage()
            teks = textpage.get_text_range()
            if len(teks.strip()) > 30:
                teks_pages += 1
        doc.close()
        ratio = teks_pages / sample
        if ratio >= 0.8:
            return "native"
        elif ratio <= 0.2:
            return "scan"
        else:
            return "mixed"
    except Exception:
        return "unknown"


def ekstrak_pdf(
    pdf_path: Path,
    output_dir: Path,
    on_progress: Optional[Callable[[str], None]] = None,
    metode: str = "auto",
    lang: str = "ch",
) -> dict:
    """
    Ekstrak PDF ke Markdown menggunakan MinerU pipeline backend (CPU).

    Args:
        pdf_path: Path ke file PDF
        output_dir: Folder output untuk hasil Markdown
        on_progress: Callback(msg) untuk update progress ke UI
        metode: 'auto' | 'txt' | 'ocr'
        lang: Bahasa OCR — 'ch' untuk mixed Cina/Latin (default), 'en' untuk Inggris/Indonesia

    Returns:
        dict dengan keys:
            success (bool)
            markdown_path (Path|None) — path ke file .md hasil
            markdown_text (str) — isi teks Markdown
            content_list_path (Path|None) — path ke *_content_list.json (untuk DOCX akurat)
            tipe_pdf (str) — 'native'|'scan'|'mixed'
            error (str|None)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    tipe_pdf = deteksi_tipe_pdf(pdf_path)
    if on_progress:
        on_progress(f"Tipe PDF terdeteksi: **{tipe_pdf}**")

    if not MINERU_EXE.exists():
        return {
            "success": False,
            "markdown_path": None,
            "markdown_text": "",
            "content_list_path": None,
            "tipe_pdf": tipe_pdf,
            "error": f"mineru tidak ditemukan di {MINERU_EXE}",
        }

    cmd = [
        str(MINERU_EXE),
        "-p", str(pdf_path.resolve()),
        "-o", str(output_dir.resolve()),
        "-b", "pipeline",
        "-m", metode,
        "-l", lang,
        "-f", "False",   # nonaktifkan formula parsing (lebih cepat)
    ]

    if on_progress:
        on_progress(f"Memulai ekstraksi MinerU... (backend: pipeline, metode: {metode})")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 menit max
        )
        stderr_lower = result.stderr.lower()
        if result.returncode != 0 and "error" in stderr_lower:
            return {
                "success": False,
                "markdown_path": None,
                "markdown_text": "",
                "content_list_path": None,
                "tipe_pdf": tipe_pdf,
                "error": result.stderr[-1000:],
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "markdown_path": None,
            "markdown_text": "",
            "content_list_path": None,
            "tipe_pdf": tipe_pdf,
            "error": "Timeout: proses ekstraksi melebihi 10 menit",
        }
    except Exception as e:
        return {
            "success": False,
            "markdown_path": None,
            "markdown_text": "",
            "content_list_path": None,
            "tipe_pdf": tipe_pdf,
            "error": str(e),
        }

    # Cari file .md yang dihasilkan
    # MinerU output structure: output_dir/<stem>/auto/<stem>.md
    md_path = _cari_file_md(output_dir, pdf_path.stem)
    content_list_path = _cari_content_list(output_dir, pdf_path.stem)

    if md_path and md_path.exists():
        teks = md_path.read_text(encoding="utf-8", errors="replace")
        if on_progress:
            cl_info = " + content_list.json ✓" if content_list_path else ""
            on_progress(f"Ekstraksi selesai. {len(teks):,} karakter diekstrak.{cl_info}")
        return {
            "success": True,
            "markdown_path": md_path,
            "markdown_text": teks,
            "content_list_path": content_list_path,
            "tipe_pdf": tipe_pdf,
            "error": None,
        }
    else:
        # Coba cari di mana saja dalam output_dir
        mds = list(output_dir.rglob("*.md"))
        if mds:
            md_path = mds[0]
            teks = md_path.read_text(encoding="utf-8", errors="replace")
            return {
                "success": True,
                "markdown_path": md_path,
                "markdown_text": teks,
                "content_list_path": content_list_path,
                "tipe_pdf": tipe_pdf,
                "error": None,
            }
        return {
            "success": False,
            "markdown_path": None,
            "markdown_text": "",
            "content_list_path": None,
            "tipe_pdf": tipe_pdf,
            "error": "File Markdown output tidak ditemukan. Cek log mineru di atas.",
        }


def _cari_file_md(output_dir: Path, stem: str) -> Optional[Path]:
    """Cari file .md MinerU berdasarkan stem nama file PDF.

    MinerU output structure: output_dir/<stem>/<metode>/<stem>.md
    Metode bisa: auto, txt, ocr, pipeline
    """
    # Cari rekursif dalam subfolder <stem>/
    subfolder = output_dir / stem
    if subfolder.exists():
        mds = list(subfolder.rglob(f"{stem}.md"))
        if mds:
            return mds[0]
        # Fallback: file .md pertama di subfolder
        mds = list(subfolder.rglob("*.md"))
        if mds:
            return mds[0]

    # Fallback langsung di output_dir
    kandidat = [
        output_dir / stem / f"{stem}.md",
        output_dir / f"{stem}.md",
    ]
    for p in kandidat:
        if p.exists():
            return p
    return None


def _cari_content_list(output_dir: Path, stem: str) -> Optional[Path]:
    """Cari file *_content_list.json di folder output MinerU."""
    subfolder = output_dir / stem
    if subfolder.exists():
        hasil = list(subfolder.rglob("*_content_list.json"))
        if hasil:
            return hasil[0]
    return None


def simpan_uploaded_pdf(uploaded_file, temp_dir: Path) -> Path:
    """
    Simpan file upload Streamlit ke folder temp.
    Return: Path ke file PDF yang tersimpan.
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    dest = temp_dir / uploaded_file.name
    dest.write_bytes(uploaded_file.read())
    return dest
