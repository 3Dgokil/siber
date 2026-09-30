import streamlit as st
import subprocess
import os
import re

# Setelan halaman dashboard Streamlit
st.set_page_config(page_title="YT Multi-Video Live Streamer", page_icon="🎬", layout="centered")

st.title("🎬 YouTube Loop Live Streamer")
st.write("Alat live streaming 24 jam ke YouTube dengan memutar 6 video secara bergantian (looping).")

# Fungsi otomatis untuk mengubah Link Google Drive biasa menjadi Direct Link FFmpeg
def convert_to_direct_link(url):
    url = url.strip()
    if not url:
        return ""
    # Deteksi ID unik dari link Google Drive biasa maupun link download
    match = re.search(r'(?:file/d/|id=)([\w-]+)', url)
    if match:
        video_id = match.group(1)
        return f"https://google.com{video_id}"
    return url  # Kembalikan url asli jika bukan link google drive

# 1. Input Stream Key YouTube
stream_key = st.text_input(
    "🔑 Masukkan YouTube Stream Key Anda:", 
    type="password", 
    help="Masukkan kode streaming rahasia dari YouTube Live Control Room."
)

st.markdown("---")
st.subheader("🔗 Masukkan Link Google Drive Video (Urutan 1 - 6)")
st.caption("Salin langsung link dari Google Drive Anda (Pastikan aksesnya sudah diubah ke 'Siapa saja yang memiliki link').")

# 2. Input 6 Link URL Video (Cukup masukkan link Drive biasa)
raw_urls = []
for i in range(1, 7):
    url = st.text_input(
        f"Video {i} Google Drive Link:", 
        placeholder="https://google.com", 
        key=f"url_{i}"
    )
    raw_urls.append(url)

st.markdown("---")

# Cek status proses streaming di session state agar tombol sinkron
if "streaming_process" not in st.session_state:
    st.session_state.streaming_process = None

# Tata letak tombol aksi
col1, col2 = st.columns(2)

with col1:
    btn_start = st.button("🚀 Mulai Live Stream 24 Jam", use_container_width=True, type="primary")
with col2:
    btn_stop = st.button("🛑 Hentikan Live Stream", use_container_width=True, disabled=(st.session_state.streaming_process is None))

# LOGIKA MULAI LIVE STREAM
if btn_start:
    # Validasi Input Kosong
    empty_urls = [u for u in raw_urls if not u.strip()]
    
    if not stream_key:
        st.error("❌ Stream Key wajib diisi!")
    elif len(empty_urls) > 0:
        st.error(f"❌ Harap isi semua 6 link video! Masih ada {len(empty_urls)} kolom kosong.")
    elif st.session_state.streaming_process is not None:
        st.warning("⚠️ Live streaming saat ini sedang berjalan!")
    else:
        st.info("⏳ Memproses link video dan membuat skrip loop internal...")
        
        # Proses konversi otomatis ke Direct Link
        direct_urls = [convert_to_direct_link(url) for url in raw_urls]
        
        playlist_path = "playlist_live.txt"
        try:
            # Trik Rahasia Concat Looping: 
            # Menggunakan header ffconcat version 1.0 dan memanggil file itu sendiri di akhir agar berputar selamanya
            with open(playlist_path, "w") as f:
                f.write("ffconcat version 1.0\n")
                for d_url in direct_urls:
                    f.write(f"file '{d_url}'\n")
                # Baris sakti: memanggil dirinya sendiri agar looping tidak putus
                f.write(f"file '{playlist_path}'\n")
            
            # PERINTAH FFmpeg FINAL DENGAN USER-AGENT BYPASS GOOGLE
            cmd = [
                "ffmpeg", 
                "-protocol_whitelist", "file,http,https,tcp,tls", 
                "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "-re", 
                "-f", "concat", 
                "-safe", "0", 
                "-i", playlist_path,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
                "-pix_fmt", "yuv420p", "-g", "60", 
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                "-f", "flv", f"rtmp://://youtube.com{stream_key}"
            ]
            
            # Jalankan FFmpeg dan rekam jika terjadi error log
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            st.session_state.streaming_process = process
            
            st.success("🎉 Perintah dikirim! Sistem sedang menghubungkan video ke server YouTube...")
            st.balloons()
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Terjadi kesalahan sistem: {e}")

# LOGIKA HENTIKAN LIVE STREAM
if btn_stop:
    if st.session_state.streaming_process is not None:
        st.session_state.streaming_process.terminate()  # Mematikan proses FFmpeg
        st.session_state.streaming_process = None
        
        # Hapus file daftar putar teks jika ada
        if os.path.exists("playlist_live.txt"):
            os.remove("playlist_live.txt")
            
        st.success("🛑 Live streaming telah dihentikan secara manual.")
        st.rerun()

st.markdown("---")
# Papan Pemantau Log FFmpeg secara Real-time untuk mendeteksi pemblokiran Google Drive
if st.session_state.streaming_process is not None:
    st.subheader("📊 Pemantau Log FFmpeg Cloud")
    st.caption("Jika live belum muncul di YT, cek pesan di bawah ini:")
    
    # Baca 5 baris log terakhir yang dikeluarkan oleh server
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
