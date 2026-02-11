import pysubs2
import re
import requests

def safe_load(path):
    """Attempts to load a subtitle file with UTF-8, falls back to guessing encoding."""
    try:
        return pysubs2.load(path, encoding="utf-8")
    except (UnicodeDecodeError, Exception):
        # Fallback to automatic encoding detection
        return pysubs2.load(path)

def translate_subs(subs, base_url, model, source_lang, target_lang, context_info="", batch_size=10):
    lines = [line.text for line in subs]
    translated_lines = []
    
    for i in range(0, len(lines), batch_size):
        batch = lines[i:i + batch_size]
        batch_text = "\n---\n".join(batch)
        
        prompt = f"""
        Context: {context_info}
        Task: Translate the following subtitle lines from {source_lang} to {target_lang}.
        Requirements:
        - Maintain original tone. 
        - Keep output format exactly as it is (one line per subtitle).
        - Do not add explanations or meta-talk.
        
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
        
        # Extract the content safely
        try:
            result = response.json()['choices'][0]['message']['content']
            # Remove possible code block wrappers if AI adds them
            result = result.replace('```', '')
            translated_batch = [line.strip() for line in result.split("\n---\n")]
        except Exception as e:
            translated_batch = [f"[Error Translating] {line}" for line in batch]
            
        translated_lines.extend(translated_batch)
        
        progress = (i + len(batch)) / len(lines)
        yield progress, batch, translated_batch

    # Apply translated text back to the subs object, handling potential length mismatch
    for i, line in enumerate(subs):
        if i < len(translated_lines):
            line.text = translated_lines[i]

def extract_episode_code(filename):
    patterns = [r'[sS]\d+[eE]\d+', r'\d+[xX]\d+', r'[eE]\d+']
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(0).upper()
    return filename

def shift_subtitles(subs, shift_ms, speed_factor=1.0):
    """
    Shifts and scales subtitles. 
    speed_factor fixes drift (e.g., 23.976 to 25 FPS).
    """
    if shift_ms == 0 and speed_factor == 1.0:
        return subs
    for line in subs:
        # Scale first (for drift), then shift (for delay)
        line.start = int(line.start * speed_factor) + shift_ms
        line.end = int(line.end * speed_factor) + shift_ms
    return subs

def merge_subtitles(path_a, path_b, output_path, threshold_ms=1000, 
                    color_hex="#ffff54", color_track="Track B",
                    shift_a=0, shift_b=0, shift_global=0):
    
    # Use safe_load to avoid UnicodeDecodeErrors
    subs_a = safe_load(path_a)
    subs_b = safe_load(path_b)

    # 1. Apply Individual Track Shifts BEFORE merging
    shift_subtitles(subs_a, shift_a)
    shift_subtitles(subs_b, shift_b)

    def apply_color(text, hex_val):
        return f'<font color="{hex_val}">{text}</font>'

    # 2. Apply Color to chosen track
    if color_track == "Track A":
        for line in subs_a: line.text = apply_color(line.text, color_hex)
    elif color_track == "Track B":
        for line in subs_b: line.text = apply_color(line.text, color_hex)

    # 3. Merge Logic
    for line_b in subs_b:
        matched = False
        for line_a in subs_a:
            if abs(line_a.start - line_b.start) <= threshold_ms:
                line_a.text += f"\n{line_b.text}"
                matched = True
                break
        if not matched:
            subs_a.append(line_b)

    # 4. Apply Global Shift AFTER merging
    shift_subtitles(subs_a, shift_global)

    subs_a.sort()
    subs_a.save(output_path)