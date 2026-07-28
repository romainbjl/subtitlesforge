import pysubs2
import re
import requests
import os
from typing import Tuple, Optional, List


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
    except:
        pass

    # Fallback to chardet if available
    if not detected_enc:
        try:
            import chardet
            detection = chardet.detect(raw_data)
            detected_enc = detection.get('encoding')
        except:
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

        except Exception as e:
            continue

    # If all encodings showed corruption or failed, use smart fallback
    if subs is None or best_encoding is None:
        if has_thai_bytes or is_thai_encoding:
            try:
                subs = pysubs2.load(input_path, encoding='utf-8')
                best_encoding = 'utf-8'
            except:
                try:
                    subs = pysubs2.load(input_path, encoding='tis-620')
                    best_encoding = 'tis-620'
                except:
                    subs = pysubs2.load(input_path, encoding='utf-8', errors='ignore')
                    best_encoding = 'utf-8'
        else:
            try:
                subs = pysubs2.load(input_path, encoding='cp1252')
                best_encoding = 'cp1252'
            except:
                subs = pysubs2.load(input_path, encoding='latin-1', errors='ignore')
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

    except Exception as e:
        return False, f"Parse error: {str(e)}"


def translate_subs(subs, base_url, model, source_lang, target_lang, context_info="", batch_size=1):
    """
    Translate subtitles using a local LLM API.

    Tuned for narrowly fine-tuned translation models (e.g. Typhoon Translate 1.5),
    which expect a minimal system prompt ("Translate the following text into X.")
    and the raw source text as the user turn -- not a multi-instruction prompt.

    Because these models are trained on single-segment translation rather than
    batched multi-line requests, batch_size defaults to 1 (one subtitle line per
    request). You can raise batch_size for speed with general-purpose chat models
    that reliably honor a "---"-separated batch format, but for translation-specific
    models like Typhoon Translate, batch_size=1 is the safest and most reliable.

    Note on timestamps: this function only ever touches line.text. Timing
    (line.start / line.end) is never read or modified here, so translation
    has no effect on subtitle sync -- each translated string is written back
    into the same subtitle event, in place, at the very end.

    Args:
        subs: pysubs2.SSAFile object
        base_url: OpenAI-compatible API base URL (e.g. http://localhost:1234/v1)
        model: model identifier as loaded in LM Studio / Ollama
        source_lang: source language name (e.g. "English")
        target_lang: target language name (e.g. "Thai")
        context_info: optional free-text context to steer translation style/tone,
            e.g. "This is a sci-fi movie. Use a formal tone. Keep character
            names untranslated." Folded into the system prompt, since that's
            the single instruction slot these translation-tuned models
            reliably respect.
        batch_size: number of subtitle lines translated per API call.
            Defaults to 1 -- see note above.

    Yields:
        Progress updates: (progress_float, original_lines, translated_lines)
    """
    lines = [line.text for line in subs]
    translated_lines = []

    # Minimal, model-friendly system prompt. Translation-specific models like
    # Typhoon Translate are trained on exactly this single-sentence instruction
    # shape -- extra framing ("You are a professional translator...", lists of
    # requirements, etc.) is out-of-distribution for them and can degrade or
    # break output entirely.
    system_content = f"Translate the following text into {target_lang}."
    if context_info:
        system_content += f" {context_info.strip()}"

    for i in range(0, len(lines), batch_size):
        batch = lines[i:i + batch_size]

        if batch_size == 1:
            # Single-line mode: send the raw subtitle text directly, no
            # separators, no task description -- matches how translation-
            # specific models were fine-tuned.
            user_content = batch[0]
        else:
            # Batched mode: only reliable with general-purpose chat models
            # that can follow the "---"-separated format. Test carefully
            # before relying on this with a narrow translation model.
            user_content = "\n---\n".join(batch)

        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500 if batch_size == 1 else 2000
                },
                timeout=60
            )
            result = response.json()['choices'][0]['message']['content']

            # Clean up common artifacts
            result = result.replace('```', '').strip()

            if batch_size == 1:
                translated_batch = [result.strip()]
            else:
                # Split by separator
                translated_batch = [line.strip() for line in result.split("\n---\n")]

                # Verify we got the right number of translations
                if len(translated_batch) != len(batch):
                    # Fallback: try splitting by newlines
                    translated_batch = [line.strip() for line in result.split("\n") if line.strip()]

                # If still mismatched, pad or truncate
                if len(translated_batch) < len(batch):
                    translated_batch.extend([f"[Translation missing]"] * (len(batch) - len(translated_batch)))
                elif len(translated_batch) > len(batch):
                    translated_batch = translated_batch[:len(batch)]

        except requests.exceptions.Timeout:
            translated_batch = [f"[Timeout] {line}" for line in batch]
        except requests.exceptions.ConnectionError:
            translated_batch = [f"[Connection Error] {line}" for line in batch]
        except Exception as e:
            translated_batch = [f"[Error: {str(e)[:50]}] {line}" for line in batch]

        translated_lines.extend(translated_batch)
        yield (i + len(batch)) / len(lines), batch, translated_batch

    # Apply translations to subtitle objects.
    # Only .text is modified -- .start / .end (timestamps) are left exactly
    # as they were, so timing/sync is unaffected by translation.
    for i, line in enumerate(subs):
        if i < len(translated_lines):
            line.text = translated_lines[i]


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

    # Corruption detection patterns
    thai_mojibake = ['Ã ', 'Ã¡', 'Ã¨', 'Ã©', 'à¸', 'à¹', 'เธ', 'เน']
    french_mojibake = ['Ã©', 'Ã¨', 'Ã', 'Ã§', 'Ãª', 'Ã´', 'Ã¹']

    corruption_type = "none"
    applied_fix = "none"

    # Strategy 1: Check if it's double-encoded UTF-8
    try:
        # First decode as Latin-1 (which accepts any byte)
        decoded_latin1 = raw_data.decode('latin-1')

        # Check for mojibake patterns
        has_thai_mojibake = any(pattern in decoded_latin1 for pattern in thai_mojibake)
        has_french_mojibake = any(pattern in decoded_latin1 for pattern in french_mojibake)

        if has_thai_mojibake or has_french_mojibake:
            corruption_type = "double_encoding"

            # Try to re-encode as Latin-1 and decode as UTF-8
            try:
                repaired_data = decoded_latin1.encode('latin-1').decode('utf-8')

                # Verify repair worked
                if has_thai_mojibake:
                    has_thai_chars = any('\u0E00' <= c <= '\u0E7F' for c in repaired_data[:500])
                    if has_thai_chars:
                        # Success! Save it
                        temp_subs = pysubs2.SSAFile()
                        temp_subs.from_string(repaired_data)
                        temp_subs.save(output_path, encoding='utf-8')
                        applied_fix = "repaired_thai_double_encoding"
                        return True, corruption_type, applied_fix

                if has_french_mojibake:
                    # Check if French characters are now correct
                    has_french_chars = any(c in 'éèêëàâäôöùûüÿçœæ' for c in repaired_data[:500])
                    if has_french_chars:
                        temp_subs = pysubs2.SSAFile()
                        temp_subs.from_string(repaired_data)
                        temp_subs.save(output_path, encoding='utf-8')
                        applied_fix = "repaired_french_double_encoding"
                        return True, corruption_type, applied_fix

            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
    except:
        pass

    # Strategy 2: Try all common Thai encoding combinations
    if target_script in ["thai", "auto"]:
        thai_repair_strategies = [
            ('tis-620', 'utf-8'),
            ('cp874', 'utf-8'),
            ('windows-874', 'utf-8'),
            ('iso-8859-11', 'utf-8'),
        ]

        for wrong_enc, correct_enc in thai_repair_strategies:
            try:
                # Decode with wrong encoding, re-encode, decode with correct
                temp_text = raw_data.decode(wrong_enc, errors='ignore')
                repaired_data = temp_text.encode(wrong_enc).decode(correct_enc, errors='ignore')

                # Verify Thai characters present
                if any('\u0E00' <= c <= '\u0E7F' for c in repaired_data[:500]):
                    temp_subs = pysubs2.SSAFile()
                    temp_subs.from_string(repaired_data)
                    temp_subs.save(output_path, encoding='utf-8')
                    corruption_type = "wrong_encoding"
                    applied_fix = f"repaired_{wrong_enc}_to_{correct_enc}"
                    return True, corruption_type, applied_fix
            except:
                continue

    # Strategy 3: Try all common Western European encoding combinations
    if target_script in ["french", "auto"]:
        western_repair_strategies = [
            ('windows-1252', 'utf-8'),
            ('iso-8859-1', 'utf-8'),
            ('cp1252', 'utf-8'),
            ('iso-8859-15', 'utf-8'),
        ]

        for wrong_enc, correct_enc in western_repair_strategies:
            try:
                temp_text = raw_data.decode(wrong_enc, errors='ignore')
                repaired_data = temp_text.encode(wrong_enc).decode(correct_enc, errors='ignore')

                # Verify French characters present
                if any(c in 'éèêëàâäôöùûüÿçœæ' for c in repaired_data[:500]):
                    temp_subs = pysubs2.SSAFile()
                    temp_subs.from_string(repaired_data)
                    temp_subs.save(output_path, encoding='utf-8')
                    corruption_type = "wrong_encoding"
                    applied_fix = f"repaired_{wrong_enc}_to_{correct_enc}"
                    return True, corruption_type, applied_fix
            except:
                continue

    # Strategy 4: Last resort - use normalize_subtitle
    try:
        normalize_subtitle(input_path, output_path)
        corruption_type = "encoding_mismatch"
        applied_fix = "normalize_subtitle_fallback"
        return True, corruption_type, applied_fix
    except:
        return False, "unrepairable", "none"


