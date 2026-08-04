import os
import re
import tempfile
from pathlib import Path
from typing import Tuple, List

import pysubs2
from pysubs2.exceptions import Pysubs2Error

from translation_engine import translate_subs


def normalize_subtitle(input_path: str, output_path: str) -> Tuple[str, str]:
    """
    Forcefully standardizes subtitles to UTF-8.
    Handles multiple scripts (Latin/French, Thai, etc.) by detecting script type
    and choosing appropriate encoding candidates.

    Returns:
        Tuple of (output_path, detected_encoding)
    """
    with open(input_path, "rb") as f:
        raw_data = f.read()

    # Try charset_normalizer first
    detected_enc = None
    try:
        from charset_normalizer import from_bytes
        result = from_bytes(raw_data).best()
        if result:
            detected_enc = str(result.encoding)
    except (ImportError, TypeError, ValueError):
        pass

    # Fallback to chardet if available
    if not detected_enc:
        try:
            import chardet
            detection = chardet.detect(raw_data)
            detected_enc = detection.get('encoding')
        except (ImportError, TypeError, ValueError):
            pass

    # Detect script type by checking for Thai byte patterns
    # Thai characters are in Unicode range U+0E00 to U+0E7F
    # In UTF-8, they appear as bytes 0xE0 0xB8-0xBB
    has_thai_bytes = any(raw_data[i:i+2] == b'\xe0\xb8' or
                          raw_data[i:i+2] == b'\xe0\xb9' or
                          raw_data[i:i+2] == b'\xe0\xba' or
                          raw_data[i:i+2] == b'\xe0\xbb'
                          for i in range(len(raw_data) - 1))

    # Check for other Asian scripts
    has_chinese_bytes = any(raw_data[i:i+3].startswith(b'\xe4') or
                             raw_data[i:i+3].startswith(b'\xe5') or
                             raw_data[i:i+3].startswith(b'\xe9')
                             for i in range(len(raw_data) - 2))

    # Check if detected encoding suggests Thai
    is_thai_encoding = detected_enc and ('874' in detected_enc.lower() or
                                          'thai' in detected_enc.lower() or
                                          'tis' in detected_enc.lower())

    # Build encoding list based on script detection
    if has_thai_bytes or is_thai_encoding:
        # Thai subtitle - prioritize UTF-8 and Thai-specific encodings
        encodings_to_try = ['utf-8', 'tis-620', 'cp874', 'iso-8859-11', detected_enc]
    elif has_chinese_bytes:
        # Chinese subtitle
        encodings_to_try = ['utf-8', 'gb2312', 'gbk', 'big5', detected_enc]
    else:
        # Latin/French subtitle - prioritize UTF-8 first (most modern files), then fallback to legacy encodings
        encodings_to_try = ['utf-8', detected_enc, 'cp1252', 'windows-1252', 'iso-8859-1', 'latin-1', 'iso-8859-15']

    # Remove duplicates while preserving order
    seen = set()
    encodings_to_try = [x for x in encodings_to_try if x and x.lower() not in seen and not seen.add(x.lower())]

    # Corruption patterns to detect
    # These patterns indicate the file was INCORRECTLY decoded/encoded
    # Eastern European chars that shouldn't appear in French text (indicates wrong codepage)
    western_corruption = ['ť', 'Ť', 'ŕ', 'Ŕ', 'č', 'Č', 'ś', 'Ś', 'ř', 'Ř', 'ů', 'Ů', '¶', 'Ķ', 'ķ']

    # Garbage characters that indicate Thai encoding issues
    thai_corruption = ['à¸', 'à¹', 'Ã ', 'Ã¡', 'Ã¨', 'Ã©']

    subs = None
    best_encoding = None

    for enc in encodings_to_try:
        try:
            subs = pysubs2.load(input_path, encoding=enc)

            # Sample first 20 lines or all if fewer
            sample_size = min(20, len(subs))
            test_text = "".join([l.text for l in subs[:sample_size]])

            # Check for corruption patterns based on detected script type
            if has_thai_bytes or is_thai_encoding:
                has_corruption = any(pattern in test_text for pattern in thai_corruption)
            else:
                has_corruption = any(pattern in test_text for pattern in western_corruption)

            # Additional check: if we expect Thai but see only ASCII/Latin, it's wrong
            if (has_thai_bytes or is_thai_encoding) and enc in ['cp1252', 'iso-8859-1', 'latin-1']:
                has_thai_chars = any(ord(c) >= 0x0E00 and ord(c) <= 0x0E7F for c in test_text)
                if not has_thai_chars:
                    continue  # Skip this encoding, it lost Thai characters

            # If no corruption detected, we found the right encoding
            if not has_corruption:
                best_encoding = enc
                break

        except (OSError, UnicodeError, LookupError, Pysubs2Error):
            continue

    # If all encodings showed corruption or failed, use smart fallback
    if subs is None or best_encoding is None:
        if has_thai_bytes or is_thai_encoding:
            try:
                subs = pysubs2.load(input_path, encoding='utf-8')
                best_encoding = 'utf-8'
            except (OSError, UnicodeError, LookupError, Pysubs2Error):
                subs = pysubs2.load(input_path, encoding='tis-620')
                best_encoding = 'tis-620'
        else:
            try:
                subs = pysubs2.load(input_path, encoding='cp1252')
                best_encoding = 'cp1252'
            except (OSError, UnicodeError, LookupError, Pysubs2Error):
                subs = pysubs2.load(input_path, encoding='latin-1')
                best_encoding = 'latin-1'

    # Standardize internal line breaks
    for line in subs:
        line.text = line.text.replace("\r\n", "\n").replace("\r", "\n")

    # Save as UTF-8 without BOM
    subs.save(output_path, encoding="utf-8")

    return output_path, best_encoding or 'unknown'


