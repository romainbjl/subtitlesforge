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
        # Latin/French subtitle - prioritize Western European encodings
        encodings_to_try = ['cp1252', 'windows-1252', 'iso-8859-1', 'latin-1', detected_enc, 'utf-8', 'iso-8859-15']
    
    # Remove duplicates while preserving order
    seen = set()
    encodings_to_try = [x for x in encodings_to_try if x and x.lower() not in seen and not seen.add(x.lower())]
    
    # Corruption patterns to detect
    # Eastern European chars that shouldn't appear in French
    western_corruption = ['ť', 'Ť', 'ŕ', 'Ŕ', 'č', 'Č', 'ś', 'Ś', 'ř', 'Ř', 'ů', 'Ů']
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


def translate_subs(subs, base_url, model, source_lang, target_lang, context_info="", batch_size=10):
    """
    Translate subtitles using a local LLM API
    
    Yields progress updates with (progress_float, original_lines, translated_lines)
    """
    lines = [line.text for line in subs]
    translated_lines = []
    
    for i in range(0, len(lines), batch_size):
        batch = lines[i:i + batch_size]
        batch_text = "\n---\n".join(batch)
        
        prompt = f"""Context: {context_info}
Task: Translate these subtitle lines from {source_lang} to {target_lang}.
Requirements:
- Maintain the original tone and style
- Keep the format (one line per subtitle, separated by ---)
- Keep translations concise (suitable for subtitles)
- No explanations or comments
- Preserve formatting tags if present

Subtitles:
{batch_text}
"""

        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a professional subtitle translator. Output ONLY the translated subtitles, separated by ---, without any preamble or explanation."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=60
            )
            
            result = response.json()['choices'][0]['message']['content']
            # Clean up common artifacts
            result = result.replace('```', '').strip()
            
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

    # Apply translations to subtitle objects
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