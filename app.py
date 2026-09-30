import streamlit as st
import subprocess
import os

st.set_page_config(page_title="YT Cloud RTMPS Streamer", page_icon="🎬", layout="centered")

st.title("🎬 YouTube Cloud RTMPS Streamer")
st.write("Mencoba bypass blokir port server cloud menggunakan jalur aman RTMPS Port 443.")

# 1. Input Stream Key YouTube
stream_key = st.text_input(
    "🔑 Masukkan YouTube Stream Key Anda:", 
    type="password", 
    help="Masukkan kode streaming rahasia dari YouTube Live Control Room."
)

st.markdown("---")
st.subheader("📁 Unggah Video Secara Bergantian (Maksimal 6 Video)")
st.caption("Unggah video satu per satu. Pastikan status upload per video sudah selesai (100%) baru lanjut ke slot berikutnya.")

# Membuat 6 kolom upload mandiri
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

# LOGIKA MULAI LIVE STREAM
if btn_start:
    if not stream_key:
        st.error("❌ Stream Key wajib diisi!")
    elif len(uploaded_files) == 0:
        st.error("❌ Minimal unggah 1 video terlebih dahulu!")
    elif st.session_state.streaming_process is not None:
        st.warning("⚠️ Live streaming saat ini sedang berjalan!")
    else:
        st.info(f"⏳ Menyimpan {len(uploaded_files)} file video secara bertahap ke server cloud...")
        
        # Simpan file dari memori ke penyimpanan fisik server cloud
        video_paths = []
        for index, uploaded_file in enumerate(uploaded_files):
            temp_path = f"local_video_{index}.mp4"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            video_paths.append(temp_path)
            
        playlist_path = "playlist_local.txt"
        try:
            # Membuat format ffconcat dengan trik loop internal mandiri
            with open(playlist_path, "w") as f:
                f.write("ffconcat version 1.0\n")
                for path in video_paths:
                    f.write(f"file '{path}'\n")
                # Looping kembali ke file teks agar berputar selamanya
                f.write(f"file '{playlist_path}'\n")
            
            # PERINTAH FFmpeg PERBAIKAN SINTAKS AUDIO & JALUR RTMPS
            cmd = [
                "ffmpeg", 
                "-protocol_whitelist", "file,crypto,tcp,tls,https", 
                "-re", 
                "-f", "concat", 
                "-safe", "0", 
                "-i", playlist_path,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2000k", "-maxrate", "2000k", "-bufsize", "4000k",
                "-pix_fmt", "yuv420p", "-g", "60", 
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",  # Diperbaiki menjadi string teks utuh
                "-f", "flv", f"rtmps://://youtube.com{stream_key}"
            ]
            
            # Jalankan FFmpeg di latar belakang server cloud
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            st.session_state.streaming_process = process
            
            st.success("🎉 Perintah dikirim via RTMPS Port 443! Silakan pantau log di bawah dan YouTube Studio Anda.")
            st.balloons()
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Terjadi kesalahan sistem: {e}")

# LOGIKA HENTIKAN LIVE STREAM
if btn_stop:
    if st.session_state.streaming_process is not None:
        st.session_state.streaming_process.terminate()
        st.session_state.streaming_process = None
        
        # Bersihkan file sampah teks playlist
        if os.path.exists("playlist_local.txt"):
            os.remove("playlist_local.txt")
            
        # Cari dan hapus semua file video lokal sementara di server
        for file in os.listdir("."):
            if file.startswith("local_video_") and file.endswith(".mp4"):
                os.remove(file)
                
        st.success("🛑 Live streaming dihentikan dan semua file video di server telah dihapus.")
        st.rerun()

st.markdown("---")
# Papan Pemantau Log Real-time diperpanjang agar membaca lebih banyak baris log terbaru
if st.session_state.streaming_process is not None:
    st.subheader("📊 Pemantau Log Real-time")
    log_area = st.empty()
    logs = ""
    try:
        # Membaca hingga 50 baris untuk memunculkan pesan error / status transmisi video
        for _ in range(50):
            line = st.session_state.streaming_process.stdout.readline()
            if line:
                logs += line
            else:
                break
        log_area.code(logs)
    except:
        pass
