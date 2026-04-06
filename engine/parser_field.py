"""
engine/parser_field.py — Parser field pengadaan dari teks Markdown
===================================================================
Ekstrak field-field standar dokumen lelang/pengadaan dari teks Markdown
hasil MinerU menggunakan regex pattern matching.

Output: dict yang kompatibel dengan format _import_lpse.json
"""

import re
import json
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def _bersihkan_angka(teks: str) -> Optional[float]:
    """Ubah string rupiah ke float. '1.234.567,00' → 1234567.0"""
    if not teks:
        return None
    teks = re.sub(r"[Rp\s]", "", teks)
    teks = teks.replace(".", "").replace(",", ".")
    try:
        return float(teks)
    except ValueError:
        return None


def _bersihkan_html(teks: str) -> str:
    """Hapus tag HTML dari teks."""
    return re.sub(r"<[^>]+>", " ", teks).strip()


def _cari_pertama(pattern: str, teks: str, flags=re.IGNORECASE) -> Optional[str]:
    """Cari match pertama, return group(1) atau None. Nilai max 200 karakter."""
    m = re.search(pattern, teks, flags)
    if not m:
        return None
    val = m.group(1).strip()
    val = _bersihkan_html(val)
    val = re.sub(r"\s+", " ", val).strip()
    # Buang nilai yang terlalu panjang (bukan nilai field, melainkan paragraf)
    if len(val) > 200:
        return None
    return val if val else None


def _format_rupiah(nilai: float) -> str:
    """Float ke format rupiah Indonesia."""
    if nilai is None:
        return ""
    return f"Rp {nilai:,.0f}".replace(",", ".")


# ─────────────────────────────────────────────
# PARSER UTAMA
# ─────────────────────────────────────────────

def parse_field_pengadaan(teks_markdown: str) -> dict:
    """
    Parse field-field standar dokumen pengadaan dari teks Markdown.

    Returns:
        dict dengan field-field pengadaan
    """
    teks = teks_markdown

    hasil = {
        # Identitas paket
        "nama_paket": None,
        "satuan_kerja": None,
        "kode_rup": None,
        "kode_tender": None,
        "nomor_pengumuman": None,

        # Nilai
        "hps": None,
        "hps_teks": None,
        "pagu": None,
        "pagu_teks": None,

        # Metode & sumber
        "metode_pengadaan": None,
        "metode_evaluasi": None,
        "sumber_dana": None,
        "tahun_anggaran": None,
        "jenis_pengadaan": None,

        # Tanggal-tanggal
        "tanggal_pengumuman": None,
        "tanggal_pendaftaran_mulai": None,
        "tanggal_pendaftaran_akhir": None,
        "tanggal_pemasukan_penawaran": None,
        "tanggal_pembukaan_penawaran": None,
        "tanggal_evaluasi": None,
        "tanggal_penetapan_pemenang": None,

        # Kualifikasi
        "klasifikasi_usaha": None,
        "sub_klasifikasi": None,
        "kualifikasi_usaha": None,
        "lokasi_pekerjaan": None,
    }

    # ─── Nama Paket ───
    hasil["nama_paket"] = (
        _cari_pertama(r"(?:nama\s+paket|nama\s+pekerjaan|paket\s+pekerjaan)[:\s]+(.+?)(?:\n|$)", teks)
        or _cari_pertama(r"(?:pengadaan|pekerjaan)[:\s]+([A-Z][^\n]{10,80})", teks)
    )

    # ─── Satuan Kerja ───
    hasil["satuan_kerja"] = _cari_pertama(
        r"(?:satuan\s+kerja|satker|opd|instansi)[:\s]+(.+?)(?:\n|$)", teks
    )

    # ─── Kode RUP ───
    hasil["kode_rup"] = _cari_pertama(r"(?:kode\s+rup|rup)[:\s#]*(\d{5,15})", teks)

    # ─── Kode Tender ───
    hasil["kode_tender"] = _cari_pertama(
        r"(?:kode\s+tender|nomor\s+tender|id\s+tender)[:\s]+([A-Z0-9\-/\.]{5,30})", teks
    )

    # ─── Nomor Pengumuman ───
    hasil["nomor_pengumuman"] = _cari_pertama(
        r"(?:nomor\s+pengumuman|no\.\s*pengumuman)[:\s]+([^\n]{5,60})", teks
    )

    # ─── HPS ───
    hps_raw = _cari_pertama(
        r"(?:hps|harga\s+perkiraan\s+sendiri)[:\s]+(?:Rp\.?\s*)?([\d.,]+)", teks
    )
    if hps_raw:
        hasil["hps"] = _bersihkan_angka(hps_raw)
        hasil["hps_teks"] = _format_rupiah(hasil["hps"])

    # ─── Pagu ───
    pagu_raw = _cari_pertama(
        r"(?:pagu\s+anggaran|pagu)[:\s]+(?:Rp\.?\s*)?([\d.,]+)", teks
    )
    if pagu_raw:
        hasil["pagu"] = _bersihkan_angka(pagu_raw)
        hasil["pagu_teks"] = _format_rupiah(hasil["pagu"])

    # ─── Metode Pengadaan ───
    hasil["metode_pengadaan"] = _cari_pertama(
        r"(?:metode\s+pengadaan|metode\s+pemilihan|cara\s+pengadaan)[:\s]+(.+?)(?:\n|$)", teks
    )

    # ─── Metode Evaluasi ───
    hasil["metode_evaluasi"] = _cari_pertama(
        r"(?:metode\s+evaluasi|sistem\s+evaluasi)[:\s]+(.+?)(?:\n|$)", teks
    )

    # ─── Sumber Dana ───
    hasil["sumber_dana"] = _cari_pertama(
        r"(?:sumber\s+dana|sumber\s+anggaran)[:\s]+(.+?)(?:\n|$)", teks
    )

    # ─── Tahun Anggaran ───
    hasil["tahun_anggaran"] = _cari_pertama(r"tahun\s+anggaran[:\s]+(\d{4})", teks)
    if not hasil["tahun_anggaran"]:
        hasil["tahun_anggaran"] = _cari_pertama(r"t\.a\.\s*(\d{4})", teks)

    # ─── Jenis Pengadaan ───
    hasil["jenis_pengadaan"] = _cari_pertama(
        r"(?:jenis\s+pengadaan|kategori)[:\s]+(.+?)(?:\n|$)", teks
    )

    # ─── Tanggal-tanggal ───
    pola_tanggal = r"(\d{1,2}[\s\-/](?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|\d{1,2})[\s\-/]\d{4}|\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})"

    hasil["tanggal_pengumuman"] = _cari_pertama(
        rf"(?:pengumuman|tanggal\s+pengumuman)[:\s]+{pola_tanggal}", teks
    )
    hasil["tanggal_pendaftaran_mulai"] = _cari_pertama(
        rf"(?:pendaftaran|download\s+dok)[^\n]*mulai[:\s]+{pola_tanggal}", teks
    )
    hasil["tanggal_pendaftaran_akhir"] = _cari_pertama(
        rf"(?:akhir\s+pendaftaran|penutupan\s+pendaftaran)[:\s]+{pola_tanggal}", teks
    )
    hasil["tanggal_pemasukan_penawaran"] = _cari_pertama(
        rf"(?:pemasukan\s+penawaran|upload\s+dok\s+penawaran)[^\n]*{pola_tanggal}", teks
    )
    hasil["tanggal_pembukaan_penawaran"] = _cari_pertama(
        rf"(?:pembukaan\s+penawaran)[:\s]+{pola_tanggal}", teks
    )
    hasil["tanggal_penetapan_pemenang"] = _cari_pertama(
        rf"(?:penetapan\s+pemenang|pengumuman\s+pemenang)[:\s]+{pola_tanggal}", teks
    )

    # ─── Kualifikasi ───
    hasil["klasifikasi_usaha"] = _cari_pertama(
        r"(?:klasifikasi|bidang\s+usaha)[:\s]+(.+?)(?:\n|$)", teks
    )
    hasil["sub_klasifikasi"] = _cari_pertama(
        r"(?:sub\s+klasifikasi|subbidang)[:\s]+(.+?)(?:\n|$)", teks
    )
    hasil["kualifikasi_usaha"] = _cari_pertama(
        r"(?:kualifikasi\s+usaha|kualifikasi)[:\s]+(.+?)(?:\n|$)", teks
    )
    hasil["lokasi_pekerjaan"] = _cari_pertama(
        r"(?:lokasi\s+pekerjaan|lokasi)[:\s]+(.+?)(?:\n|$)", teks
    )

    # Buang nilai None → kosongkan
    return {k: v for k, v in hasil.items()}


