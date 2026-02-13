import streamlit as st
import os, zipfile, io, pysubs2, re
from sub_engine import merge_subtitles, extract_episode_code, translate_subs, shift_subtitles, normalize_subtitle

st.set_page_config(page_title="Subtitle Forge", layout="wide", page_icon="🎬")

# Session State Initialization
for key in ["m_res", "t_res", "s_res", "clean_res"]:
    if key not in st.session_state: st.session_state[key] = {} if "res" in key else None

st.title("🎬 Subtitle Forge")
tabs = st.tabs(["🔗 Merger", "🤖 AI Translator", "⏱️ Quick Sync", "🧼 Sanitizer"])

# --- TAB 1: MERGER ---
with tabs[0]:
    st.header("Batch Merger")
    
    # Inputs at the top
    with st.expander("⚙️ Configuration", expanded=True):
        c1, c2, c3 = st.columns(3)
        s_a = c1.number_input("Track A Shift (ms)", value=0, step=50)
        s_b = c1.number_input("Track B Shift (ms)", value=0, step=50)
        s_g = c2.number_input("Global Shift (ms)", value=0, step=50)
        thresh = c2.number_input("Threshold (ms)", value=1000)
        col_t = c3.selectbox("Color track?", ["None", "Track A", "Track B"], index=2)
        hex_v = c3.color_picker("Color", "#FFFF54")
        kw_b = st.text_input("Track B Keyword (e.g. FR)", value="")
    
    m_files = st.file_uploader("Upload Subtitles", accept_multiple_files=True, key="m_up")
    
    if st.button("🚀 Process Pairs", type="primary"):
        if m_files:
            st.session_state.m_res = {}
            groups = {}
            for f in m_files:
                code = extract_episode_code(f.name)
                groups.setdefault(code, []).append(f)
            
            for code, pair in groups.items():
                if len(pair) == 2:
                    with open("r1.srt", "wb") as f: f.write(pair[0].getbuffer())
                    with open("r2.srt", "wb") as f: f.write(pair[1].getbuffer())
                    
                    normalize_subtitle("r1.srt", "c1.srt")
                    normalize_subtitle("r2.srt", "c2.srt")
                    
                    # Track logic
                    if kw_b.lower() in pair[0].name.lower(): ta, tb = "c2.srt", "c1.srt"
                    else: ta, tb = "c1.srt", "c2.srt"
                    
                    out = f"Merged_{code}.srt"
                    merge_subtitles(ta, tb, out, thresh, hex_v, col_t, s_a, s_b, s_g)
                    with open(out, "rb") as f: st.session_state.m_res[out] = f.read()
                    
                    for tmp in ["r1.srt", "r2.srt", "c1.srt", "c2.srt", out]:
                        if os.path.exists(tmp): os.remove(tmp)
            st.rerun()

# Results Section
    if st.session_state.m_res:
        st.divider()
        
        # 1. Download All (ZIP)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for name, data in st.session_state.m_res.items():
                zf.writestr(name, data)
        
        st.download_button(
            "📥 Download All (ZIP)", 
            zip_buffer.getvalue(), 
            file_name="merged_subtitles.zip", 
            use_container_width=True
        )

        # 2. Preview Feature
        st.subheader("🔍 Quality Control")
        preview_choice = st.selectbox(
            "Select a file to inspect for encoding/sync:",
            options=list(st.session_state.m_res.keys())
        )

        if preview_choice:
            # Get binary data from session state
            binary_data = st.session_state.m_res[preview_choice]
            
            # Explicitly decode as UTF-8 for the preview
            try:
                raw_text = binary_data.decode('utf-8')
            except UnicodeDecodeError:
                # Fallback just for display purposes
                raw_text = binary_data.decode('latin-1', errors='replace')
            
            # Show the first 40 lines (enough to get past the SRT header)
            lines = raw_text.splitlines()
            preview_snippet = "\n".join(lines[:40]) 
            
            st.info(f"Showing preview of: {preview_choice}")
            st.code(preview_snippet, language="markdown")

        st.divider()

        # 3. Individual Downloads
        for name, data in st.session_state.m_res.items():
            col_n, col_d = st.columns([3, 1])
            col_n.write(f"📄 {name}")
            col_d.download_button("Download", data, file_name=name, key=f"dl_{name}")

# --- TAB 2: AI TRANSLATOR ---
with tabs[1]:
    st.header("AI Translator")
    c_a, c_l = st.columns(2)
    url = c_a.text_input("LM Studio URL", value="http://localhost:1234/v1")
    mod = c_a.text_input("Model ID", value="mario-sigma-lm")
    sl, tl = c_l.text_input("From", "English"), c_l.text_input("To", "French")
    ctx = st.text_area("Context (IMDB)")
    file_t = st.file_uploader("Upload File", type=['srt', 'ass'])
    
    col1, col2 = st.columns([1, 4])
    if col1.button("🌍 Start", type="primary") and file_t:
        with open("raw_t.srt", "wb") as f: f.write(file_t.getbuffer())
        normalize_subtitle("raw_t.srt", "clean_t.srt")
        subs = pysubs2.load("clean_t.srt", encoding="utf-8")
        bar = st.progress(0); preview = st.empty()
        try:
            for prog, orig, trans in translate_subs(subs, url, mod, sl, tl, ctx):
                bar.progress(prog)
                with preview.container():
                    ca, cb = st.columns(2)
                    ca.code("\n".join(orig)); cb.code("\n".join(trans))
            st.session_state.t_res = {"n": f"AI_{file_t.name}", "d": subs.to_string(format_="srt")}
        except Exception as e: st.error(e)
    if col2.button("🛑 Stop"): st.stop()
    if st.session_state.t_res:
        st.download_button("📥 Download", st.session_state.t_res['d'], file_name=st.session_state.t_res['n'])

