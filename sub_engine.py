import pysubs2
import re
import requests
import os

def normalize_subtitle(input_path, output_path):
    """
    Forcefully standardizes subtitles to UTF-8. 
    Handles multiple scripts (Latin/French, Thai, etc.) by detecting script type
    and choosing appropriate encoding candidates.
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
    
    # Check if detected encoding suggests Thai
    is_thai_encoding = detected_enc and ('874' in detected_enc.lower() or 
                                          'thai' in detected_enc.lower() or
                                          'tis' in detected_enc.lower())
    
    # Build encoding list based on script detection
    if has_thai_bytes or is_thai_encoding:
        # Thai subtitle - prioritize UTF-8 and Thai-specific encodings
        encodings_to_try = ['utf-8', 'tis-620', 'cp874', 'iso-8859-11', detected_enc]
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
    return output_path

def translate_subs(subs, base_url, model, source_lang, target_lang, context_info="", batch_size=10):
    lines = [line.text for line in subs]
    translated_lines = []
    
    for i in range(0, len(lines), batch_size):
        batch = lines[i:i + batch_size]
        batch_text = "\n---\n".join(batch)
        
        prompt = f"""
        Context: {context_info}
        Task: Translate these subtitle lines from {source_lang} to {target_lang}.
        Requirements:
        - Maintain tone. 
        - Keep format (one line per subtitle).
        - No explanations.
        
        Subtitles:
        {batch_text}
        """

        response = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional subtitle translator."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }
        )
        
        try:
            result = response.json()['choices'][0]['message']['content']
            result = result.replace('```', '').strip()
            translated_batch = [line.strip() for line in result.split("\n---\n")]
        except:
            translated_batch = [f"[Error] {line}" for line in batch]
            
        translated_lines.extend(translated_batch)
        yield (i + len(batch)) / len(lines), batch, translated_batch

    for i, line in enumerate(subs):
        if i < len(translated_lines):
            line.text = translated_lines[i]

def extract_episode_code(filename):
    patterns = [r'[sS]\d+[eE]\d+', r'\d+[xX]\d+', r'[eE]\d+']
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match: return match.group(0).upper()
    return filename

def shift_subtitles(subs, shift_ms, speed_factor=1.0):
    if shift_ms == 0 and speed_factor == 1.0: return subs
    for line in subs:
        line.start = int(line.start * speed_factor) + shift_ms
        line.end = int(line.end * speed_factor) + shift_ms
    return subs

def merge_subtitles(path_a, path_b, output_path, threshold_ms=1000, 
                    color_hex="#ffff54", color_track="Track B",
                    shift_a=0, shift_b=0, shift_global=0):
    
    # Normalized files are now GUARANTEED UTF-8
    subs_a = pysubs2.load(path_a, encoding="utf-8")
    subs_b = pysubs2.load(path_b, encoding="utf-8")

    shift_subtitles(subs_a, shift_a)
    shift_subtitles(subs_b, shift_b)

    # Apply color tags
    if color_track == "Track A":
        for line in subs_a: line.text = f'<font color="{color_hex}">{line.text.strip()}</font>'
    elif color_track == "Track B":
        for line in subs_b: line.text = f'<font color="{color_hex}">{line.text.strip()}</font>'

    # Merge Logic
    for line_b in subs_b:
        matched = False
        for line_a in subs_a:
            if abs(line_a.start - line_b.start) <= threshold_ms:
                # Use a clean separator to avoid clumping
                line_a.text = f"{line_a.text.strip()}\n{line_b.text.strip()}"
                matched = True
                break
        if not matched:
            subs_a.append(line_b)

    shift_subtitles(subs_a, shift_global)
    subs_a.sort()
    # Save as UTF-8 WITHOUT BOM (Streamlit and most players prefer this)
    subs_a.save(output_path, encoding="utf-8")