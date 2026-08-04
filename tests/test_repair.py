from __future__ import annotations

from pathlib import Path

import pysubs2
import pytest

from sub_engine import analyze_corruption, repair_corrupted_encoding


def srt(text: str) -> str:
    return f"1\n00:00:01,000 --> 00:00:03,000\n{text}\n"


def load_text(path: Path) -> str:
    subtitles = pysubs2.load(str(path), encoding="utf-8")
    assert len(subtitles) == 1
    return subtitles[0].text


@pytest.mark.parametrize(
    ("text", "target"),
    [
        ("C'est très agréable", "french"),
        ("ผมพูดภาษาไทย", "thai"),
    ],
)
def test_repairs_utf8_mojibake_without_empty_output(
    tmp_path: Path, text: str, target: str
) -> None:
    source = tmp_path / "corrupted.srt"
    output = tmp_path / "repaired.srt"
    mojibake = srt(text).encode("utf-8").decode("latin-1")
    source.write_text(mojibake, encoding="utf-8")

    success, corruption_type, method = repair_corrupted_encoding(
        str(source), str(output), target
    )

    assert success is True
    assert corruption_type == "double_encoding"
    assert method.startswith(f"repaired_{target}_")
    assert output.stat().st_size > 0
    assert load_text(output) == text


@pytest.mark.parametrize(
    ("text", "encoding", "target"),
    [
        ("Déjà à la maison", "cp1252", "french"),
        ("ภาษาไทย", "cp874", "thai"),
        ("中文字幕", "gb18030", "chinese"),
    ],
)
def test_repairs_legacy_encoded_subtitles(
    tmp_path: Path, text: str, encoding: str, target: str
) -> None:
    source = tmp_path / "legacy.srt"
    output = tmp_path / "repaired.srt"
    source.write_bytes(srt(text).encode(encoding))

    success, corruption_type, method = repair_corrupted_encoding(
        str(source), str(output), target
    )

    assert success is True
    assert corruption_type == "wrong_encoding"
    assert method.startswith("decoded_")
    assert load_text(output) == text


def test_auto_mode_repairs_double_encoded_french(tmp_path: Path) -> None:
    source = tmp_path / "auto.srt"
    output = tmp_path / "repaired.srt"
    text = "Voilà déjà l'été"
    source.write_text(srt(text).encode("utf-8").decode("latin-1"), encoding="utf-8")

    success, _, _ = repair_corrupted_encoding(str(source), str(output), "auto")

    assert success is True
    assert load_text(output) == text


def test_rejects_empty_input(tmp_path: Path) -> None:
    source = tmp_path / "empty.srt"
    output = tmp_path / "repaired.srt"
    source.write_bytes(b"")

    result = repair_corrupted_encoding(str(source), str(output), "auto")

    assert result == (False, "empty_input", "none")
    assert not output.exists()


def test_analysis_reports_clean_utf8_and_entry_count(tmp_path: Path) -> None:
    source = tmp_path / "clean.srt"
    source.write_text(srt("Bonjour déjà"), encoding="utf-8")

    analysis = analyze_corruption(str(source))

    assert analysis["detected_encoding"] == "utf-8"
    assert analysis["subtitle_entries"] == 1
    assert analysis["corruption_indicators"] == ["None - file appears clean"]


def test_analysis_reports_mojibake(tmp_path: Path) -> None:
    source = tmp_path / "mojibake.srt"
    corrupted = srt("Déjà").encode("utf-8").decode("latin-1")
    source.write_text(corrupted, encoding="utf-8")

    analysis = analyze_corruption(str(source))

    assert "Likely UTF-8 mojibake" in analysis["corruption_indicators"]

