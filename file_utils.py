"""Safe, session-isolated file helpers for the Streamlit interface."""

from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_UNSAFE_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1F]+")


def safe_filename(filename: str, fallback: str = "subtitle.srt") -> str:
    """Return a basename suitable for downloads and temporary paths."""
    basename = Path(filename.replace("\\", "/")).name.strip()
    sanitized = _UNSAFE_FILENAME.sub("_", basename).strip(". ")
    return sanitized or fallback


@contextmanager
def temporary_workspace(prefix: str) -> Iterator[Path]:
    """Yield an isolated workspace and remove it when processing finishes."""
    with tempfile.TemporaryDirectory(prefix=f"subtitlesforge-{prefix}-") as directory:
        yield Path(directory)


def save_uploaded_file(uploaded_file, directory: Path, stem: str = "input") -> Path:
    """Persist a Streamlit upload inside an isolated workspace."""
    original_name = safe_filename(uploaded_file.name)
    suffix = Path(original_name).suffix.lower() or ".srt"
    destination = directory / f"{safe_filename(stem, 'input')}{suffix}"
    destination.write_bytes(bytes(uploaded_file.getbuffer()))
    if destination.stat().st_size == 0:
        raise ValueError(f"Uploaded file {original_name!r} is empty")
    return destination


def read_nonempty_bytes(path: Path) -> bytes:
    """Read a generated file and reject empty output."""
    data = path.read_bytes()
    if not data:
        raise ValueError(f"Generated file {path.name!r} is empty")
    return data