def validate_subtitle_file(file_path: str) -> Tuple[bool, str]:
    """
    Validate that a subtitle file is properly formatted

    Returns:
        Tuple of (is_valid, message)
    """
    try:
        subs = pysubs2.load(file_path, encoding="utf-8")

        if len(subs) == 0:
            return False, "File contains no subtitle entries"

        # Check for basic formatting issues
        issues = []

        # Check for overlapping subtitles
        for i in range(len(subs) - 1):
            if subs[i].end > subs[i+1].start:
                issues.append(f"Overlap at entry {i+1}")

        # Check for negative durations
        for i, line in enumerate(subs):
            if line.end <= line.start:
                issues.append(f"Invalid duration at entry {i+1}")

        if issues:
            return True, f"Warning: {', '.join(issues[:3])}" + (f" (+{len(issues)-3} more)" if len(issues) > 3 else "")

        return True, f"Valid subtitle file ({len(subs)} entries)"

    except (OSError, UnicodeError, ValueError, Pysubs2Error) as error:
        return False, f"Parse error: {error}"


def extract_episode_code(filename: str) -> str:
    """
    Extract episode/season code from filename
    Supports formats: S01E01, 1x01, E01, etc.
    """
    # Try multiple patterns in order of specificity
    patterns = [
        r'[sS]\d+[eE]\d+',  # S01E01
        r'\d+[xX]\d+',      # 1x01
        r'[eE]\d+',         # E01
        r'\d{3,4}'          # 001 or 0001
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(0).upper()

    # If no pattern matches, use filename without extension as code
    return os.path.splitext(filename)[0]


def shift_subtitles(subs, shift_ms: int, speed_factor: float = 1.0):
    """
    Shift subtitle timing and/or adjust speed

    Args:
        subs: pysubs2.SSAFile object
        shift_ms: Milliseconds to shift (positive = later, negative = earlier)
        speed_factor: Speed multiplier (>1.0 = slower, <1.0 = faster)

    Returns:
        Modified subs object
    """
    if shift_ms == 0 and speed_factor == 1.0:
        return subs

    for line in subs:
        # Apply speed factor first, then shift
        line.start = int(line.start * speed_factor) + shift_ms
        line.end = int(line.end * speed_factor) + shift_ms

        # Ensure times don't go negative
        if line.start < 0:
            line.start = 0
        if line.end < 0:
            line.end = 0

    return subs


def merge_subtitles(path_a: str, path_b: str, output_path: str,
                     threshold_ms: int = 1000,
                     color_hex: str = "#ffff54",
                     color_track: str = "Track B",
                     shift_a: int = 0,
                     shift_b: int = 0,
                     shift_global: int = 0) -> int:
    """
    Merge two subtitle files with alignment and coloring

    Args:
        path_a, path_b: Input subtitle file paths
        output_path: Output file path
        threshold_ms: Maximum time difference to consider subs as matching
        color_hex: Color for highlighted track
        color_track: Which track to colorize ("Track A", "Track B", or "None")
        shift_a, shift_b, shift_global: Timing adjustments in milliseconds

    Returns:
        Number of merged subtitle entries
    """
    # Normalized files are now GUARANTEED UTF-8
    subs_a = pysubs2.load(path_a, encoding="utf-8")
    subs_b = pysubs2.load(path_b, encoding="utf-8")

    # Apply individual track shifts
    shift_subtitles(subs_a, shift_a)
    shift_subtitles(subs_b, shift_b)

    # Apply color tags
    if color_track == "Track A":
        for line in subs_a:
            line.text = f'<font color="{color_hex}">{line.text.strip()}</font>'
    elif color_track == "Track B":
        for line in subs_b:
            line.text = f'<font color="{color_hex}">{line.text.strip()}</font>'

    # Merge Logic: Match subtitles within threshold
    matched_indices_b = set()

    for line_a in subs_a:
        best_match = None
        best_diff = threshold_ms + 1

        for idx, line_b in enumerate(subs_b):
            if idx in matched_indices_b:
                continue

            time_diff = abs(line_a.start - line_b.start)
            if time_diff <= threshold_ms and time_diff < best_diff:
                best_match = idx
                best_diff = time_diff

        if best_match is not None:
            # Merge the matched subtitle
            line_b = subs_b[best_match]
            line_a.text = f"{line_a.text.strip()}\n{line_b.text.strip()}"
            matched_indices_b.add(best_match)

    # Add unmatched subtitles from Track B
    for idx, line_b in enumerate(subs_b):
        if idx not in matched_indices_b:
            subs_a.append(line_b)

    # Apply global shift and sort
    shift_subtitles(subs_a, shift_global)
    subs_a.sort()

    # Save as UTF-8 WITHOUT BOM (most players prefer this)
    subs_a.save(output_path, encoding="utf-8")

    return len(subs_a)


def remove_duplicates(subs, time_threshold_ms: int = 100) -> int:
    """
    Remove duplicate subtitle entries based on timing and text

    Returns:
        Number of duplicates removed
    """
    unique_lines = []
    duplicates_removed = 0

    for line in subs:
        is_duplicate = False
        for unique_line in unique_lines:
            # Check if timing is very similar and text is identical
            if (abs(line.start - unique_line.start) <= time_threshold_ms and
                abs(line.end - unique_line.end) <= time_threshold_ms and
                line.text.strip() == unique_line.text.strip()):
                is_duplicate = True
                duplicates_removed += 1
                break

        if not is_duplicate:
            unique_lines.append(line)

    subs.lines = unique_lines
    return duplicates_removed


def fix_common_issues(subs) -> List[str]:
    """
    Fix common subtitle issues

    Returns:
        List of fixes applied
    """
    fixes = []

    # Fix 1: Remove lines with only whitespace
    original_count = len(subs)
    subs.lines = [line for line in subs if line.text.strip()]
    if len(subs) < original_count:
        fixes.append(f"Removed {original_count - len(subs)} empty lines")

    # Fix 2: Normalize whitespace
    for line in subs:
        new_text = ' '.join(line.text.split())
        if new_text != line.text:
            line.text = new_text

    # Fix 3: Fix negative durations
    fixed_durations = 0
    for line in subs:
        if line.end <= line.start:
            line.end = line.start + 1000  # Set to 1 second duration
            fixed_durations += 1
    if fixed_durations > 0:
        fixes.append(f"Fixed {fixed_durations} invalid durations")

    return fixes


def _save_repaired_subtitles(repaired_text: str, output_path: str) -> int:
    """Parse, validate, and atomically save repaired subtitle text."""
    subtitles = pysubs2.SSAFile.from_string(repaired_text)
    if not subtitles:
        raise ValueError("Repair produced no subtitle entries")
    if not any(event.text.strip() for event in subtitles):
        raise ValueError("Repair produced subtitle entries without text")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.stem}-",
            suffix=destination.suffix or ".srt",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        subtitles.save(str(temporary_path), encoding="utf-8")
        if temporary_path.stat().st_size == 0:
            raise ValueError("Repair produced an empty subtitle file")

        reloaded = pysubs2.load(str(temporary_path), encoding="utf-8")
        if not reloaded:
            raise ValueError("Saved repair contains no subtitle entries")

        os.replace(temporary_path, destination)
        temporary_path = None
        return len(reloaded)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _contains_script(text: str, script: str) -> bool:
    sample = text[:5000]
    if script == "thai":
        return any("\u0E00" <= character <= "\u0E7F" for character in sample)
    if script == "french":
        return any(character in "éèêëàâäôöùûüÿçœæÉÈÊËÀÂÄÔÖÙÛÜŸÇŒÆ" for character in sample)
    if script == "chinese":
        return any("\u3400" <= character <= "\u9FFF" for character in sample)
    return False