# --- TAB 3: QUICK SYNC ---
with tabs[2]:
    st.header("⏱️ Sync & Drift Fix")
    
    with st.expander("🧮 Drift Calculator", expanded=False):
        st.write("If the start is synced but the end is off, use this:")
        c1, c2 = st.columns(2)
        actual_time = c1.text_input("Actual time of last line (MM:SS.ms)", "00:00.000")
        current_time = c2.text_input("Current time of last line (MM:SS.ms)", "00:00.000")
        if st.button("Calculate Speed Factor"):
            def to_ms(t_str):
                m, s = t_str.split(':')
                return (int(m) * 60 + float(s)) * 1000
            try:
                factor = to_ms(actual_time) / to_ms(current_time)
                st.info(f"Suggested Speed Factor: **{factor:.4f}**")
            except: st.error("Format error. Use MM:SS.ms")

    st.divider()
    c_s, c_d = st.columns(2)
    sh = c_s.number_input("Global Shift (ms)", value=0, step=50, help="Positive = Later, Negative = Earlier")
    sp = c_d.number_input("Speed Factor / FPS Ratio", 0.5, 2.0, 1.0, format="%.4f", step=0.001)
    
    file_s = st.file_uploader("Upload Subtitles to Sync", key="sync_up")
    
    if st.button("⚡ Apply Sync", type="primary") and file_s:
        with open("temp_sync.srt", "wb") as f: f.write(file_s.getbuffer())
        normalize_subtitle("temp_sync.srt", "temp_clean.srt")
        
        subs = pysubs2.load("temp_clean.srt", encoding="utf-8")
        shift_subtitles(subs, sh, sp)
        
        st.session_state.s_res = {
            "n": f"Synced_{file_s.name}", 
            "d": subs.to_string(format_="srt")
        }
        os.remove("temp_sync.srt"); os.remove("temp_clean.srt")

    if st.session_state.s_res:
        st.success(f"Applied: {sh}ms shift at {sp}x speed.")
        st.download_button("📥 Download Synced File", st.session_state.s_res['d'], file_name=st.session_state.s_res['n'])

# --- TAB 4: SANITIZER ---
with tabs[3]:
    st.header("🧼 Subtitle Sanitizer")
    st.write("Clean encoding, remove advertisements, and strip hearing-impaired tags.")
    
    with st.expander("🛠️ Cleaning Options", expanded=True):
        col_c1, col_c2 = st.columns(2)
        rem_ads = col_c1.checkbox("Remove Ads (e.g., OpenSubtitles, YIFY)", value=True)
        rem_hi = col_c2.checkbox("Strip Hearing Impaired Tags (e.g., [Sighs])", value=False)
        find_text = st.text_input("Custom Find (Regex supported)", "")
        replace_text = st.text_input("Custom Replace", "")

    clean_files = st.file_uploader("Upload Subtitles", accept_multiple_files=True, key="clean_up")
    
    if st.button("🧼 Run Sanitizer", type="primary"):
        if clean_files:
            results = {}
            for f in clean_files:
                # Save temp and normalize
                temp_raw = f"raw_{f.name}"
                temp_fixed = f"fixed_{f.name}"
                with open(temp_raw, "wb") as tmp: tmp.write(f.getbuffer())
                
                normalize_subtitle(temp_raw, temp_fixed)
                subs = pysubs2.load(temp_fixed, encoding="utf-8")
                
                # --- Cleaning Logic ---
                new_lines = []
                # Common patterns for subtitle ads
                ad_patterns = [r"subtitles? by", r"corrected by", r"www\.", r"\.com", r"opensubtitles"]
                
                for line in subs:
                    # 1. Remove HI tags: [Text] or (Text)
                    if rem_hi:
                        line.text = re.sub(r"\[.*?\]|\(.*?\)", "", line.text).strip()
                    
                    # 2. Custom Find/Replace
                    if find_text:
                        line.text = re.sub(find_text, replace_text, line.text)
                    
                    # 3. Ad Removal
                    is_ad = any(re.search(p, line.text, re.IGNORECASE) for p in ad_patterns) if rem_ads else False
                    
                    if line.text and not is_ad:
                        new_lines.append(line)
                
                subs.lines = new_lines
                subs.save(temp_fixed, encoding="utf-8")
                
                with open(temp_fixed, "rb") as res:
                    results[f"Clean_{f.name}"] = res.read()
                
                # Local cleanup
                for t in [temp_raw, temp_fixed]: 
                    if os.path.exists(t): os.remove(t)
            
            st.session_state.clean_res = results
            st.rerun()

    # Results Section (ZIP and List)
    if st.session_state.clean_res:
        st.divider()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for n, d in st.session_state.clean_res.items(): zf.writestr(n, d)
        
        st.download_button("📥 Download All Sanitized (ZIP)", zip_buf.getvalue(), "cleaned_subs.zip", use_container_width=True)
        
        for name, data in st.session_state.clean_res.items():
            cn, cd = st.columns([3, 1])
            cn.success(f"Fixed: {name}")
            cd.download_button("Download", data, file_name=name, key=f"dl_c_{name}")