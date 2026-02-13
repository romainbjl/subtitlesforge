import streamlit as st
import os, zipfile, io, pysubs2, re
from pathlib import Path
from sub_engine import (merge_subtitles, extract_episode_code, translate_subs, 
                        shift_subtitles, normalize_subtitle, analyze_corruption, 
                        repair_corrupted_encoding)

st.set_page_config(page_title="Subtitles Forge", layout="wide", page_icon="🎬")

# Session State Initialization
for key in ["m_res", "t_res", "s_res", "clean_res", "processing_log"]:
    if key not in st.session_state: 
        st.session_state[key] = {} if "res" in key else []

# Utility function for safe file cleanup
def safe_cleanup(file_paths):
    """Safely remove temporary files"""
    for path in file_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            st.warning(f"Could not delete {path}: {e}")

# Add sidebar with app info and tips
with st.sidebar:
    st.header("ℹ️ About")
    st.write("""
    **Subtitles Forge** helps you:
    - Merge dual-language subtitles
    - Translate with local AI
    - Fix sync/drift issues
    - Clean & sanitize files
    """)
    
    st.divider()
    
    st.header("💡 Tips")
    with st.expander("Merger Tips"):
        st.markdown("""
        - Upload files in pairs (same episode code)
        - Use keyword to identify Track B (e.g., "FR", "TH")
        - Adjust threshold if subs don't align
        - Color coding helps distinguish tracks
        """)
    
    with st.expander("Encoding Tips"):
        st.markdown("""
        - App auto-detects French, Thai, and other encodings
        - Preview files before downloading
        - If corruption persists, try Sanitizer tab
        """)
    
    st.divider()
    
    if st.session_state.processing_log:
        with st.expander("📋 Processing Log", expanded=False):
            for log_entry in st.session_state.processing_log[-10:]:  # Last 10 entries
                st.text(log_entry)

st.title("🎬 Subtitles Forge")
tabs = st.tabs(["🔗 Merger", "🤖 AI Translator", "⏱️ Quick Sync", "🧼 Sanitizer", "🔧 Repair"])

