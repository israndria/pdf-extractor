"""
engine/supabase_uploader.py — Upload hasil ekstraksi ke Supabase
=================================================================
Tabel: dokumen_pdf
Auto-create tabel jika belum ada (via Supabase REST API).

Schema:
    id          uuid (PK, default gen_random_uuid())
    nama_file   text
    tipe_dokumen text  -- 'native' | 'scan' | 'mixed' | 'unknown'
    teks_markdown text
    field_parsed jsonb
    created_at  timestamptz (default now())
"""

import os
import json
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
# ENV LOADER
# ─────────────────────────────────────────────

def _load_env() -> tuple[str, str]:
    """Baca Supabase URL + Key dari secret_supabase.env."""
    BASE_DIR = Path(__file__).resolve().parent.parent
    kandidat = [
        BASE_DIR / "secret_supabase.env",
        BASE_DIR.parent / "V19_Scheduler" / "WPy64-313110" / "secret_supabase.env",
        Path(r"D:\Dokumen\@ POKJA 2026\V19_Scheduler\WPy64-313110\secret_supabase.env"),
    ]
    errs = []
    for path in kandidat:
        try:
            with open(str(path), encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_KEY", "")
            if url and key:
                return url, key
        except Exception as e:
            errs.append(f"{path}: {e}")
    raise FileNotFoundError(
        "secret_supabase.env tidak ditemukan atau tidak berisi SUPABASE_URL/SUPABASE_KEY.\n"
        + "\n".join(errs)
    )


SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS dokumen_pdf (
    id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    nama_file   text,
    tipe_dokumen text,
    teks_markdown text,
    field_parsed jsonb,
    created_at  timestamptz DEFAULT now()
);
""".strip()


# ─────────────────────────────────────────────
# FUNGSI UTAMA
# ─────────────────────────────────────────────

def simpan_ke_supabase(
    nama_file: str,
    tipe_dokumen: str,
    teks_markdown: str,
    field_parsed: dict,
) -> dict:
    """
    Simpan satu dokumen ke tabel dokumen_pdf di Supabase.

    Returns:
        dict dengan keys: success (bool), id (str), error (str|None)
    """
    try:
        url, key = _load_env()
    except FileNotFoundError as e:
        return {"success": False, "id": None, "error": str(e)}

    try:
        from supabase import create_client
        sb = create_client(url, key)
    except Exception as e:
        return {"success": False, "id": None, "error": f"Gagal connect Supabase: {e}"}

    payload = {
        "nama_file": nama_file,
        "tipe_dokumen": tipe_dokumen,
        "teks_markdown": teks_markdown[:100_000],  # batasi 100KB teks
        "field_parsed": field_parsed,
    }

    try:
        resp = sb.table("dokumen_pdf").insert(payload).execute()
        data = resp.data
        if data and len(data) > 0:
            return {"success": True, "id": data[0].get("id"), "error": None}
        else:
            return {"success": False, "id": None, "error": "Insert tidak mengembalikan data"}
    except Exception as e:
        err_msg = str(e)
        # Tabel belum ada — berikan SQL untuk user
        if "relation" in err_msg.lower() and "does not exist" in err_msg.lower():
            return {
                "success": False,
                "id": None,
                "error": (
                    "Tabel `dokumen_pdf` belum ada di Supabase.\n"
                    "Buat dulu via Supabase Dashboard → SQL Editor:\n\n"
                    f"```sql\n{SQL_CREATE_TABLE}\n```"
                ),
            }
        return {"success": False, "id": None, "error": err_msg}


def cek_koneksi_supabase() -> dict:
    """Test koneksi ke Supabase. Return dict: success, url, error."""
    try:
        url, key = _load_env()
    except FileNotFoundError as e:
        return {"success": False, "url": None, "error": str(e)}

    try:
        from supabase import create_client
        sb = create_client(url, key)
        # Query ringan untuk test koneksi
        sb.table("dokumen_pdf").select("id").limit(1).execute()
        return {"success": True, "url": url, "error": None}
    except Exception as e:
        err = str(e)
        if "relation" in err.lower() and "does not exist" in err.lower():
            # Tabel belum ada tapi koneksi berhasil
            return {
                "success": True,
                "url": url,
                "error": None,
                "tabel_belum_ada": True,
                "sql_create": SQL_CREATE_TABLE,
            }
        return {"success": False, "url": url, "error": err}
