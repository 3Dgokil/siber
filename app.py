import sys
import subprocess
import threading
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

# Install streamlit jika belum ada
try:
    import streamlit as st
    import streamlit.components.v1 as components
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    import streamlit as st
    import streamlit.components.v1 as components


APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = APP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Dipakai agar tombol Stop bisa menghentikan proses FFmpeg yang sedang aktif.
FFMPEG_PROCESS = None
PROCESS_LOCK = threading.Lock()


def safe_filename(name: str) -> str:
    """Buat nama file aman untuk disimpan di server."""
    name = Path(name).name
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- ()"
    cleaned = "".join(c if c in allowed else "_" for c in name).strip()
    return cleaned or "video.mp4"


def save_uploaded_file(uploaded_file, slot: int) -> str:
    """Simpan upload ke folder uploads dengan nama slot agar urutannya jelas."""
    original = safe_filename(uploaded_file.name)
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()
    filename = f"video_{slot}_{stem}{suffix}"
    path = UPLOAD_DIR / filename
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(path)


def download_video_from_url(url: str, slot: int, filename_hint: str = "") -> str:
    """Download video dari URL langsung atau Google Drive ke server."""
    url = url.strip()
    if not url:
        raise ValueError("Link video kosong.")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Link harus diawali http:// atau https://")

    # Google Drive: gunakan gdown agar link sharing file dapat diunduh.
    if "drive.google.com" in parsed.netloc or "docs.google.com" in parsed.netloc:
        try:
            import gdown
        except ImportError as exc:
            raise RuntimeError("Library gdown belum terpasang. Tambahkan gdown di requirements.txt.") from exc
        hint = safe_filename(filename_hint or f"video_{slot}.mp4")
        if not Path(hint).suffix:
            hint += ".mp4"
        target = UPLOAD_DIR / f"video_{slot}_drive_{hint}"
        result = gdown.download(url=url, output=str(target), quiet=True, fuzzy=True)
        if not result or not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("Google Drive gagal diunduh. Pastikan file disetel 'Anyone with the link'.")
        return str(target)

    # URL file langsung (MP4/MKV/WebM, dll).
    hint = filename_hint.strip()
    if not hint:
        name = Path(urllib.parse.unquote(parsed.path)).name
        hint = name or f"video_{slot}.mp4"
    hint = safe_filename(hint)
    if not Path(hint).suffix:
        hint += ".mp4"
    target = UPLOAD_DIR / f"video_{slot}_link_{hint}"

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response, open(target, "wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("Link tidak menghasilkan file video.")
    return str(target)


def save_uploaded_audio(uploaded_file, slot: int) -> str:
    """Simpan MP3 berdasarkan slot agar urutan playlist selalu 1 -> 5."""
    original = safe_filename(uploaded_file.name)
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()
    filename = f"audio_{slot}_{stem}{suffix}"
    path = UPLOAD_DIR / filename
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(path)



def make_concat_playlist(video_paths, repeat_count=1):
    """Buat playlist FFmpeg Video 1 -> 5, dengan jumlah putaran eksplisit."""
    playlist = UPLOAD_DIR / "playlist.txt"
    repeat_count = max(1, int(repeat_count))
    with open(playlist, "w", encoding="utf-8") as f:
        for _ in range(repeat_count):
            for path in video_paths:
                p = Path(path).resolve().as_posix().replace("'", "'\\''")
                f.write(f"file '{p}'\n")
    return str(playlist)


def make_audio_playlist(audio_paths, repeat_count=1):
    """Buat playlist audio yang diulang secara eksplisit agar jumlah putaran pasti."""
    playlist = UPLOAD_DIR / "audio_playlist.txt"
    repeat_count = max(1, int(repeat_count))
    with open(playlist, "w", encoding="utf-8") as f:
        for _ in range(repeat_count):
            for path in audio_paths:
                p = Path(path).resolve().as_posix().replace("'", "'\\''")
                f.write(f"file '{p}'\n")
    return str(playlist)


def run_ffmpeg(mode, video_paths, audio_paths, stream_key, is_shorts, playback_mode, repeat_count, duration_hours, log_callback):
    global FFMPEG_PROCESS

    output_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
    duration_seconds = int(duration_hours * 3600) if playback_mode == "Durasi streaming" and duration_hours else None

    if mode == "Video + MP3":
        if not video_paths or not audio_paths:
            log_callback("ERROR: Mode Video + MP3 membutuhkan 1 video dan minimal 1 MP3.")
            return

        # Penting: audio sebelumnya dibaca terlalu cepat oleh FFmpeg karena hanya
        # input video yang memakai -re. Ini bisa membuat antrean audio membesar
        # dan live YouTube tersendat/putus. Sekarang kedua input dibaca realtime.
        if playback_mode == "Jumlah pengulangan":
            audio_playlist = make_audio_playlist(audio_paths, repeat_count)
            audio_loop_args = []
        else:
            audio_playlist = make_audio_playlist(audio_paths, 1)
            audio_loop_args = ["-stream_loop", "-1"]

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "info",
            "-thread_queue_size", "256",
            "-re",
            "-stream_loop", "-1",
            "-i", video_paths[0],
            "-thread_queue_size", "256",
            "-re",
        ]
        cmd += audio_loop_args
        cmd += [
            "-f", "concat",
            "-safe", "0",
            "-i", audio_playlist,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-r", "20",
            "-pix_fmt", "yuv420p",
            "-profile:v", "main",
            "-threads", "2",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "3600k",
            "-g", "50",
            "-keyint_min", "50",
            "-sc_threshold", "0",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-ac", "2",
            "-af", "aresample=async=1:first_pts=0",
            "-fps_mode", "cfr",
            "-max_interleave_delta", "0",
            "-avoid_negative_ts", "make_zero",
        ]

        if is_shorts:
            cmd += [
                "-vf",
                "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            ]
        else:
            # Target video landscape hingga 1080p dengan 20fps dan preset ultrafast agar CPU tetap serendah mungkin.
            cmd += [
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            ]

        if duration_seconds:
            cmd += ["-t", str(duration_seconds)]
        elif playback_mode == "Jumlah pengulangan":
            # Video di-loop, tetapi output wajib berhenti tepat setelah playlist
            # MP3 selesai sesuai jumlah pengulangan.
            cmd += ["-shortest"]

        cmd += [
            "-flvflags", "no_duration_filesize",
            "-muxdelay", "0",
            "-muxpreload", "0",
            "-f", "flv",
            output_url,
        ]

        log_callback("Mode: Video + MP3 — mode audio realtime")
        log_callback(f"Video loop: {Path(video_paths[0]).name}")
        log_callback("Urutan MP3:")
        for i, path in enumerate(audio_paths, 1):
            log_callback(f"  {i}. {Path(path).name}")
        log_callback("Audio dibaca realtime (-re) agar antrean tidak menumpuk.")
        if playback_mode == "Jumlah pengulangan":
            log_callback(f"Playlist MP3 diputar tepat {repeat_count} kali, lalu streaming berhenti.")
        elif playback_mode == "Durasi streaming":
            log_callback(f"Streaming dibatasi {duration_hours:g} jam.")
        else:
            log_callback("MP3: 1 → 2 → 3 → 4 → 5 → kembali ke 1, loop terus.")
        log_callback("Video di-loop terus; audio asli video tidak digunakan.")
        log_callback("Menjalankan FFmpeg ke YouTube...")

    else:
        if not video_paths:
            log_callback("ERROR: Minimal 1 video diperlukan.")
            return

        # Jumlah pengulangan dibuat eksplisit di file concat agar putarannya pasti.
        playlist_repeat = repeat_count if playback_mode == "Jumlah pengulangan" else 1
        playlist = make_concat_playlist(video_paths, playlist_repeat)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-re",
        ]

        if playback_mode == "Tanpa batas":
            cmd += ["-stream_loop", "-1"]

        cmd += [
            "-f", "concat",
            "-safe", "0",
            "-i", playlist,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-r", "20",
            "-pix_fmt", "yuv420p",
            "-profile:v", "main",
            "-threads", "2",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "3600k",
            "-g", "50",
            "-keyint_min", "50",
            "-sc_threshold", "0",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-af", "aresample=async=1:first_pts=0",
            "-fps_mode", "cfr",
        ]

        if is_shorts:
            cmd += [
                "-vf",
                "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            ]

        if duration_seconds:
            cmd += ["-t", str(duration_seconds)]

        cmd += ["-f", "flv", output_url]

        log_callback("Mode: 5 Video Playlist")
        log_callback("Urutan video:")
        for i, path in enumerate(video_paths, 1):
            log_callback(f"  {i}. {Path(path).name}")
        log_callback("Playlist: Video 1 → Video 2 → Video 3 → Video 4 → Video 5")
        if playback_mode == "Tanpa batas":
            log_callback("Playlist video akan loop terus.")
        elif playback_mode == "Jumlah pengulangan":
            log_callback(f"Playlist 5 Video diputar tepat {repeat_count} kali, lalu streaming berhenti.")
        elif playback_mode == "Durasi streaming":
            log_callback(f"Streaming dibatasi {duration_hours:g} jam.")
        log_callback("Menjalankan FFmpeg ke YouTube...")

    try:
        with PROCESS_LOCK:
            FFMPEG_PROCESS = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

        process = FFMPEG_PROCESS
        for line in process.stdout:
            line = line.strip()
            if line:
                log_callback(line)
        process.wait()
        log_callback(f"FFmpeg berhenti dengan kode: {process.returncode}")
    except FileNotFoundError:
        log_callback("ERROR: FFmpeg tidak ditemukan. Pastikan FFmpeg sudah terpasang dan tersedia di PATH.")
    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        with PROCESS_LOCK:
            FFMPEG_PROCESS = None
        log_callback("Streaming selesai atau dihentikan.")

def stop_ffmpeg():
    global FFMPEG_PROCESS
    with PROCESS_LOCK:
        process = FFMPEG_PROCESS
        if process and process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            except Exception:
                pass
        FFMPEG_PROCESS = None


def main():
    st.set_page_config(
        page_title="STREMQU | YouTube Live Streaming",
        page_icon="🎬",
        layout="wide"
    )
    # Histats hidden counter
    # Counter 5023868 / code 101. Tidak menampilkan elemen counter ke pengguna.
    st.markdown(
        """
        <a href="/" alt="hit counter" target="_blank" style="display:none;">
            <img src="//sstatic1.histats.com/0.gif?5023868&101" alt="hit counter" border="0">
        </a>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        /* Ganti keterangan otomatis Streamlit (mis. "1GB per file • MP4...")
           dengan teks batas upload kita sendiri. Tombol Upload tetap tampil. */
        [data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"],
        [data-testid="stFileUploaderDropzone"] small {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"]::after {
            content: "Max 600 MB per file agar live lancar & lama";
            margin-left: 14px;
            font-size: 0.82rem;
            color: #9ca3af;
            white-space: nowrap;
            align-self: center;
        }
        .upload-limit-note {
            display: none !important;
        }

        /* Mode streaming memakai checkbox native seperti menu "📢 Tampilkan Iklan". */
        div[data-testid="stCheckbox"] label {
            font-size: 1.75rem !important;
            font-weight: 600 !important;
        }
        .streaming-mode-title {
            font-size: 1.75rem;
            font-weight: 700;
            margin: 0.5rem 0 0.25rem 0;
        }
                </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<h1><a href="https://www.youtube.com/@thexextsolutionid?sub_confirmation=1" target="_blank" style="text-decoration:none;">STREMQU by TNS</a></h1>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<h4>Tools live streaming YouTube pribadi tanpa habiskan kuota, sewa RDP, VPS dll.</h4>',
        unsafe_allow_html=True
    )

    with st.expander("⚠️ DISCLAIMER", expanded=True):
        st.markdown("""
        - Layanan gratis mengikuti kebijakan dan batasan penyedia hosting.
        - Durasi streaming tergantung resource yang tersedia pada Streamlit.
        - Tidak menjamin jumlah view, penonton, subscriber, atau hasil tertentu.
        """)

    show_ads = st.checkbox("📢 Tampilkan Iklan", value=False)
    if show_ads:
        components.html(
            """
            <div style="background:#f0f2f6;padding:20px;border-radius:10px;text-align:center">
                <script type='text/javascript'
                        src='//pl26562103.profitableratecpm.com/28/f9/95/28f9954a1d5bbf4924abe123c76a68d2.js'>
                </script>
                <p style="color:#888">Iklan akan muncul di sini</p>
            </div>
            """,
            height=300
        )

    st.markdown("### 1. PILIH MODE STREAMING")

    # Mode streaming dibuat seperti menu checkbox, sama seperti "📢 Tampilkan Iklan".
    # Default: 🎬 5 Video Playlist. Menu ditampilkan satu kali di atas.
    if "streaming_mode" not in st.session_state:
        st.session_state.streaming_mode = "5 Video Playlist"

    def sync_mode(source):
        if source == "top_video":
            st.session_state.streaming_mode = "5 Video Playlist"
        elif source == "top_mp3":
            st.session_state.streaming_mode = "Video + MP3"
        active = st.session_state.streaming_mode
        for key in ("top_video",):
            st.session_state[key] = active == "5 Video Playlist"
        for key in ("top_mp3",):
            st.session_state[key] = active == "Video + MP3"

    # Nilai awal checkbox.
    st.session_state.setdefault("top_video", st.session_state.streaming_mode == "5 Video Playlist")
    st.session_state.setdefault("top_mp3", st.session_state.streaming_mode == "Video + MP3")
    st.checkbox("🎬 5 Video Playlist", key="top_video", on_change=sync_mode, args=("top_video",))
    st.checkbox("🎵 Video + MP3", key="top_mp3", on_change=sync_mode, args=("top_mp3",))

    mode = st.session_state.streaming_mode

    selected_paths = []
    audio_paths = []

    if mode == "5 Video Playlist":
        st.subheader("2. UPLOAD VIDEO / PLAYLIST (MIN. 1 VIDEO)")
        st.caption("Video akan dimainkan sesuai urutan: Video 1 → Video 2 → Video 3 → Video 4 → Video 5.")
        st.info("Setiap slot bisa menggunakan Upload, Link langsung, atau Google Drive. Video dari Link/Drive diunduh langsung ke server sehingga tidak perlu upload melalui browser.")

        for slot in range(1, 6):
            st.markdown(f"### Video {slot}")
            source = st.radio(
                f"Sumber Video {slot}",
                ["Upload dari perangkat", "Link langsung", "Google Drive"],
                horizontal=True,
                key=f"playlist_video_source_{slot}",
                label_visibility="collapsed",
            )

            if source == "Upload dari perangkat":
                uploaded_file = st.file_uploader(
                    f"Upload Video {slot}",
                    type=["mp4", "flv", "mov", "mkv", "webm"],
                    label_visibility="collapsed",
                    key=f"video_uploader_{slot}",
                    help=f"Video ke-{slot} dalam urutan playlist."
                )
                st.markdown(
                    '<div class="upload-limit-note">Max 600 MB per file agar live lancar &amp; lama</div>',
                    unsafe_allow_html=True,
                )
                if uploaded_file is not None:
                    saved = save_uploaded_file(uploaded_file, slot)
                    st.session_state[f"playlist_video_path_{slot}"] = saved
                    st.success(f"Video {slot} siap: {uploaded_file.name}")

            elif source == "Link langsung":
                video_url = st.text_input(
                    f"URL Video {slot}",
                    placeholder="https://contoh.com/video.mp4",
                    key=f"playlist_video_url_{slot}",
                    help="Gunakan direct link yang bisa diakses tanpa login dan mengarah ke file video."
                )
                link_name = st.text_input(
                    "Nama file (opsional)",
                    placeholder=f"video_{slot}.mp4",
                    key=f"playlist_video_name_{slot}",
                )
                if st.button(f"⬇️ Ambil Video {slot} dari Link", key=f"playlist_download_link_{slot}", use_container_width=True):
                    if not video_url.strip():
                        st.error(f"Masukkan URL Video {slot} terlebih dahulu.")
                    else:
                        try:
                            with st.spinner(f"Mengunduh Video {slot} ke server..."):
                                saved = download_video_from_url(video_url, slot, link_name)
                            st.session_state[f"playlist_video_path_{slot}"] = saved
                            st.success(f"Video {slot} siap: {Path(saved).name}")
                        except Exception as e:
                            st.error(f"Gagal mengambil Video {slot}: {e}")

            else:
                drive_url = st.text_input(
                    f"Link Google Drive Video {slot}",
                    placeholder="https://drive.google.com/file/d/.../view?usp=sharing",
                    key=f"playlist_video_drive_url_{slot}",
                    help="Fil