# --- TAB 1: MERGER ---
with tabs[0]:
    st.header("Batch Merger")
    
    # Inputs at the top
    with st.expander("⚙️ Configuration", expanded=True):
        c1, c2, c3 = st.columns(3)
        s_a = c1.number_input("Track A Shift (ms)", value=0, step=50, 
                              help="Shift Track A timing. Positive = later, Negative = earlier")
        s_b = c1.number_input("Track B Shift (ms)", value=0, step=50,
                              help="Shift Track B timing. Positive = later, Negative = earlier")
        s_g = c2.number_input("Global Shift (ms)", value=0, step=50,
                              help="Apply final shift to merged result")
        thresh = c2.number_input("Threshold (ms)", value=1000, min_value=0, max_value=5000,
                                 help="Max time difference to consider subs as matching (0-5000ms)")
        col_t = c3.selectbox("Color track?", ["None", "Track A", "Track B"], index=2,
                            help="Which track to colorize in the output")
        hex_v = c3.color_picker("Color", "#FFFF54")
        kw_b = st.text_input("Track B Keyword (e.g. FR, TH, EN)", value="",
                            help="Files containing this keyword will be assigned to Track B")
    
    m_files = st.file_uploader("Upload Subtitles", accept_multiple_files=True, key="m_up",
                               help="Upload subtitle pairs. Files will be auto-paired by episode code.")
    
    # Show file preview
    if m_files:
        with st.expander("📂 Uploaded Files Preview", expanded=True):
            groups = {}
            for f in m_files:
                code = extract_episode_code(f.name)
                groups.setdefault(code, []).append(f.name)
            
            for code, files in groups.items():
                if len(files) == 2:
                    st.success(f"✅ **{code}**: {files[0]} + {files[1]}")
                else:
                    st.warning(f"⚠️ **{code}**: {len(files)} file(s) - {', '.join(files)}")
            
            total_pairs = sum(1 for files in groups.values() if len(files) == 2)
            st.info(f"**{total_pairs} valid pair(s)** ready to merge")
    
    if st.button("🚀 Process Pairs", type="primary", disabled=not m_files):
        if m_files:
            st.session_state.m_res = {}
            st.session_state.processing_log = []
            groups = {}
            
            for f in m_files:
                code = extract_episode_code(f.name)
                groups.setdefault(code, []).append(f)
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            pairs = [pair for pair in groups.items() if len(pair[1]) == 2]
            
            for idx, (code, pair) in enumerate(pairs):
                status_text.text(f"Processing {code}... ({idx+1}/{len(pairs)})")
                temp_files = []
                
                try:
                    # Save uploaded files
                    with open("r1.srt", "wb") as f: f.write(pair[0].getbuffer())
                    with open("r2.srt", "wb") as f: f.write(pair[1].getbuffer())
                    temp_files.extend(["r1.srt", "r2.srt"])
                    
                    # Normalize encoding
                    normalize_subtitle("r1.srt", "c1.srt")
                    normalize_subtitle("r2.srt", "c2.srt")
                    temp_files.extend(["c1.srt", "c2.srt"])
                    
                    # Track logic
                    if kw_b and kw_b.lower() in pair[0].name.lower(): 
                        ta, tb = "c2.srt", "c1.srt"
                        log_msg = f"{code}: {pair[1].name} (A) + {pair[0].name} (B)"
                    else: 
                        ta, tb = "c1.srt", "c2.srt"
                        log_msg = f"{code}: {pair[0].name} (A) + {pair[1].name} (B)"
                    
                    st.session_state.processing_log.append(log_msg)
                    
                    # Merge
                    out = f"Merged_{code}.srt"
                    merge_subtitles(ta, tb, out, thresh, hex_v, col_t, s_a, s_b, s_g)
                    
                    with open(out, "rb") as f: 
                        st.session_state.m_res[out] = f.read()
                    
                    temp_files.append(out)
                    st.session_state.processing_log.append(f"✓ {code} merged successfully")
                    
                except Exception as e:
                    st.session_state.processing_log.append(f"✗ {code} failed: {str(e)}")
                    st.error(f"Error processing {code}: {e}")
                
                finally:
                    safe_cleanup(temp_files)
                
                progress_bar.progress((idx + 1) / len(pairs))
            
            status_text.success(f"✅ Completed! Processed {len(st.session_state.m_res)} file(s)")
            st.rerun()

    # Results Section
    if st.session_state.m_res:
        st.divider()
        
        # Stats
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        total_files = len(st.session_state.m_res)
        total_size = sum(len(data) for data in st.session_state.m_res.values())
        
        col_stat1.metric("Files Merged", total_files)
        col_stat2.metric("Total Size", f"{total_size / 1024:.1f} KB")
        col_stat3.metric("Avg Size", f"{total_size / total_files / 1024:.1f} KB")
        
        st.divider()
        
        # Download All (ZIP)
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

        # Preview Feature
        st.subheader("🔍 Quality Control")
        preview_choice = st.selectbox(
            "Select a file to inspect for encoding/sync:",
            options=list(st.session_state.m_res.keys())
        )

        if preview_choice:
            binary_data = st.session_state.m_res[preview_choice]
            
            try:
                raw_text = binary_data.decode('utf-8')
            except UnicodeDecodeError:
                raw_text = binary_data.decode('latin-1', errors='replace')
            
            lines = raw_text.splitlines()
            
            # Better preview with line numbers and more lines
            col_prev1, col_prev2 = st.columns([3, 1])
            num_lines = col_prev2.slider("Preview lines", 10, 100, 40, step=10)
            
            preview_snippet = "\n".join(lines[:num_lines])
            
            st.info(f"Showing first {num_lines} lines of: {preview_choice}")
            st.code(preview_snippet, language="srt")
            
            # Show encoding verification
            has_thai = any('ก' <= c <= '๛' for line in lines[:20] for c in line)
            has_french = any(c in 'éèêëàâäôöùûüÿçœæ' for line in lines[:20] for c in line)
            
            if has_thai:
                st.success("✓ Thai characters detected")
            if has_french:
                st.success("✓ French accents detected")

        st.divider()

        # Individual Downloads
        st.subheader("📦 Individual Files")
        for name, data in st.session_state.m_res.items():
            col_n, col_size, col_d = st.columns([4, 1, 1])
            col_n.write(f"📄 {name}")
            col_size.caption(f"{len(data) / 1024:.1f} KB")
            col_d.download_button("⬇️", data, file_name=name, key=f"dl_{name}")
        
        # Clear results button
        if st.button("🗑️ Clear Results"):
            st.session_state.m_res = {}
            st.session_state.processing_log = []
            st.rerun()

