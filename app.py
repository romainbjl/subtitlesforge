import streamlit as st
import os
import zipfile
import io
import pysubs2
from sub_engine import merge_subtitles, extract_episode_code, translate_subs, shift_subtitles

st.set_page_config(page_title="Roro's Subtitle Forge", layout="wide", page_icon="🎬")

# --- Session State Initialization ---
if "merged_results" not in st.session_state: st.session_state.merged_results = {}
if "translated_result" not in st.session_state: st.session_state.translated_result = None
if "shifted_result" not in st.session_state: st.session_state.shifted_result = None

st.title("🎬 Subtitle Forge")

tabs = st.tabs(["🔗 Merger & Sync", "🤖 AI Translator", "⏱️ Quick Shift & Drift"])

# --- TAB 1: BATCH MERGER ---
with tabs[0]:
    st.header("Batch Merge & Sync")
    
    with st.expander("⚙️ Configuration", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            s_a = st.number_input("Track A Shift (ms)", value=0, step=50)
            s_b = st.number_input("Track B Shift (ms)", value=0, step=50)
        with c2:
            s_g = st.number_input("Global Shift (ms)", value=0, step=50)
            threshold = st.number_input("Merge Threshold (ms)", value=1000)
        with c3:
            color_track = st.selectbox("Color track?", ["None", "Track A", "Track B"], index=2)
            picked_hex = st.color_picker("Color", "#FFFF54")
            track_b_kw = st.text_input("Track B Keyword", value="FR")

    files = st.file_uploader("Upload pairs of subtitles", accept_multiple_files=True, key="m_up")

    if st.button("🚀 Process & Merge", type="primary"):
        if files:
            st.session_state.merged_results = {}
            groups = {}
            for f in files:
                code = extract_episode_code(f.name)
                groups.setdefault(code, []).append(f)
            
            for code, pair in groups.items():
                if len(pair) == 2:
                    # Identify files
                    if track_b_kw.lower() in pair[0].name.lower():
                        tb_f, ta_f = pair[0], pair[1]
                    else:
                        ta_f, tb_f = pair[0], pair[1]
                    
                    with open("temp_a.srt", "wb") as f: f.write(ta_f.getbuffer())
                    with open("temp_b.srt", "wb") as f: f.write(tb_f.getbuffer())
                    
                    out_name = f"Merged_{code}.srt"
                    merge_subtitles("temp_a.srt", "temp_b.srt", out_name, threshold, picked_hex, color_track, s_a, s_b, s_g)
                    
                    with open(out_name, "rb") as f:
                        st.session_state.merged_results[out_name] = f.read()
                    
                    for tmp in ["temp_a.srt", "temp_b.srt", out_name]:
                        if os.path.exists(tmp): os.remove(tmp)
            st.rerun()

    if st.session_state.merged_results:
        st.divider()
        for name, data in st.session_state.merged_results.items():
            col_n, col_d = st.columns([3, 1])
            col_n.write(f"📄 {name}")
            col_d.download_button("Download", data, file_name=name, key=f"dl_{name}")

# --- TAB 2: AI TRANSLATOR ---
with tabs[1]:
    st.header("AI Subtitle Translation")
    
    c_api, c_lang = st.columns(2)
    with c_api:
        api_url = st.text_input("LM Studio URL", value="http://localhost:1234/v1")
        model_id = st.text_input("Model ID", value="mario-sigma-lm")
    with c_lang:
        src_l = st.text_input("From", value="English")
        tgt_l = st.text_input("To", value="French")

    context = st.text_area("Context / Summary", placeholder="Enter show context to help the AI...")
    t_file = st.file_uploader("Upload to translate", type=['srt', 'ass'], key="t_up")

    col_s1, col_s2 = st.columns([1, 4])
    if col_s1.button("🌍 Translate", type="primary"):
        if t_file:
            with open("temp_t.srt", "wb") as f: f.write(t_file.getbuffer())
            # Safe load within app
            try:
                subs = pysubs2.load("temp_t.srt", encoding="utf-8")
            except:
                subs = pysubs2.load("temp_t.srt")
            
            p_bar = st.progress(0)
            preview = st.empty()
            
            try:
                # The translate_subs generator handles the work
                for prog, orig, trans in translate_subs(subs, api_url, model_id, src_l, tgt_l, context):
                    p_bar.progress(prog, text=f"Translating: {int(prog*100)}%")
                    with preview.container():
                        st.markdown("### 👁️ Live Monitor")
                        ca, cb = st.columns(2)
                        ca.info("Original"); ca.code("\n".join(orig))
                        cb.success("AI Translated"); cb.code("\n".join(trans))
                
                st.session_state.translated_result = {"name": f"AI_{t_file.name}", "data": subs.to_string(format_="srt")}
                st.success("Done!")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                if os.path.exists("temp_t.srt"): os.remove(temp_t.srt)

    if col_s2.button("🛑 Stop"):
        st.warning("Stopping... (Script will halt on next batch)")
        st.stop()

    if st.session_state.translated_result:
        st.download_button("📥 Download AI Sub", st.session_state.translated_result['data'], file_name=st.session_state.translated_result['name'])

# --- TAB 3: QUICK SHIFT & DRIFT ---
with tabs[2]:
    st.header("Quick Sync Fixer")
    st.write("Fix simple delays or progressive drift (frame rate mismatch).")
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        q_shift = st.number_input("Linear Shift (ms)", value=0, step=50)
    with col_v2:
        q_speed = st.number_input("Speed Factor (Drift)", value=1.0000, format="%.4f", step=0.0005)
        st.caption("Common factors: 0.9590 (23.9 to 25) | 1.0427 (25 to 23.9)")

    q_up = st.file_uploader("Upload file", type=['srt', 'ass'], key="q_up")

    if st.button("⚡ Apply Sync Fix"):
        if q_up:
            with open("temp_q.srt", "wb") as f: f.write(q_up.getbuffer())
            try:
                subs = pysubs2.load("temp_q.srt", encoding="utf-8")
            except:
                subs = pysubs2.load("temp_q.srt")
            
            shift_subtitles(subs, q_shift, q_speed)
            
            st.session_state.shifted_result = {
                "name": f"Fixed_{q_up.name}",
                "data": subs.to_string(format_="srt")
            }
            if os.path.exists("temp_q.srt"): os.remove("temp_q.srt")
            st.success("Sync parameters applied!")

    if st.session_state.shifted_result:
        st.download_button(f"📥 Download {st.session_state.shifted_result['name']}", 
                           st.session_state.shifted_result['data'], 
                           file_name=st.session_state.shifted_result['name'])