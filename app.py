import streamlit as st
import os, zipfile, io, pysubs2
from sub_engine import merge_subtitles, extract_episode_code, translate_subs, shift_subtitles, normalize_subtitle

st.set_page_config(page_title="Roro's Subtitle Forge", layout="wide", page_icon="🎬")

# Session State Initialization
for key in ["m_res", "t_res", "s_res", "clean_res"]:
    if key not in st.session_state: st.session_state[key] = {} if "res" in key else None

st.title("🎬 Roro's Subtitle Forge")
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
    
    kw_b = st.text_input("Track B Keyword (e.g. DEMAND.fr)", value="DEMAND.fr")
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
        
        # Download All as ZIP at the top of results
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for name, data in st.session_state.m_res.items():
                zf.writestr(name, data)
        
        st.download_button(
            "📥 Download All (ZIP)", 
            zip_buffer.getvalue(), 
            file_name="merged_subtitles.zip", 
            use_container_width=True,
            type="secondary"
        )
        
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
    st.header("Sync & Drift Fix")
    c_s, c_d = st.columns(2)
    sh, sp = c_s.number_input("Shift (ms)", 0, step=50), c_d.number_input("Speed Factor", 1.0, format="%.4f", step=0.001)
    file_s = st.file_uploader("Upload to Fix", key="sync_up")
    if st.button("⚡ Apply") and file_s:
        with open("raw_s.srt", "wb") as f: f.write(file_s.getbuffer())
        normalize_subtitle("raw_s.srt", "clean_s.srt")
        subs = pysubs2.load("clean_s.srt", encoding="utf-8")
        shift_subtitles(subs, sh, sp)
        st.session_state.s_res = {"n": f"Fixed_{file_s.name}", "d": subs.to_string(format_="srt")}
    if st.session_state.s_res:
        st.download_button("📥 Download", st.session_state.s_res['d'], file_name=st.session_state.s_res['n'])

# --- TAB 4: SANITIZER ---
with tabs[3]:
    st.header("🧼 Subtitle Sanitizer")
    st.write("Upload any file to instantly convert it to clean UTF-8 SRT with standard formatting.")
    clean_files = st.file_uploader("Upload Subtitles to Clean", accept_multiple_files=True, key="clean_up")
    
    if st.button("🧼 Clean Files", type="primary"):
        if clean_files:
            results = {}
            for f in clean_files:
                with open("raw_clean.srt", "wb") as tmp: tmp.write(f.getbuffer())
                normalize_subtitle("raw_clean.srt", "fixed.srt")
                with open("fixed.srt", "rb") as fixed: results[f"Clean_{f.name}"] = fixed.read()
            st.session_state.clean_res = results
            st.rerun()

    if st.session_state.clean_res:
        st.divider()
        for name, data in st.session_state.clean_res.items():
            col_n, col_d = st.columns([3, 1])
            col_n.write(f"✅ {name}")
            col_d.download_button("Download", data, file_name=name, key=f"clean_dl_{name}")