def _detect_target_script(raw_data: bytes) -> str:
    """Infer the intended script conservatively for automatic repair."""
    decoded_views = []
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            decoded_views.append(raw_data.decode(encoding))
        except UnicodeDecodeError:
            continue

    for script in ("thai", "chinese", "french"):
        if any(_contains_script(view, script) for view in decoded_views):
            return script

    try:
        import chardet

        encoding = (chardet.detect(raw_data).get("encoding") or "").lower()
        if any(value in encoding for value in ("874", "tis-620", "thai")):
            return "thai"
        if any(value in encoding for value in ("1252", "8859-1", "latin")):
            return "french"
        if any(value in encoding for value in ("gb", "big5", "chinese")):
            return "chinese"
    except (ImportError, TypeError, ValueError):
        pass
    return "unknown"


def _mojibake_score(text: str) -> int:
    markers = ("Ã", "Â", "â€", "à¸", "à¹", "�")
    return sum(text.count(marker) for marker in markers)


def _iter_mojibake_repairs(raw_data: bytes):
    """Yield strictly reversible UTF-8 mojibake repair candidates."""
    seen = set()
    for initial_encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            initial = raw_data.decode(initial_encoding)
        except UnicodeDecodeError:
            continue

        for source_encoding in ("latin-1", "cp1252"):
            current = initial
            for depth in (1, 2):
                try:
                    candidate = current.encode(source_encoding).decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    break
                if candidate == current:
                    break
                key = (source_encoding, candidate)
                if key not in seen and _mojibake_score(candidate) < _mojibake_score(current):
                    seen.add(key)
                    yield f"{initial_encoding}_{source_encoding}_pass{depth}", candidate
                current = candidate


