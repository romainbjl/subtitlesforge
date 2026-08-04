from __future__ import annotations

from pathlib import Path

import pytest

from file_utils import (
    read_nonempty_bytes,
    safe_filename,
    save_uploaded_file,
    temporary_workspace,
)


class UploadedFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self) -> memoryview:
        return memoryview(self._data)


def test_safe_filename_removes_paths_and_unsafe_characters() -> None:
    assert safe_filename("../../bad:name?.srt") == "bad_name_.srt"
    assert safe_filename(r"..\folder\episode 01.srt") == "episode 01.srt"
    assert safe_filename("คำบรรยายไทย.srt") == "คำบรรยายไทย.srt"


def test_temporary_workspace_is_removed() -> None:
    with temporary_workspace("test") as workspace:
        path = workspace
        (workspace / "file.srt").write_text("data", encoding="utf-8")
        assert workspace.exists()

    assert not path.exists()


def test_save_uploaded_file_uses_isolated_safe_name(tmp_path: Path) -> None:
    upload = UploadedFile("../episode.ass", b"subtitle")

    path = save_uploaded_file(upload, tmp_path)

    assert path.parent == tmp_path
    assert path.name == "input.ass"
    assert path.read_bytes() == b"subtitle"


def test_empty_upload_and_output_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is empty"):
        save_uploaded_file(UploadedFile("empty.srt", b""), tmp_path)

    output = tmp_path / "empty-output.srt"
    output.write_bytes(b"")
    with pytest.raises(ValueError, match="is empty"):
        read_nonempty_bytes(output)