# --- TAB 2: AI TRANSLATOR ---
with tabs[1]:
    st.header("AI Translator")
    
    st.info("💡 Requires local LM Studio or compatible OpenAI API endpoint")
    
    c_a, c_l = st.columns(2)
    url = c_a.text_input("LM Studio URL", value="http://localhost:1234/v1",
                         help="OpenAI-compatible API endpoint")
    mod = c_a.text_input("Model ID", value="mario-sigma-lm",
                         help="Model identifier in LM Studio")
    sl, tl = c_l.text_input("From Language", "English"), c_l.text_input("To Language", "French")
    ctx = st.text_area("Context (Optional)", placeholder="e.g., Movie title, genre, character names...",
                       help="Provide context to improve translation accuracy")
    file_t = st.file_uploader("Upload Subtitle File", type=['srt', 'ass'])
    
    if file_t:
        st.info(f"📄 Loaded: {file_t.name} ({file_t.size / 1024:.1f} KB)")
    
    col1, col2 = st.columns([1, 4])
    if col1.button("🌍 Start Translation", type="primary") and file_t:
        temp_files = ["raw_t.srt", "clean_t.srt"]
        try:
            with open("raw_t.srt", "wb") as f: f.write(file_t.getbuffer())
            normalize_subtitle("raw_t.srt", "clean_t.srt")
            subs = pysubs2.load("clean_t.srt", encoding="utf-8")
            
            bar = st.progress(0)
            preview = st.empty()
            
            for prog, orig, trans in translate_subs(subs, url, mod, sl, tl, ctx):
                bar.progress(prog)
                with preview.container():
                    ca, cb = st.columns(2)
                    ca.code("\n".join(orig), language="text")
                    cb.code("\n".join(trans), language="text")
            
            st.session_state.t_res = {
                "n": f"Translated_{sl}_to_{tl}_{file_t.name}", 
                "d": subs.to_string(format_="srt")
            }
            st.success("✅ Translation complete!")
            
        except Exception as e:
            st.error(f"Translation failed: {e}")
            st.info("Check that LM Studio is running and the model is loaded")
        finally:
            safe_cleanup(temp_files)
            
    if col2.button("🛑 Stop"): 
        st.stop()
        
    if st.session_state.t_res:
        st.download_button(
            "📥 Download Translated File", 
            st.session_state.t_res['d'], 
            file_name=st.session_state.t_res['n'],
            use_container_width=True
        )

# --- TAB 3: QUICK SYNC ---
with tabs[2]:
    st.header("⏱️ Sync & Drift Fix")
    
    with st.expander("🧮 Drift Calculator", expanded=False):
        st.write("**Use this when:** Start is synced but end drifts out of sync")
        c1, c2 = st.columns(2)
        actual_time = c1.text_input("Actual time of last subtitle (MM:SS.ms)", "00:00.000",
                                     help="Where the last subtitle SHOULD appear")
        current_time = c2.text_input("Current time of last subtitle (MM:SS.ms)", "00:00.000",
                                      help="Where the last subtitle CURRENTLY appears")
        if st.button("Calculate Speed Factor"):
            def to_ms(t_str):
                try:
                    m, s = t_str.split(':')
                    return (int(m) * 60 + float(s)) * 1000
                except:
                    return None
            
            actual_ms = to_ms(actual_time)
            current_ms = to_ms(current_time)
            
            if actual_ms and current_ms and current_ms > 0:
                factor = actual_ms / current_ms
                st.success(f"✅ Suggested Speed Factor: **{factor:.4f}**")
                st.caption(f"This will stretch/compress timing by {abs(1-factor)*100:.1f}%")
            else:
                st.error("⚠️ Format error. Use MM:SS.ms (e.g., 45:30.500)")

    st.divider()
    c_s, c_d = st.columns(2)
    sh = c_s.number_input("Global Shift (ms)", value=0, step=50, 
                          help="Positive = Later, Negative = Earlier")
    sp = c_d.number_input("Speed Factor / FPS Ratio", 0.5, 2.0, 1.0, format="%.4f", step=0.001,
                          help="1.0 = no change, >1.0 = slower, <1.0 = faster")
    
    file_s = st.file_uploader("Upload Subtitles to Sync", key="sync_up")
    
    if file_s:
        st.info(f"📄 {file_s.name}")
    
    if st.button("⚡ Apply Sync", type="primary") and file_s:
        temp_files = ["temp_sync.srt", "temp_clean.srt"]
        try:
            with open("temp_sync.srt", "wb") as f: f.write(file_s.getbuffer())
            normalize_subtitle("temp_sync.srt", "temp_clean.srt")
            
            subs = pysubs2.load("temp_clean.srt", encoding="utf-8")
            shift_subtitles(subs, sh, sp)
            
            st.session_state.s_res = {
                "n": f"Synced_{file_s.name}", 
                "d": subs.to_string(format_="srt")
            }
            st.success(f"✅ Applied: {sh}ms shift at {sp}x speed")
        except Exception as e:
            st.error(f"Sync failed: {e}")
        finally:
            safe_cleanup(temp_files)

    if st.session_state.s_res:
        st.download_button(
            "📥 Download Synced File", 
            st.session_state.s_res['d'], 
            file_name=st.session_state.s_res['n'],
            use_container_width=True
        )

