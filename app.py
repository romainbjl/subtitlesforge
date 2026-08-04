import io
import re
import zipfile

import pysubs2
import streamlit as st
from file_utils import (
    read_nonempty_bytes,
    safe_filename,
    save_uploaded_file,
    temporary_workspace,
)
from sub_engine import (merge_subtitles, extract_episode_code, translate_subs, 
                        shift_subtitles, normalize_subtitle, analyze_corruption, 
                        repair_corrupted_encoding)

st.set_page_config(page_title="Subtitles Forge", layout="wide", page_icon="🎬")

# Session State Initialization
SESSION_DEFAULTS = {
    "m_res": {},
    "t_res": {},
    "s_res": {},
    "clean_res": {},
    "repair_res": {},
    "repair_analysis": {},
    "processing_log": [],
}
for key, default_value in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value.copy()

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
                try:
                    with temporary_workspace("merge") as workspace:
                        raw_a = save_uploaded_file(pair[0], workspace, "track-a")
                        raw_b = save_uploaded_file(pair[1], workspace, "track-b")
                        clean_a = workspace / "track-a.srt"
                        clean_b = workspace / "track-b.srt"
                        normalize_subtitle(str(raw_a), str(clean_a))
                        normalize_subtitle(str(raw_b), str(clean_b))

                        if kw_b and kw_b.lower() in pair[0].name.lower():
                            track_a, track_b = clean_b, clean_a
                            log_msg = f"{code}: {pair[1].name} (A) + {pair[0].name} (B)"
                        else:
                            track_a, track_b = clean_a, clean_b
                            log_msg = f"{code}: {pair[0].name} (A) + {pair[1].name} (B)"

                        st.session_state.processing_log.append(log_msg)
                        output_name = safe_filename(f"Merged_{code}.srt")
                        output_path = workspace / output_name
                        merge_subtitles(
                            str(track_a),
                            str(track_b),
                            str(output_path),
                            thresh,
                            hex_v,
                            col_t,
                            s_a,
                            s_b,
                            s_g,
                        )
                        st.session_state.m_res[output_name] = read_nonempty_bytes(output_path)

                    st.session_state.processing_log.append(f"✓ {code} merged successfully")
                    
                except Exception as e:
                    st.session_state.processing_log.append(f"✗ {code} failed: {str(e)}")
                    st.error(f"Error processing {code}: {e}")
                
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
    mod = c_a.text_input("Model ID", value="typhoon-translate1.5-4b@q8_0",
                         help="Model identifier in LM Studio")
    sl, tl = c_l.text_input("From Language", "English"), c_l.text_input("To Language", "French")
    ctx = st.text_area("Context (Optional)", placeholder="e.g., Movie title, genre, character names...",
                       help="Provide context to improve translation accuracy")

    translation_mode_label = st.radio(
        "Translation mode",
        ["Contextual sliding window (recommended)", "Individual subtitles"],
        horizontal=True,
        help=(
            "Contextual mode translates small dialogue groups while showing the model "
            "surrounding lines and previously accepted translations."
        ),
    )
    translation_mode = (
        "sliding"
        if translation_mode_label.startswith("Contextual")
        else "individual"
    )

    with st.expander("Translation quality settings", expanded=translation_mode == "sliding"):
        temperature = st.slider(
            "Initial translation temperature",
            min_value=0.0,
            max_value=1.0,
            value=0.4,
            step=0.05,
            help="0.4 balances natural dialogue with reliable subtitle structure.",
        )
        if translation_mode == "sliding":
            q1, q2, q3 = st.columns(3)
            translation_group_size = q1.number_input(
                "Subtitles translated together",
                min_value=1,
                max_value=10,
                value=4,
                help="The central dialogue group returned by each request.",
            )
            previous_context = q2.number_input(
                "Previous context",
                min_value=0,
                max_value=20,
                value=8,
                help="Earlier subtitles supplied as read-only context.",
            )
            next_context = q3.number_input(
                "Following context",
                min_value=0,
                max_value=20,
                value=8,
                help="Upcoming subtitles supplied as read-only context.",
            )
            consistency_pass = st.checkbox(
                "Run a second consistency pass",
                value=True,
                help=(
                    "Reviews groups of translations in a larger dialogue window for "
                    "consistent tone, pronouns, terminology, idioms, and jokes."
                ),
            )
            review_temperature = st.slider(
                "Consistency review temperature",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.05,
                disabled=not consistency_pass,
                help="A slightly lower value keeps revisions focused and stable.",
            )
            q4, q5 = st.columns(2)
            consistency_group_size = q4.number_input(
                "Translations reviewed together",
                min_value=1,
                max_value=15,
                value=8,
                disabled=not consistency_pass,
            )
            consistency_context = q5.number_input(
                "Review context on each side",
                min_value=0,
                max_value=20,
                value=8,
                disabled=not consistency_pass,
                help="The default reviews 8 lines inside a window of up to 24 lines.",
            )
            retry_invalid = st.checkbox(
                "Retry malformed output in smaller groups",
                value=True,
                help=(
                    "If a model loses an ID marker, split the group and retry; a "
                    "single-line request is the final compatibility fallback."
                ),
            )
        else:
            translation_group_size = 1
            previous_context = 0
            next_context = 0
            consistency_pass = False
            consistency_group_size = 8
            consistency_context = 8
            review_temperature = 0.3
            retry_invalid = True

    file_t = st.file_uploader("Upload Subtitle File", type=['srt', 'ass'])
    
    if file_t:
        st.info(f"📄 Loaded: {file_t.name} ({file_t.size / 1024:.1f} KB)")
    
    col1, col2 = st.columns([1, 4])
    if col1.button("🌍 Start Translation", type="primary") and file_t:
        try:
            with temporary_workspace("translate") as workspace:
                raw_path = save_uploaded_file(file_t, workspace)
                clean_path = workspace / "normalized.srt"
                normalize_subtitle(str(raw_path), str(clean_path))
                subs = pysubs2.load(str(clean_path), encoding="utf-8")

                bar = st.progress(0)
                preview = st.empty()
                initial_group = 1 if translation_mode == "individual" else int(translation_group_size)
                initial_steps = (len(subs) + initial_group - 1) // initial_group
                completed_step = 0

                for prog, orig, trans in translate_subs(
                    subs,
                    url,
                    mod,
                    sl,
                    tl,
                    ctx,
                    mode=translation_mode,
                    group_size=int(translation_group_size),
                    previous_context=int(previous_context),
                    next_context=int(next_context),
                    temperature=float(temperature),
                    review_temperature=float(review_temperature),
                    consistency_pass=consistency_pass,
                    consistency_group_size=int(consistency_group_size),
                    consistency_context=int(consistency_context),
                    retry_invalid=retry_invalid,
                ):
                    bar.progress(prog)
                    reviewing = consistency_pass and completed_step >= initial_steps
                    completed_step += 1
                    with preview.container():
                        st.caption(
                            "Consistency review"
                            if reviewing
                            else "Initial contextual translation"
                        )
                        ca, cb = st.columns(2)
                        ca.caption("First-pass translation" if reviewing else "Source")
                        cb.caption("Reviewed translation" if reviewing else "Translation")
                        ca.code("\n".join(orig), language="text")
                        cb.code("\n".join(trans), language="text")

                st.session_state.t_res = {
                    "n": safe_filename(f"Translated_{sl}_to_{tl}_{file_t.name}"),
                    "d": subs.to_string(format_="srt"),
                }
            st.success("✅ Translation complete!")
            
        except Exception as e:
            st.error(f"Translation failed: {e}")
            st.info("Check that LM Studio is running and the model is loaded")
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
                except (TypeError, ValueError):
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
        try:
            with temporary_workspace("sync") as workspace:
                raw_path = save_uploaded_file(file_s, workspace)
                clean_path = workspace / "normalized.srt"
                normalize_subtitle(str(raw_path), str(clean_path))

                subs = pysubs2.load(str(clean_path), encoding="utf-8")
                shift_subtitles(subs, sh, sp)

                st.session_state.s_res = {
                    "n": safe_filename(f"Synced_{file_s.name}"),
                    "d": subs.to_string(format_="srt"),
                }
            st.success(f"✅ Applied: {sh}ms shift at {sp}x speed")
        except Exception as e:
            st.error(f"Sync failed: {e}")

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
            custom_pattern = None
            if find_text:
                try:
                    custom_pattern = re.compile(find_text)
                except re.error as error:
                    st.error(f"Invalid regular expression: {error}")
                    st.stop()
            
            for idx, f in enumerate(clean_files):
                status_text.text(f"Cleaning {f.name}... ({idx+1}/{len(clean_files)})")
                try:
                    with temporary_workspace("sanitize") as workspace:
                        raw_path = save_uploaded_file(f, workspace)
                        fixed_path = workspace / f"normalized{raw_path.suffix}"

                        if fix_encoding:
                            normalize_subtitle(str(raw_path), str(fixed_path))
                        else:
                            fixed_path.write_bytes(raw_path.read_bytes())

                        subs = pysubs2.load(str(fixed_path), encoding="utf-8")
                        new_lines = []
                        ad_patterns = [
                            r"subtitles? by",
                            r"corrected by",
                            r"www\.",
                            r"\.com",
                            r"opensubtitles",
                            r"addic7ed",
                            r"subscene",
                            r"yify",
                        ]

                        for line in subs:
                            if rem_hi:
                                line.text = re.sub(r"\[.*?\]|\(.*?\)", "", line.text)
                            if custom_pattern is not None:
                                line.text = custom_pattern.sub(replace_text, line.text)

                            line.text = line.text.strip()
                            is_ad = rem_ads and any(
                                re.search(pattern, line.text, re.IGNORECASE)
                                for pattern in ad_patterns
                            )
                            is_empty = rem_empty and not line.text
                            if not is_ad and not is_empty:
                                new_lines.append(line)

                        subs.lines = new_lines
                        subs.save(str(fixed_path), encoding="utf-8")
                        output_name = safe_filename(f"Clean_{f.name}")
                        results[output_name] = read_nonempty_bytes(fixed_path)
                    
                except Exception as e:
                    st.error(f"Error cleaning {f.name}: {e}")
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
        analysis_results = {}
        repair_results = {}
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, f in enumerate(repair_files):
            status_text.text(f"Processing {f.name}... ({idx+1}/{len(repair_files)})")
            display_name = safe_filename(f.name)

            try:
                with temporary_workspace("repair") as workspace:
                    input_path = save_uploaded_file(f, workspace)
                    analysis = analyze_corruption(str(input_path))
                    analysis_results[display_name] = analysis

                    if repair_mode == "🔧 Analyze & Repair":
                        output_path = workspace / f"repaired{input_path.suffix}"
                        success, corruption_type, applied_fix = repair_corrupted_encoding(
                            str(input_path),
                            str(output_path),
                            target_script,
                        )

                        if success:
                            output_name = safe_filename(f"Repaired_{display_name}")
                            repair_results[output_name] = read_nonempty_bytes(output_path)
                            analysis_results[display_name]["repair_status"] = (
                                "✅ Successfully repaired"
                            )
                            analysis_results[display_name]["repair_method"] = applied_fix
                            analysis_results[display_name]["corruption_type"] = corruption_type
                        else:
                            analysis_results[display_name]["repair_status"] = (
                                "❌ Could not repair"
                            )
                            analysis_results[display_name]["repair_method"] = "none"
            except Exception as e:
                analysis_results[display_name] = {
                    "error": str(e),
                    "repair_status": "❌ Error during analysis",
                }

            progress_bar.progress((idx + 1) / len(repair_files))

        st.session_state.repair_analysis = analysis_results
        st.session_state.repair_res = repair_results
        status_text.success(f"✅ Completed analysis of {len(repair_files)} file(s)")

    if st.session_state.repair_analysis:
        st.divider()
        st.subheader("📊 Analysis Results")

        for filename, analysis in st.session_state.repair_analysis.items():
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

    if st.session_state.repair_res:
        st.divider()
        st.subheader("📥 Download Repaired Files")

        if len(st.session_state.repair_res) > 1:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                for name, data in st.session_state.repair_res.items():
                    zf.writestr(name, data)

            st.download_button(
                "📥 Download All Repaired (ZIP)",
                zip_buf.getvalue(),
                "repaired_subtitles.zip",
                use_container_width=True,
            )

        for name, data in st.session_state.repair_res.items():
            col_name, col_size, col_dl = st.columns([4, 1, 1])
            col_name.success(f"✅ {name}")
            col_size.caption(f"{len(data) / 1024:.1f} KB")
            col_dl.download_button("⬇️", data, file_name=name, key=f"dl_repair_{name}")

        if st.button("🗑️ Clear Repair Results", key="clear_repair"):
            st.session_state.repair_analysis = {}
            st.session_state.repair_res = {}
            st.rerun()
    
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
