import pysubs2
import re
import requests
import os
from charset_normalizer import detect

def normalize_subtitle(input_path, output_path):
    """
    Forcefully standardizes subtitles to UTF-8. 
    Specifically targets the 'é' -> 'ť' corruption by prioritizing 
    Western European maps.
    """
    with open(input_path, "rb") as f:
        raw_data = f.read()
        prediction = detect(raw_data)
        detected_enc = prediction.get('encoding')
        confidence = prediction.get('confidence', 0)

    # List of encodings to try in order of likelihood for French/Western subs
    # cp1252 (Windows-1252) is the most common culprit for the 'ť' error
    encodings_to_try = [detected_enc, 'utf-8', 'cp1252', 'latin-1', 'windows-1252']
    
    subs = None
    for enc in encodings_to_try:
        if not enc: continue
        try:
            subs = pysubs2.load(input_path, encoding=enc)
            # Check if the text actually contains common corruption patterns
            # If we see 'ť' where we expect 'é', we try the next encoding
            test_text = "".join([l.text for l in subs[:10]])
            if 'ť' in test_text or 'Ť' in test_text:
                continue 
            break # Success!
        except:
            continue

    if subs is None:
        # Final fallback
        subs = pysubs2.load(input_path, encoding='latin-1')

    # Standardize internal line breaks
    for line in subs:
        line.text = line.text.replace("\r\n", "\n").replace("\r", "\n")
        
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