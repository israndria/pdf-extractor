"""
engine/content_list_ke_docx.py — Konverter MinerU content_list.json → DOCX (v3)
================================================================================
Menggunakan metadata struktural MinerU untuk DOCX akurat:
  - Indentasi dari bbox.x0 via percentile-binning per dokumen
  - Heading level dari text_level MinerU
  - Tabel dengan colspan/rowspan penuh
  - Gambar/stempel embedded

Cara pakai:
    from engine.content_list_ke_docx import content_list_ke_bytes
"""

import json
import io
import re
import html as html_lib
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ─────────────────────────────────────────────
# KALIBRASI INDENTASI — Percentile Binning
# ─────────────────────────────────────────────

def _bangun_x0_mapper(blocks, n_levels: int = 4, batas_kanan: float = 350):
    """
    Buat fungsi mapper: x0_float → indent_level (int 0..n_levels-1)

    Strategi:
    1. Kumpulkan semua x0 dari blok teks body (bukan heading, bukan centered)
    2. Hitung min dan max x0 → definisikan range
    3. Bagi range menjadi n_levels slot sama besar
    4. Return lambda yang memetakan x0 ke slot-nya

    Hasilnya robust untuk scan PDF karena tidak bergantung pada gap antar x0.
    """
    x0_vals = []
    for b in blocks:
        if b.get("type") == "text" and b.get("bbox"):
            x0 = b["bbox"][0]
            if x0 < batas_kanan:  # skip teks terpusat (judul halaman, stempel, dll.)
                x0_vals.append(x0)

    if not x0_vals:
        return lambda x: 0, 0, 0

    x0_sorted = sorted(x0_vals)
    n = len(x0_sorted)
    # Gunakan percentile 5%-95% agar outlier tidak menggeser seluruh mapping
    x0_min = x0_sorted[max(0, int(n * 0.05))]
    x0_max = x0_sorted[min(n - 1, int(n * 0.95))]
    span = x0_max - x0_min

    if span < 10:
        # Semua teks di posisi sama — tidak ada indentasi
        return lambda x: 0, x0_min, x0_max

    slot_size = span / n_levels

    def mapper(x0: float) -> int:
        lvl = int((x0 - x0_min) / slot_size)
        return max(0, min(n_levels - 1, lvl))

    return mapper, x0_min, x0_max


# ─────────────────────────────────────────────
# FUNGSI UTAMA
# ─────────────────────────────────────────────