def repair_corrupted_encoding(input_path: str, output_path: str, target_script: str = "auto") -> Tuple[bool, str, str]:
    """
    Attempt to repair badly corrupted subtitle files by trying multiple decoding strategies.
    This handles double-encoding, mojibake, and other encoding disasters.

    Args:
        input_path: Path to corrupted subtitle file
        output_path: Where to save repaired file
        target_script: "thai", "french", "chinese", or "auto" for auto-detection

    Returns:
        Tuple of (success, detected_corruption_type, applied_fix)
    """
    with open(input_path, "rb") as f:
        raw_data = f.read()

    if not raw_data:
        return False, "empty_input", "none"
    if target_script not in {"auto", "thai", "french", "chinese"}:
        raise ValueError(f"Unsupported target script: {target_script}")
    effective_target = (
        _detect_target_script(raw_data) if target_script == "auto" else target_script
    )

    corruption_type = "none"
    applied_fix = "none"

    # Strategy 1: Undo one or two reversible UTF-8 mojibake passes.
    for method, repaired_data in _iter_mojibake_repairs(raw_data):
        repaired_script = effective_target
        if repaired_script == "unknown":
            repaired_script = next(
                (
                    script
                    for script in ("thai", "chinese", "french")
                    if _contains_script(repaired_data, script)
                ),
                "unknown",
            )
        if repaired_script != "unknown" and _contains_script(repaired_data, repaired_script):
            try:
                _save_repaired_subtitles(repaired_data, output_path)
            except (ValueError, Pysubs2Error):
                continue
            return True, "double_encoding", f"repaired_{repaired_script}_{method}"

    # Strategy 2: Try all common Thai encoding combinations
    if effective_target == "thai":
        for encoding in ("tis-620", "cp874", "iso-8859-11"):
            try:
                # Decode the original bytes directly with the candidate legacy
                # encoding. Re-encoding and decoding as UTF-8 would simply
                # recreate the original bytes and can silently discard text.
                repaired_data = raw_data.decode(encoding)

                # Verify Thai characters present
                if any('\u0E00' <= c <= '\u0E7F' for c in repaired_data[:500]):
                    _save_repaired_subtitles(repaired_data, output_path)
                    corruption_type = "wrong_encoding"
                    applied_fix = f"decoded_{encoding}"
                    return True, corruption_type, applied_fix
            except (LookupError, UnicodeDecodeError, ValueError, Pysubs2Error):
                continue

    # Strategy 3: Try all common Western European encoding combinations
    if effective_target == "french":
        for encoding in ("cp1252", "iso-8859-15", "latin-1"):
            try:
                repaired_data = raw_data.decode(encoding)

                # Verify French characters present
                if any(c in 'éèêëàâäôöùûüÿçœæ' for c in repaired_data[:500]):
                    _save_repaired_subtitles(repaired_data, output_path)
                    corruption_type = "wrong_encoding"
                    applied_fix = f"decoded_{encoding}"
                    return True, corruption_type, applied_fix
            except (LookupError, UnicodeDecodeError, ValueError, Pysubs2Error):
                continue

    # Strategy 4: Decode common Chinese legacy encodings strictly.
    if effective_target == "chinese":
        for encoding in ("gb18030", "big5", "gbk"):
            try:
                repaired_data = raw_data.decode(encoding)
                if _contains_script(repaired_data, "chinese"):
                    _save_repaired_subtitles(repaired_data, output_path)
                    return True, "wrong_encoding", f"decoded_{encoding}"
            except (LookupError, UnicodeDecodeError, ValueError, Pysubs2Error):
                continue

    # Strategy 5: Last resort - use the general normalizer.
    try:
        normalize_subtitle(input_path, output_path)
        valid, validation_message = validate_subtitle_file(output_path)
        if not valid or Path(output_path).stat().st_size == 0:
            raise ValueError(validation_message)
        corruption_type = "encoding_mismatch"
        applied_fix = "normalize_subtitle_fallback"
        return True, corruption_type, applied_fix
    except (OSError, UnicodeError, ValueError, Pysubs2Error):
        return False, "unrepairable", "none"


