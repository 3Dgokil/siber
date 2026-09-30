import streamlit as st
import subprocess
import os

st.set_page_config(page_title="YT Cloud RTMPS Streamer", page_icon="🎬", layout="centered")

st.title("🎬 YouTube Cloud RTMPS Streamer")
st.write("Mencoba bypass port menggunakan jalur RTMPS Port 443.")

# 1. Input Stream Key YouTube
stream_key = st.text_input(
    "🔑 Masukkan YouTube Stream Key Anda:", 
    type="password", 
    help="Masukkan kode streaming rahasia dari YouTube Live Control Room."
)

st.markdown("---")
st.subheader("📁 Unggah Video Secara Bergantian (Maksimal 6 Video)")
st.caption("Unggah video satu per satu. Pastikan status upload per video sudah selesai (100%) baru lanjut.")

uploaded_files = []
for i in range(1, 7):
    file = st.file_uploader(f"🎬 Unggah Video {i} (.mp4):", type=["mp4"], key=f"upload_slot_{i}")
    if file is not None:
        uploaded_files.append(file)

st.markdown("---")

if "streaming_process" not in st.session_state:
    st.session_state.streaming_process = None

col1, col2 = st.columns(2)
with col1:
    btn_start = st.button("🚀 Mulai Live Stream 24 Jam", use_container_width=True, type="primary")
with col2:
    btn_stop = st.button("🛑 Hentikan Live Stream", use_container_width=True, disabled=(st.session_state.streaming_process is None))

if btn_start:
    if not stream_key:
        st.error("❌ Stream Key wajib diisi!")
    elif len(uploaded_files) == 0:
        st.error("❌ Minimal unggah 1 video terlebih dahulu!")
    elif st.session_state.streaming_process is not None:
        st.warning("⚠️ Live streaming saat ini sedang berjalan!")
    else:
        st.info("⏳ Menyimpan file video secara bertahap ke server cloud...")
        
        clean_key = stream_key.strip()
        
        video_paths = []
        for index, uploaded_file in enumerate(uploaded_files):
            temp_path = f"local_video_{index}.mp4"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            video_paths.append(temp_path)
            
        playlist_path = "playlist_local.txt"
        try:
            with open(playlist_path, "w") as f:
                f.write("ffconcat version 1.0\n")
                for path in video_paths:
                    f.write(f"file '{path}'\n")
                f.write(f"file '{playlist_path}'\n")
            
            rtmps_base = "rtmps://://youtube.com"
            rtmps_full_target = rtmps_base + clean_key
            
            cmd = [
                "ffmpeg", 
                "-protocol_whitelist", "file,crypto,tcp,tls,https", 
                "-re", 
                "-f", "concat", 
                "-safe", "0", 
                "-i", playlist_path,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2000k", "-maxrate", "2000k", "-bufsize", "4000k",
                "-pix_fmt", "yuv420p", "-g", "60", 
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-f", "flv", rtmps_full_target
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            st.session_state.streaming_process = process
            
            st.success("🎉 Format string diperbarui dan dikirim! Silakan pantau log aman di bawah.")
            st.balloons()
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Terjadi kesalahan sistem: {e}")

if btn_stop:
    if st.session_state.streaming_process is not None:
        st.session_state.streaming_process.terminate()
        st.session_state.streaming_process = None
        if os.path.exists("playlist_local.txt"):
            os.remove("playlist_local.txt")
        for file in os.listdir("."):
            if file.startswith("local_video_") and file.endswith(".mp4"):
                os.remove(file)
        st.success("🛑 Live streaming telah dihentikan.")
        st.rerun()

st.markdown("---")
if st.session_state.streaming_process is not None:
    st.subheader("📊 Pemantau Log Real-time (Disensor)")
    log_area = st.empty()
    logs = ""
    try:
        for _ in range(60):
            line = st.session_state.streaming_process.stdout.readline()
            if line:
                # SISTEM SENSOR OTOMATIS: Jika isi log mengandung stream key, potong & sembunyikan kodenya
                if stream_key in line:
                    line = line.replace(stream_key, "[STREAM_KEY_DISEMBUNYIKAN]")
                logs += line
            else:
                break
        log_area.code(logs)
    except:
        pass