def export_ke_lpse_json(field_dict: dict) -> str:
    """
    Konversi hasil parse ke format JSON yang kompatibel dengan _import_lpse.json
    (format yang dibaca oleh VBA ModWordLink.ImportHTML).
    """
    lpse_format = {
        "nama_paket": field_dict.get("nama_paket") or "",
        "satker": field_dict.get("satuan_kerja") or "",
        "kode_rup": field_dict.get("kode_rup") or "",
        "kode_tender": field_dict.get("kode_tender") or "",
        "hps": field_dict.get("hps") or 0,
        "pagu": field_dict.get("pagu") or 0,
        "metode_pengadaan": field_dict.get("metode_pengadaan") or "",
        "metode_evaluasi": field_dict.get("metode_evaluasi") or "",
        "sumber_dana": field_dict.get("sumber_dana") or "",
        "tahun_anggaran": field_dict.get("tahun_anggaran") or "",
        "jenis_pengadaan": field_dict.get("jenis_pengadaan") or "",
        "lokasi_pekerjaan": field_dict.get("lokasi_pekerjaan") or "",
        "kualifikasi_usaha": field_dict.get("kualifikasi_usaha") or "",
        "klasifikasi": field_dict.get("klasifikasi_usaha") or "",
        "tanggal_pengumuman": field_dict.get("tanggal_pengumuman") or "",
        "tanggal_pendaftaran_mulai": field_dict.get("tanggal_pendaftaran_mulai") or "",
        "tanggal_pendaftaran_akhir": field_dict.get("tanggal_pendaftaran_akhir") or "",
        "tanggal_pemasukan": field_dict.get("tanggal_pemasukan_penawaran") or "",
        "tanggal_pembukaan": field_dict.get("tanggal_pembukaan_penawaran") or "",
        "tanggal_penetapan_pemenang": field_dict.get("tanggal_penetapan_pemenang") or "",
    }
    return json.dumps(lpse_format, ensure_ascii=False, indent=2)


def hitung_kelengkapan(field_dict: dict) -> tuple[int, int]:
    """Return (field_terisi, total_field) untuk indikator kelengkapan."""
    total = len(field_dict)
    terisi = sum(1 for v in field_dict.values() if v is not None and v != "")
    return terisi, total