def analyze_corruption(file_path: str) -> dict:
    """Analyze encoding, likely script, mojibake, and subtitle structure."""
    try:
        raw_data = Path(file_path).read_bytes()
    except OSError as error:
        return {
            "error": str(error),
            "corruption_indicators": ["Unable to read file"],
            "recommendations": ["Check if the file is accessible"],
        }

    analysis = {
        "file_size_bytes": len(raw_data),
        "corruption_indicators": [],
        "detected_script": _detect_target_script(raw_data),
        "detected_encoding": "unknown",
        "confidence": 0,
        "recommendations": [],
    }
    if not raw_data:
        analysis["error"] = "File is empty"
        analysis["corruption_indicators"].append("Empty input")
        analysis["recommendations"].append("Upload a non-empty subtitle file")
        return analysis

    try:
        from charset_normalizer import from_bytes

        match = from_bytes(raw_data).best()
        if match is not None:
            analysis["detected_encoding"] = str(match.encoding or "unknown")
    except (ImportError, TypeError, ValueError):
        pass

    try:
        utf8_view = raw_data.decode("utf-8-sig")
    except UnicodeDecodeError:
        analysis["corruption_indicators"].append("Not valid UTF-8")
        analysis["recommendations"].append("Decode and save the file as UTF-8")
        analysis["confidence"] = 70 if analysis["detected_script"] != "unknown" else 40
        return analysis

    analysis["detected_encoding"] = "utf-8"
    if _mojibake_score(utf8_view) > 0:
        analysis["corruption_indicators"].append("Likely UTF-8 mojibake")
        analysis["recommendations"].append("Run Analyze & Repair")
        analysis["confidence"] = 85
    else:
        analysis["corruption_indicators"].append("None - file appears clean")
        analysis["recommendations"].append("No encoding repair is needed")
        analysis["confidence"] = 100

    try:
        subtitles = pysubs2.SSAFile.from_string(utf8_view)
        analysis["subtitle_entries"] = len(subtitles)
        if not subtitles:
            analysis["corruption_indicators"].append("No subtitle entries detected")
            analysis["recommendations"].append("Verify the subtitle format")
    except Pysubs2Error as error:
        analysis["subtitle_entries"] = 0
        analysis["corruption_indicators"].append("Subtitle format could not be parsed")
        analysis["recommendations"].append(str(error))

    return analysis