def analyze_corruption(file_path: str) -> dict:
    """
    Analyze a subtitle file to detect what kind of corruption (if any) is present.

    Returns:
        Dictionary with corruption analysis
    """
    try:
        with open(file_path, "rb") as f:
            raw_data = f.read()

        analysis = {
            "file_size_bytes": len(raw_data),
            "corruption_indicators": [],
            "detected_script": "unknown",
            "confidence": 0,
            "recommendations": []
        }

        # Try decoding as Latin-1 to see raw characters
        try:
            latin1_view = raw_data.decode('latin-1')

            # Check for Thai mojibake patterns
            thai_mojibake = ['à¸', 'à¹', 'เธ', 'เน', 'Ã ', 'Ã¡']
            if any(pattern in latin1_view for pattern in thai_mojibake):
                analysis["corruption_indicators"].append("Thai mojibake (double-encoding)")
                analysis["detected_script"] = "thai"
                analysis["confidence"] = 80
                analysis["recommendations"].append("Use 'Repair Corrupted Subtitles' feature with Thai target")

            # Check for French mojibake
            french_mojibake = ['Ã©', 'Ã¨', 'Ã§', 'Ãª', 'Ã´']
            if any(pattern in latin1_view for pattern in french_mojibake):
                analysis["corruption_indicators"].append("French mojibake (double-encoding)")
                analysis["detected_script"] = "french"
                analysis["confidence"] = 80
                analysis["recommendations"].append("Use 'Repair Corrupted Subtitles' feature with French target")

            # Check for Eastern European characters in Western text
            eastern_chars = ['ť', 'Ť', 'ŕ', 'Ŕ', 'č', 'Č', 'ś', 'Ś']
            if any(char in latin1_view for char in eastern_chars):
                analysis["corruption_indicators"].append("Wrong codepage (Western text as Eastern European)")
                analysis["detected_script"] = "french"
                analysis["confidence"] = 70
                analysis["recommendations"].append("Use Sanitizer with 'Fix encoding issues' enabled")
        except:
            pass

        # Check for valid UTF-8 with actual Thai characters
        try:
            utf8_view = raw_data.decode('utf-8')
            has_thai = any('\u0E00' <= c <= '\u0E7F' for c in utf8_view[:1000])
            has_french = any(c in 'éèêëàâäôöùûüÿçœæ' for c in utf8_view[:1000])

            if has_thai:
                analysis["detected_script"] = "thai"
                analysis["confidence"] = 100
                if not analysis["corruption_indicators"]:
                    analysis["corruption_indicators"].append("None - file appears clean")
                    analysis["recommendations"].append("No repair needed, encoding is correct")

            if has_french:
                analysis["detected_script"] = "french"
                analysis["confidence"] = 100
                if not analysis["corruption_indicators"]:
                    analysis["corruption_indicators"].append("None - file appears clean")
                    analysis["recommendations"].append("No repair needed, encoding is correct")
        except UnicodeDecodeError:
            analysis["corruption_indicators"].append("Not valid UTF-8")
            analysis["recommendations"].append("File needs encoding repair")

        return analysis

    except Exception as e:
        return {
            "error": str(e),
            "corruption_indicators": ["Unable to read file"],
            "recommendations": ["Check if file is actually a subtitle file"]
        }