# --- TAB 4: SANITIZER ---
with tabs[3]:
    st.header("🧼 Subtitle Sanitizer")
    st.write("Clean encoding, remove advertisements, and strip hearing-impaired tags.")
    
    with st.expander("🛠️ Cleaning Options", expanded=True):
        col_c1, col_c2 = st.columns(2)
        rem_ads = col_c1.checkbox("Remove Ads (e.g., OpenSubtitles, YIFY)", value=True)
        rem_hi = col_c2.checkbox("Strip Hearing Impaired Tags (e.g., [Sighs], (Music))", value=False)
        rem_empty = col_c1.checkbox("Remove empty lines", value=True)
        fix_encoding = col_c2.checkbox("Fix encoding issues", value=True)
        
        st.divider()
        st.subheader("Custom Find & Replace")
        find_text = st.text_input("Find (Regex supported)", "",
                                  help="e.g., \\[.*?\\] to remove all [bracketed] text")
        replace_text = st.text_input("Replace with", "")

    clean_files = st.file_uploader("Upload Subtitles", accept_multiple_files=True, key="clean_up")
    
    if clean_files:
        st.info(f"📂 {len(clean_files)} file(s) uploaded")
    
    if st.button("🧼 Run Sanitizer", type="primary", disabled=not clean_files):
        if clean_files:
            results = {}
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, f in enumerate(clean_files):
                status_text.text(f"Cleaning {f.name}... ({idx+1}/{len(clean_files)})")
                temp_raw = f"raw_{f.name}"
                temp_fixed = f"fixed_{f.name}"
                
                try:
                    with open(temp_raw, "wb") as tmp: tmp.write(f.getbuffer())
                    
                    if fix_encoding:
                        normalize_subtitle(temp_raw, temp_fixed)
                    else:
                        # Just copy if not fixing encoding
                        with open(temp_raw, "rb") as src, open(temp_fixed, "wb") as dst:
                            dst.write(src.read())
                    
                    subs = pysubs2.load(temp_fixed, encoding="utf-8")
                    
                    # Cleaning Logic
                    new_lines = []
                    ad_patterns = [
                        r'subtitles? by', r'corrected by', r'www\.', r'\.com', 
                        r'opensubtitles', r'addic7ed', r'subscene', r'yify'
                    ]
                    
                    for line in subs:
                        original_text = line.text
                        
                        # 1. Remove HI tags
                        if rem_hi:
                            line.text = re.sub(r'\[.*?\]|\(.*?\)', '', line.text)
                        
                        # 2. Custom Find/Replace
                        if find_text:
                            try:
                                line.text = re.sub(find_text, replace_text, line.text)
                            except re.error:
                                st.warning(f"Invalid regex in '{find_text}', skipping")
                        
                        # 3. Strip whitespace
                        line.text = line.text.strip()
                        
                        # 4. Ad Removal
                        is_ad = False
                        if rem_ads:
                            is_ad = any(re.search(p, line.text, re.IGNORECASE) for p in ad_patterns)
                        
                        # 5. Empty line check
                        is_empty = not line.text if rem_empty else False
                        
                        if not is_ad and not is_empty:
                            new_lines.append(line)
                    
                    subs.lines = new_lines
                    subs.save(temp_fixed, encoding="utf-8")
                    
                    with open(temp_fixed, "rb") as res:
                        results[f"Clean_{f.name}"] = res.read()
                    
                except Exception as e:
                    st.error(f"Error cleaning {f.name}: {e}")
                finally:
                    safe_cleanup([temp_raw, temp_fixed])
                
                progress_bar.progress((idx + 1) / len(clean_files))
            
            st.session_state.clean_res = results
            status_text.success(f"✅ Cleaned {len(results)} file(s)")
            st.rerun()

    # Results Section
    if st.session_state.clean_res:
        st.divider()
        
        # Stats
        st.metric("Files Cleaned", len(st.session_state.clean_res))
        
        # Download All
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for n, d in st.session_state.clean_res.items(): 
                zf.writestr(n, d)
        
        st.download_button(
            "📥 Download All Sanitized (ZIP)", 
            zip_buf.getvalue(), 
            "cleaned_subs.zip", 
            use_container_width=True
        )
        
        st.divider()
        
        # Individual files
        for name, data in st.session_state.clean_res.items():
            cn, cs, cd = st.columns([4, 1, 1])
            cn.success(f"✅ {name}")
            cs.caption(f"{len(data) / 1024:.1f} KB")
            cd.download_button("⬇️", data, file_name=name, key=f"dl_c_{name}")
        
        # Clear button
        if st.button("🗑️ Clear Results", key="clear_sanitizer"):
            st.session_state.clean_res = {}
            st.rerun()

