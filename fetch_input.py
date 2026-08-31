"""
fetch_input.py

The ONLY environment-aware piece of this project. Everything else
(run_pipeline.py, data_loader.py, derived_quantities.py, ...) just
takes a local file path and doesn't know or care whether it's running
on your laptop or a GitHub Actions runner.

resolve_input() accepts:
  - a plain local path            -> returned as-is (local dev case)
  - a Google Drive file ID/URL    -> downloaded via gdown into work_dir
  - a plain http(s) URL           -> downloaded via requests

This keeps large COMSOL exports OUT of git entirely. In CI, the file
lives in Drive (or any storage you like); the workflow calls this with
the Drive reference, gets a local path back, and everything downstream
runs identically to a local run.

For a PRIVATE Drive file, gdown needs either "anyone with the link" 
sharing, or you switch to an OAuth/service-account flow (rclone with a
service-account JSON is the common CI pattern - see the workflow yaml
for where that would plug in; not implemented here since it's mostly
CI configuration, not Python).
"""

from __future__ import annotations

import re
from pathlib import Path


def _is_google_drive_ref(ref: str) -> str | None:
    """Returns a Drive file ID if ref is a Drive URL or bare ID, else None."""
    m = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", ref)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", ref)
    if m:
        return m.group(1)
    # bare Drive file IDs are long alnum/-/_ strings with no path separators
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", ref):
        return ref
    return None


def resolve_input(ref: str, work_dir: str | Path = "workdir_downloads") -> Path:
    local_path = Path(ref)
    if local_path.exists():
        print(f"[fetch_input] using local file: {local_path}")
        return local_path

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    drive_id = _is_google_drive_ref(ref)
    if drive_id:
        import gdown
        out_path = work_dir / f"{drive_id}.dat"
        print(f"[fetch_input] downloading Drive file {drive_id} -> {out_path}")
        gdown.download(id=drive_id, output=str(out_path), quiet=False)
        return out_path

    if ref.startswith("http://") or ref.startswith("https://"):
        import requests
        out_path = work_dir / Path(ref.split("?")[0]).name
        print(f"[fetch_input] downloading {ref} -> {out_path}")
        with requests.get(ref, stream=True) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        return out_path

    raise FileNotFoundError(
        f"'{ref}' is not a local file, a Drive URL/ID, or an http(s) URL."
    )