def content_list_ke_docx(json_path: Path, judul: str = "") -> Document:
    """
    Konversi *_content_list.json MinerU ke python-docx Document.

    Indentasi dihitung per-dokumen dari distribusi x0 aktual (percentile binning).
    Cocok untuk dokumen scan yang x0-nya tidak presisi.
    """
    with open(json_path, encoding="utf-8") as f:
        blocks = json.load(f)

    doc = Document()

    # Margin standar dokumen pemerintah Indonesia
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3)
        section.right_margin = Cm(2.5)

    if judul:
        p = doc.add_heading(judul, level=0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ── Bangun mapper x0 → indent level ─────
    # Gunakan semua blok teks untuk kalibrasi (termasuk heading — lebih representatif)
    mapper, x0_min, x0_max = _bangun_x0_mapper(blocks, n_levels=4, batas_kanan=350)
    CM_PER_LEVEL = 0.75   # indent Word per level

    halaman_sebelumnya = None

    for block in blocks:
        tipe = block.get("type", "")
        page_idx = block.get("page_idx")

        # Page break antar halaman
        if page_idx is not None and halaman_sebelumnya is not None:
            try:
                if int(page_idx) != int(halaman_sebelumnya):
                    doc.add_page_break()
            except (ValueError, TypeError):
                pass
        if page_idx is not None:
            halaman_sebelumnya = page_idx

        # Skip noise
        if tipe in ("header", "footer", "page_number"):
            continue

        # ─── Blok teks
        if tipe == "text":
            teks = block.get("text", "").strip()
            if not teks:
                continue

            text_level = block.get("text_level")
            bbox = block.get("bbox", [])
            x0 = bbox[0] if bbox else x0_min
            lvl = mapper(x0)

            if text_level == 1:
                # Heading utama MinerU — selalu Word Heading 1
                doc.add_heading(teks, level=1)
                continue

            if text_level == 2:
                # Heading sekunder — jadikan Heading 2 jika di level 0-1,
                # paragraf indent jika lebih ke kanan (sub-item salah label)
                if lvl <= 1:
                    doc.add_heading(teks, level=2)
                else:
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Cm(CM_PER_LEVEL * lvl)
                    p.paragraph_format.space_before = Pt(1)
                    p.paragraph_format.space_after = Pt(1)
                    _tambah_runs(p, teks)
                continue

            # Paragraf biasa
            p = doc.add_paragraph()
            if lvl > 0:
                p.paragraph_format.left_indent = Cm(CM_PER_LEVEL * lvl)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            _tambah_runs(p, teks)

        # ─── Blok tabel
        elif tipe == "table":
            table_body = block.get("table_body", "")
            caption = block.get("table_caption", "")
            if table_body:
                try:
                    _tambah_tabel_html(doc, table_body)
                except Exception:
                    teks_bersih = re.sub(r"<[^>]+>", " ", table_body)
                    teks_bersih = re.sub(r"\s+", " ", teks_bersih).strip()
                    if teks_bersih:
                        doc.add_paragraph(teks_bersih)
            if caption and str(caption) not in ("[]", "", "['']"):
                caption_str = str(caption).strip("[]'\"").strip()
                if caption_str:
                    doc.add_paragraph(caption_str)
            doc.add_paragraph()

        # ─── Blok gambar / stempel
        elif tipe in ("image", "seal"):
            img_path_rel = block.get("img_path", "")
            if img_path_rel:
                img_abs = json_path.parent / img_path_rel
                if img_abs.exists():
                    try:
                        p = doc.add_paragraph()
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p.add_run()
                        lebar = Inches(2) if tipe == "seal" else Inches(4)
                        run.add_picture(str(img_abs), width=lebar)
                    except Exception:
                        pass

    return doc


def content_list_ke_bytes(json_path: Path, judul: str = "") -> bytes:
    """Konversi content_list.json ke bytes DOCX (untuk st.download_button)."""
    doc = content_list_ke_docx(json_path, judul)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def cari_content_list_json(output_dir: Path, stem: str) -> "Path | None":
    """Cari *_content_list.json di folder output MinerU."""
    kandidat = [
        output_dir / stem / "auto" / f"{stem}_content_list.json",
        output_dir / stem / "pipeline" / f"{stem}_content_list.json",
    ]
    for p in kandidat:
        if p.exists():
            return p
    hasil = list((output_dir / stem).rglob("*_content_list.json")) if (output_dir / stem).exists() else []
    if not hasil:
        hasil = list(output_dir.rglob("*_content_list.json"))
    return hasil[0] if hasil else None


# ─────────────────────────────────────────────
# HELPER — TABEL dengan colspan/rowspan
# ─────────────────────────────────────────────

def _tambah_tabel_html(doc: Document, html: str):
    """Parse HTML table MinerU (colspan/rowspan) ke Word Table Grid."""
    baris_tr = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    if not baris_tr:
        return

    parsed_rows = []
    for tr in baris_tr:
        cells_raw = re.findall(
            r"<(td|th)([^>]*)>(.*?)</(?:td|th)>", tr, re.DOTALL | re.IGNORECASE
        )
        row = []
        for tag, attrs, content in cells_raw:
            m_cs = re.search(r'colspan=["\']?(\d+)', attrs, re.I)
            m_rs = re.search(r'rowspan=["\']?(\d+)', attrs, re.I)
            colspan = int(m_cs.group(1)) if m_cs else 1
            rowspan = int(m_rs.group(1)) if m_rs else 1
            teks = re.sub(r"<[^>]+>", " ", content)
            teks = html_lib.unescape(teks)
            teks = re.sub(r"\s+", " ", teks).strip()
            row.append({
                "text": teks,
                "colspan": max(1, colspan),
                "rowspan": max(1, rowspan),
                "header": tag.lower() == "th",
            })
        if row:
            parsed_rows.append(row)

    if not parsed_rows:
        return

    total_cols = max(sum(c["colspan"] for c in row) for row in parsed_rows)
    total_rows = len(parsed_rows)
    if total_cols == 0:
        return

    table = doc.add_table(rows=total_rows, cols=total_cols)
    table.style = "Table Grid"
    occupied = [[False] * total_cols for _ in range(total_rows)]

    for r_idx, row in enumerate(parsed_rows):
        c_grid = 0
        for cell_data in row:
            while c_grid < total_cols and occupied[r_idx][c_grid]:
                c_grid += 1
            if c_grid >= total_cols:
                break

            colspan = cell_data["colspan"]
            rowspan = cell_data["rowspan"]
            word_cell = table.cell(r_idx, c_grid)
            word_cell.text = cell_data["text"][:500]

            if cell_data["header"] or r_idx == 0:
                for run in word_cell.paragraphs[0].runs:
                    run.bold = True

            if colspan > 1 or rowspan > 1:
                end_row = min(r_idx + rowspan - 1, total_rows - 1)
                end_col = min(c_grid + colspan - 1, total_cols - 1)
                if end_row != r_idx or end_col != c_grid:
                    word_cell.merge(table.cell(end_row, end_col))

            for dr in range(rowspan):
                for dc in range(colspan):
                    rr, cc = r_idx + dr, c_grid + dc
                    if rr < total_rows and cc < total_cols:
                        occupied[rr][cc] = True

            c_grid += colspan


# ─────────────────────────────────────────────
# HELPER — INLINE FORMATTING
# ─────────────────────────────────────────────

def _tambah_runs(paragraph, teks: str):
    """Parse **bold**, *italic*, `code` dan tambahkan ke paragraph."""
    pattern = re.compile(r"(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|([^*`]+))")
    for m in pattern.finditer(teks):
        if m.group(2):
            run = paragraph.add_run(m.group(2))
            run.bold = True
        elif m.group(3):
            run = paragraph.add_run(m.group(3))
            run.italic = True
        elif m.group(4):
            run = paragraph.add_run(m.group(4))
            run.font.name = "Courier New"
            run.font.size = Pt(9)
        elif m.group(5):
            paragraph.add_run(m.group(5))