# --- TAB 5: REPAIR ---
with tabs[4]:
    st.header("🔧 Subtitle Repair Lab")
    st.write("Analyze and repair severely corrupted subtitle files (mojibake, double-encoding, wrong codepage)")
    
    st.info("""
    **When to use this tab:**
    - Thai subtitles showing as `à¸`, `à¹`, `เธ`, `เน`
    - French accents showing as `Ã©`, `Ã¨`, `Ã§`
    - Text is completely garbled/unreadable
    - File has been re-saved multiple times with wrong encoding
    """)
    
    repair_mode = st.radio(
        "Mode:",
        ["🔍 Analyze Only", "🔧 Analyze & Repair"],
        horizontal=True
    )
    
    repair_files = st.file_uploader(
        "Upload Corrupted Subtitles", 
        accept_multiple_files=True, 
        key="repair_up",
        help="Upload subtitle files that appear corrupted"
    )
    
    if repair_files:
        st.info(f"📂 {len(repair_files)} file(s) uploaded")
    
    # Target script selection
    with st.expander("⚙️ Repair Options", expanded=True):
        target_script = st.selectbox(
            "Target Script/Language",
            ["auto", "thai", "french", "chinese"],
            help="Which language are the subtitles supposed to be in?"
        )
    
    if st.button("🔍 Analyze/Repair Files", type="primary", disabled=not repair_files):
        from sub_engine import analyze_corruption, repair_corrupted_encoding
        
        analysis_results = {}
        repair_results = {}
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, f in enumerate(repair_files):
            status_text.text(f"Processing {f.name}... ({idx+1}/{len(repair_files)})")
            temp_file = f"temp_corrupt_{f.name}"
            
            try:
                # Save uploaded file
                with open(temp_file, "wb") as tmp:
                    tmp.write(f.getbuffer())
                
                # Analyze corruption
                analysis = analyze_corruption(temp_file)
                analysis_results[f.name] = analysis
                
                # If repair mode, attempt repair
                if repair_mode == "🔧 Analyze & Repair":
                    repair_output = f"repaired_{f.name}"
                    success, corruption_type, applied_fix = repair_corrupted_encoding(
                        temp_file, 
                        repair_output, 
                        target_script
                    )
                    
                    if success:
                        with open(repair_output, "rb") as repaired:
                            repair_results[f"Repaired_{f.name}"] = repaired.read()
                        
                        analysis_results[f.name]["repair_status"] = "✅ Successfully repaired"
                        analysis_results[f.name]["repair_method"] = applied_fix
                        safe_cleanup([repair_output])
                    else:
                        analysis_results[f.name]["repair_status"] = "❌ Could not repair"
                        analysis_results[f.name]["repair_method"] = "none"
                
            except Exception as e:
                analysis_results[f.name] = {
                    "error": str(e),
                    "repair_status": "❌ Error during analysis"
                }
            finally:
                safe_cleanup([temp_file])
            
            progress_bar.progress((idx + 1) / len(repair_files))
        
        status_text.success(f"✅ Completed analysis of {len(repair_files)} file(s)")
        
        # Display results
        st.divider()
        st.subheader("📊 Analysis Results")
        
        for filename, analysis in analysis_results.items():
            with st.expander(f"📄 {filename}", expanded=True):
                if "error" in analysis:
                    st.error(f"Error: {analysis['error']}")
                else:
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Detected Script", analysis.get("detected_script", "unknown").title())
                    with col2:
                        st.metric("Confidence", f"{analysis.get('confidence', 0)}%")
                    with col3:
                        st.metric("File Size", f"{analysis.get('file_size_bytes', 0) / 1024:.1f} KB")
                    
                    st.write("**Corruption Indicators:**")
                    for indicator in analysis.get("corruption_indicators", []):
                        if "None" in indicator:
                            st.success(f"✓ {indicator}")
                        else:
                            st.warning(f"⚠️ {indicator}")
                    
                    st.write("**Recommendations:**")
                    for rec in analysis.get("recommendations", []):
                        st.info(f"💡 {rec}")
                    
                    if "repair_status" in analysis:
                        st.divider()
                        if "✅" in analysis["repair_status"]:
                            st.success(analysis["repair_status"])
                            st.caption(f"Method: {analysis.get('repair_method', 'unknown')}")
                        else:
                            st.error(analysis["repair_status"])
        
        # Download repaired files
        if repair_results:
            st.divider()
            st.subheader("📥 Download Repaired Files")
            
            # Download all as ZIP
            if len(repair_results) > 1:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for name, data in repair_results.items():
                        zf.writestr(name, data)
                
                st.download_button(
                    "📥 Download All Repaired (ZIP)",
                    zip_buf.getvalue(),
                    "repaired_subtitles.zip",
                    use_container_width=True
                )
            
            # Individual downloads
            for name, data in repair_results.items():
                col_name, col_size, col_dl = st.columns([4, 1, 1])
                col_name.success(f"✅ {name}")
                col_size.caption(f"{len(data) / 1024:.1f} KB")
                col_dl.download_button("⬇️", data, file_name=name, key=f"dl_repair_{name}")
    
    # Add examples section
    with st.expander("📖 Example Corruption Patterns", expanded=False):
        st.markdown("""
        ### Thai Corruption Examples
        
        **Double-encoded UTF-8:**
        ```
        Corrupted: à¸œà¸¡à¸Šà¸·à¹ˆà¸­à¸ˆà¸­à¸«à¹Œà¸™
        Should be: ผมชื่อจอห์น
        ```
        
        **Wrong codepage (TIS-620 as Latin-1):**
        ```
        Corrupted: ¼Á ª×èÍ¨Í˹Œ¹
        Should be: ผมชื่อจอห์น
        ```
        
        ### French Corruption Examples
        
        **Double-encoded UTF-8:**
        ```
        Corrupted: Ã  la maison, câ€™est très belle
        Should be: À la maison, c'est très belle
        ```
        
        **Wrong codepage (Windows-1252 as UTF-8):**
        ```
        Corrupted: � la maison
        Should be: À la maison
        ```
        
        ### What This Tool Can Fix
        - ✅ Double-encoding (UTF-8 → Latin-1 → UTF-8)
        - ✅ Wrong codepage interpretation
        - ✅ Mojibake (garbled characters)
        - ✅ Mixed encoding issues
        
        ### What It Cannot Fix
        - ❌ Lost/deleted characters
        - ❌ Truncated files
        - ❌ Actual typos (wrong characters typed)
        - ❌ 3+ layers of corruption
        """)