import streamlit as st
import subprocess
import os

st.set_page_config(page_title="YT Local Multi-Video Live Streamer", page_icon="🎬", layout="centered")

st.title("🎬 YouTube Direct Upload Live Streamer")
st.write("Live streaming 24 jam dengan mengunggah langsung file video dari HP/PC ke server Cloud.")

# 1. Input Stream Key YouTube
stream_key = st.text_input(
    "🔑 Masukkan YouTube Stream Key Anda:", 
    type="password", 
    help="Masukkan kode streaming rahasia dari YouTube Live Control Room."
)

st.markdown("---")
st.subheader("📁 Unggah File Video Anda")
st.caption("Pilih atau seret ke-6 file video .mp4 Anda sekaligus. Pastikan total ukuran tidak melebihi kapasitas server.")

# 2. Multi-file Uploader (Bisa pilih banyak video sekaligus)
uploaded_files = st.file_uploader(
    "Pilih file video (.mp4):", 
    type=["mp4"], 
    accept_multiple_files=True
)

st.markdown("---")

if "streaming_process" not in st.session_state:
    st.session_state.streaming_process = None

col1, col2 = st.columns(2)
with col1:
    btn_start = st.button("🚀 Mulai Live Stream 24 Jam", use_container_width=True, type="primary")
with col2:
    btn_stop = st.button("🛑 Hentikan Live Stream", use_container_width=True, disabled=(st.session_state.streaming_process is None))

# LOGIKA MULAI LIVE STREAM
if btn_start:
    if not stream_key:
        st.error("❌ Stream Key wajib diisi!")
    elif not uploaded_files:
        st.error("❌ Harap unggah video terlebih dahulu!")
    elif st.session_state.streaming_process is not None:
        st.warning("⚠️ Live streaming saat ini sedang berjalan!")
    else:
        st.info("⏳ Menyimpan file video ke server lokal cloud...")
        
        # Simpan file yang diunggah ke penyimpanan lokal server cloud
        video_paths = []
        for i, uploaded_file in enumerate(uploaded_files):
            # Beri nama urut sesuai urutan unggah (video_0.mp4, video_1.mp4, dst)
            temp_path = f"local_video_{i}.mp4"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            video_paths.append(temp_path)
            
        playlist_path = "playlist_local.txt"
        try:
            # Membuat format ffconcat version 1.0 dengan trik loop internal mandiri
            with open(playlist_path, "w") as f:
                f.write("ffconcat version 1.0\n")
                for path in video_paths:
                    f.write(f"file '{path}'\n")
                # Looping kembali ke file ini agar berputar 24 jam nonstop
                f.write(f"file '{playlist_path}'\n")
            
            # PERINTAH FFmpeg UNTUK FILE LOKAL (Sangat Ringan & Stabil)
            cmd = [
                "ffmpeg", 
                "-protocol_whitelist", "file,crypto,tcp", 
                "-re", 
                "-f", "concat", 
                "-safe", "0", 
                "-i", playlist_path,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
                "-pix_fmt", "yuv420p", "-g", "60", 
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-f", "flv", f"rtmp://://youtube.com{stream_key}"
            ]
            
            # Jalankan FFmpeg di latar belakang
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            st.session_state.streaming_process = process
            
            st.success("🎉 Sukses! Video berhasil dimuat secara lokal. Silakan cek YouTube Studio Anda dalam 30 detik.")
            st.balloons()
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Terjadi kesalahan sistem: {e}")

# LOGIKA HENTIKAN LIVE STREAM
if btn_stop:
    if st.session_state.streaming_process is not None:
        st.session_state.streaming_process.terminate()
        st.session_state.streaming_process = None
        
        # Bersihkan file sampah video dan playlist di server
        if os.path.exists("playlist_local.txt"):
            os.remove("playlist_local.txt")
            
        # Cari dan hapus semua file video lokal sementara
        for file in os.listdir("."):
            if file.startswith("local_video_") and file.endswith(".mp4"):
                os.remove(file)
                
        st.success("🛑 Live streaming telah dihentikan dan file sampah dibersihkan.")
        st.rerun()

st.markdown("---")
# Papan Pemantau Log Real-time
if st.session_state.streaming_process is not None:
    st.subheader("📊 Pemantau Log Real-time")
    log_area = st.empty()
    logs = ""
    try:
        for _ in range(5):
            line = st.session_state.streaming_process.stdout.readline()
            if line:
                logs += line
        log_area.code(logs)
    except:
        pass
