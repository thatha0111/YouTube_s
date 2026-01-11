import sys
import subprocess
import threading
import os
import time
import uuid
import requests
import re
import json
import streamlit as st
from datetime import datetime
import pandas as pd
from urllib.parse import urlparse
import html

# Warna tema professional
THEME_COLORS = {
    "primary": "#1877F2",  # Facebook blue
    "secondary": "#242526",
    "accent": "#00BFFF",
    "success": "#31A24C",
    "danger": "#F02849",
    "warning": "#F7B928",
    "dark": "#18191A",
    "light": "#F0F2F5"
}

def validate_url_manual(url):
    """Validasi URL secara manual tanpa library external"""
    try:
        # Cek format URL dasar
        if not url or not isinstance(url, str):
            return False, "URL tidak valid"
        
        # Cek jika mengandung protokol
        if not url.startswith(('http://', 'https://')):
            return False, "URL harus diawali dengan http:// atau https://"
        
        # Cek format dengan regex sederhana
        url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        if not re.match(url_pattern, url):
            return False, "Format URL tidak valid"
        
        return True, "URL valid"
    except:
        return False, "URL tidak valid"

def check_video_url(url):
    """Cek apakah URL mengarah ke video"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Coba HEAD request dulu
        try:
            response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
            content_type = response.headers.get('content-type', '').lower()
            
            # Cek tipe konten video
            if 'video' in content_type:
                return True, "URL video valid"
            elif 'application' in content_type or 'octet-stream' in content_type:
                return True, "URL file valid"
            
            # Jika HEAD tidak memberikan info, coba GET sebagian kecil
            response = requests.get(url, headers=headers, timeout=5, stream=True)
            content_type = response.headers.get('content-type', '').lower()
            
            if 'video' in content_type or 'application' in content_type:
                return True, "URL video valid"
            
            # Cek ekstensi file dari URL
            parsed = urlparse(url)
            path = parsed.path.lower()
            video_extensions = ['.mp4', '.flv', '.mkv', '.avi', '.mov', '.webm', '.m3u8', '.m3u']
            
            for ext in video_extensions:
                if path.endswith(ext):
                    return True, f"URL video valid ({ext})"
                    
            return False, "URL tidak dikenali sebagai video"
            
        except requests.exceptions.Timeout:
            return False, "Timeout saat mengakses URL"
        except requests.exceptions.RequestException as e:
            return False, f"Tidak dapat mengakses URL: {str(e)}"
            
    except Exception as e:
        return False, f"Error: {str(e)}"

def validate_video_url(url):
    """Validasi URL video dengan kombinasi metode"""
    # Validasi format URL
    is_valid_format, format_msg = validate_url_manual(url)
    if not is_valid_format:
        return False, format_msg
    
    # Cek jika URL video
    return check_video_url(url)

def get_hls_stream_info(url):
    """Mendapatkan informasi HLS stream tanpa library m3u8"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            content = response.text
            
            # Analisis sederhana playlist HLS
            lines = content.split('\n')
            info = {
                'segment_count': 0,
                'is_variant': '#EXT-X-STREAM-INF' in content,
                'has_endlist': '#EXT-X-ENDLIST' in content
            }
            
            # Hitung segmen
            for line in lines:
                if line and not line.startswith('#'):
                    info['segment_count'] += 1
            
            return info
    except Exception as e:
        return {'error': str(e)}
    return None

def run_ffmpeg_stream(video_source, stream_key, is_vertical, live_id, input_type, log_callback):
    """Menjalankan streaming FFmpeg dengan berbagai tipe input"""
    output_url = f"rtmps://live-api-s.facebook.com:443/rtmp/{stream_key}"
    
    scale = "-vf scale=720:1280" if is_vertical else ""
    
    # Base command
    cmd = [
        "ffmpeg",
        "-re",  # Read input at native frame rate
    ]
    
    # Tambahkan parameter berdasarkan tipe input
    if input_type == "hls":
        # Untuk HLS stream
        cmd.extend([
            "-i", video_source,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-g", "60",
            "-keyint_min", "60",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "flv"
        ])
        log_callback(live_id, f"📡 Menggunakan HLS stream: {video_source}")
        
    elif input_type == "url":
        # Untuk URL video langsung
        cmd.extend([
            "-i", video_source,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-g", "60",
            "-keyint_min", "60",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "flv"
        ])
        log_callback(live_id, f"🌐 Menggunakan URL video: {video_source}")
        
    else:  # file
        # Untuk file lokal dengan loop
        cmd.extend([
            "-stream_loop", "-1",
            "-i", video_source,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-g", "60",
            "-keyint_min", "60",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "flv"
        ])
        log_callback(live_id, f"📁 Menggunakan file lokal: {os.path.basename(video_source)}")
    
    # Tambahkan scale jika mode vertikal
    if scale:
        cmd += scale.split()
    
    cmd.append(output_url)
    
    log_callback(live_id, f"🚀 Memulai streaming untuk Live ID: {live_id}")
    log_callback(live_id, f"🔧 Mode: {'Vertikal' if is_vertical else 'Horizontal'}")
    log_callback(live_id, f"📡 Menghubungkan ke Facebook Live...")
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Simpan process ke session state
        if 'processes' not in st.session_state:
            st.session_state.processes = {}
        st.session_state.processes[live_id] = process
        
        # Baca output secara real-time
        for line in iter(process.stdout.readline, ''):
            if line:
                # Filter dan format output
                if "frame=" in line.lower():
                    match = re.search(r'frame=\s*(\d+)', line)
                    if match:
                        log_callback(live_id, f"📊 Frame: {match.group(1)}")
                elif "bitrate=" in line.lower():
                    match = re.search(r'bitrate=\s*([\d\.]+\s*\w+/s)', line)
                    if match:
                        log_callback(live_id, f"📈 Bitrate: {match.group(1)}")
                elif "error" in line.lower() or "failed" in line.lower():
                    log_callback(live_id, f"❌ {line.strip()[:100]}")
        
        process.wait()
        
    except Exception as e:
        log_callback(live_id, f"❌ Runtime Error: {str(e)}")
    finally:
        log_callback(live_id, "🔴 Streaming dihentikan")
        # Hapus process dari session state
        if 'processes' in st.session_state and live_id in st.session_state.processes:
            del st.session_state.processes[live_id]

def stop_live_stream(live_id):
    """Menghentikan streaming untuk live tertentu"""
    if 'processes' in st.session_state and live_id in st.session_state.processes:
        try:
            process = st.session_state.processes[live_id]
            process.terminate()
            time.sleep(1)
            if process.poll() is None:
                process.kill()
            
            # Update status di session state
            if 'active_lives' in st.session_state and live_id in st.session_state.active_lives:
                st.session_state.active_lives[live_id]['status'] = 'stopped'
                st.session_state.active_lives[live_id]['stopped_at'] = datetime.now().strftime("%H:%M:%S")
            
            return True
        except Exception as e:
            st.error(f"❌ Gagal menghentikan live: {str(e)}")
            return False
    return False

def create_live_card(live_id, live_info):
    """Membuat kartu untuk live yang sedang berjalan"""
    status_color = {
        'running': THEME_COLORS['success'],
        'stopped': THEME_COLORS['danger'],
        'error': THEME_COLORS['warning']
    }
    
    input_type_icon = {
        'file': '📁',
        'url': '🌐',
        'hls': '📡'
    }
    
    with st.container():
        st.markdown(f"""
        <div style="background: white; padding: 1.5rem; border-radius: 10px; 
                    border-left: 5px solid {THEME_COLORS['primary']}; 
                    margin-bottom: 1rem; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([3, 2, 1])
        
        with col1:
            st.markdown(f"### {input_type_icon.get(live_info.get('input_type', 'file'))} Live: {live_info['title']}")
            st.caption(f"🎬 Sumber: {live_info['source_display']}")
            st.caption(f"⏰ Dimulai: {live_info['started_at']}")
            if 'stopped_at' in live_info:
                st.caption(f"🛑 Dihentikan: {live_info['stopped_at']}")
            
            # Tampilkan log terakhir
            if 'logs' in live_info and live_info['logs']:
                with st.expander("📝 Log Terakhir", expanded=False):
                    for log in live_info['logs'][-3:]:
                        st.code(log, language=None)
        
        with col2:
            status = live_info.get('status', 'stopped')
            st.markdown(f"""
            <div style="background-color: {status_color[status]}; 
                        color: white; 
                        padding: 8px; 
                        border-radius: 5px;
                        text-align: center;
                        margin: 5px 0;">
                <strong>{status.upper()}</strong>
            </div>
            """, unsafe_allow_html=True)
            
            st.caption(f"🔧 Tipe: {live_info.get('input_type', 'file').upper()}")
            st.caption(f"📐 Mode: {'Vertikal' if live_info.get('is_vertical', False) else 'Horizontal'}")
            if live_info.get('quality'):
                st.caption(f"🎚️ Kualitas: {live_info.get('quality')}")
        
        with col3:
            if status == 'running':
                if st.button("⏹️ Stop", key=f"stop_{live_id}"):
                    if stop_live_stream(live_id):
                        st.rerun()
            else:
                if st.button("🗑️ Hapus", key=f"delete_{live_id}"):
                    if 'active_lives' in st.session_state and live_id in st.session_state.active_lives:
                        del st.session_state.active_lives[live_id]
                        st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)

def main():
    # Konfigurasi halaman
    st.set_page_config(
        page_title="Facebook Live Manager Pro",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # CSS Custom untuk tampilan profesional
    st.markdown(f"""
    <style>
    .stApp {{
        background-color: {THEME_COLORS['light']};
    }}
    
    .main-header {{
        background: linear-gradient(135deg, {THEME_COLORS['primary']}, {THEME_COLORS['accent']});
        color: white;
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }}
    
    .input-method-card {{
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border: 2px solid #e0e0e0;
        cursor: pointer;
        transition: all 0.3s;
    }}
    
    .input-method-card:hover {{
        border-color: {THEME_COLORS['primary']};
        transform: translateY(-2px);
    }}
    
    .input-method-card.active {{
        border-color: {THEME_COLORS['primary']};
        background-color: rgba(24, 119, 242, 0.1);
    }}
    
    .method-icon {{
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }}
    
    .live-card {{
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid {THEME_COLORS['primary']};
        margin-bottom: 1rem;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }}
    
    .stat-card {{
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }}
    
    .streaming-active {{
        animation: pulse 2s infinite;
    }}
    
    @keyframes pulse {{
        0% {{ opacity: 1; }}
        50% {{ opacity: 0.7; }}
        100% {{ opacity: 1; }}
    }}
    
    /* Style untuk tabs */
    .stTabs [data-baseweb="tab-list"] {{
        background-color: transparent;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        background-color: transparent;
        border-radius: 5px 5px 0 0;
        padding: 10px 16px;
        font-weight: 600;
    }}
    
    .stTabs [aria-selected="true"] {{
        background-color: {THEME_COLORS['primary']} !important;
        color: white !important;
    }}
    
    /* Style untuk button */
    .stButton > button {{
        border-radius: 5px;
        font-weight: 500;
    }}
    </style>
    """, unsafe_allow_html=True)
    
    # Header utama
    st.markdown("""
    <div class="main-header">
        <h1 style="margin: 0; color: white;">📡 Facebook Live Manager Pro</h1>
        <p style="margin: 0; opacity: 0.9;">Unlimited Live Streaming dengan 3 Metode Input Video</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Inisialisasi session state
    if 'active_lives' not in st.session_state:
        st.session_state.active_lives = {}
    if 'selected_input_method' not in st.session_state:
        st.session_state.selected_input_method = "file"
    if 'processes' not in st.session_state:
        st.session_state.processes = {}
    
    # Sidebar untuk statistik dan kontrol
    with st.sidebar:
        st.markdown(f"""
        <div style="background-color: {THEME_COLORS['dark']}; 
                    color: white; 
                    padding: 1rem; 
                    border-radius: 10px;
                    margin-bottom: 1rem;">
            <h3 style="margin: 0; color: white;">📊 Dashboard</h3>
        </div>
        """, unsafe_allow_html=True)
        
        # Statistik
        col1, col2 = st.columns(2)
        with col1:
            active_count = sum(1 for live in st.session_state.active_lives.values() 
                             if live.get('status') == 'running')
            st.markdown(f"""
            <div class="stat-card">
                <h3 style="color: {THEME_COLORS['success']}; margin: 0;">{active_count}</h3>
                <p style="margin: 0; font-size: 12px;">Live Aktif</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            total_count = len(st.session_state.active_lives)
            st.markdown(f"""
            <div class="stat-card">
                <h3 style="color: {THEME_COLORS['primary']}; margin: 0;">{total_count}</h3>
                <p style="margin: 0; font-size: 12px;">Total Live</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Statistik berdasarkan metode input
        st.markdown("### 📊 Metode Input")
        input_stats = {}
        for live in st.session_state.active_lives.values():
            method = live.get('input_type', 'file')
            input_stats[method] = input_stats.get(method, 0) + 1
        
        for method, count in input_stats.items():
            icon = {'file': '📁', 'url': '🌐', 'hls': '📡'}.get(method, '📁')
            st.caption(f"{icon} {method.upper()}: {count} live")
        
        st.divider()
        
        # Kontrol global
        st.markdown("### 🎛️ Kontrol Global")
        if st.button("🛑 Hentikan Semua Live", use_container_width=True, type="secondary"):
            if 'processes' in st.session_state:
                for live_id, process in list(st.session_state.processes.items()):
                    try:
                        process.terminate()
                        time.sleep(0.5)
                        if process.poll() is None:
                            process.kill()
                        if live_id in st.session_state.active_lives:
                            st.session_state.active_lives[live_id]['status'] = 'stopped'
                    except:
                        pass
                st.session_state.processes = {}
                st.success("✅ Semua live dihentikan")
                st.rerun()
        
        st.divider()
        
        # Informasi sistem
        st.markdown("### ℹ️ Informasi Sistem")
        st.caption(f"Python: {sys.version.split()[0]}")
        
        # Video yang tersedia
        video_files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.flv', '.mkv', '.avi', '.mov'))]
        if video_files:
            with st.expander("📁 Video Tersedia"):
                for video in video_files[:5]:
                    st.code(video)
                if len(video_files) > 5:
                    st.caption(f"... dan {len(video_files)-5} lainnya")
    
    # Main content area
    tab1, tab2, tab3 = st.tabs(["🎬 Live Aktif", "➕ Tambah Live Baru", "📊 Analytics"])
    
    with tab1:
        st.markdown("### 📡 Live Streaming Aktif")
        
        if not st.session_state.active_lives:
            st.info("🎯 Belum ada live yang aktif. Mulai live baru di tab 'Tambah Live Baru'")
        else:
            # Tampilkan semua live aktif
            for live_id, live_info in st.session_state.active_lives.items():
                create_live_card(live_id, live_info)
    
    with tab2:
        st.markdown("### 🚀 Buat Live Streaming Baru")
        
        # Pilihan metode input
        st.markdown("#### 📥 Pilih Metode Input Video")
        
        col_file, col_url, col_hls = st.columns(3)
        
        with col_file:
            method_active = "active" if st.session_state.selected_input_method == "file" else ""
            st.markdown(f"""
            <div class="input-method-card {method_active}" onclick="document.getElementById('method_file').click()">
                <div class="method-icon">📁</div>
                <h4>File Lokal</h4>
                <p style="font-size: 12px;">Upload video dari komputer</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Pilih", key="method_file", type="primary" if st.session_state.selected_input_method == "file" else "secondary"):
                st.session_state.selected_input_method = "file"
                st.rerun()
        
        with col_url:
            method_active = "active" if st.session_state.selected_input_method == "url" else ""
            st.markdown(f"""
            <div class="input-method-card {method_active}" onclick="document.getElementById('method_url').click()">
                <div class="method-icon">🌐</div>
                <h4>URL Video</h4>
                <p style="font-size: 12px;">Link video mentah dari internet</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Pilih", key="method_url", type="primary" if st.session_state.selected_input_method == "url" else "secondary"):
                st.session_state.selected_input_method = "url"
                st.rerun()
        
        with col_hls:
            method_active = "active" if st.session_state.selected_input_method == "hls" else ""
            st.markdown(f"""
            <div class="input-method-card {method_active}" onclick="document.getElementById('method_hls').click()">
                <div class="method-icon">📡</div>
                <h4>HLS Stream</h4>
                <p style="font-size: 12px;">HLS/M3U8 streaming link</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Pilih", key="method_hls", type="primary" if st.session_state.selected_input_method == "hls" else "secondary"):
                st.session_state.selected_input_method = "hls"
                st.rerun()
        
        st.divider()
        
        # Form berdasarkan metode input
        input_method = st.session_state.selected_input_method
        
        # Tampilkan indikator metode
        method_info = {
            "file": {"icon": "📁", "desc": "Upload file video lokal"},
            "url": {"icon": "🌐", "desc": "Link video mentah dari internet"},
            "hls": {"icon": "📡", "desc": "HLS/M3U8 streaming link"}
        }
        
        st.markdown(f"### {method_info[input_method]['icon']} {method_info[input_method]['desc']}")
        
        video_source = None
        source_display = ""
        
        if input_method == "file":
            col1, col2 = st.columns(2)
            
            with col1:
                # Upload video baru
                uploaded_file = st.file_uploader(
                    "📤 Upload Video Baru",
                    type=['mp4', 'flv', 'mkv', 'avi', 'mov', 'webm'],
                    help="Format: MP4/FLV dengan codec H264/AAC",
                    key="file_upload"
                )
            
            with col2:
                # Atau pilih video yang ada
                video_files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.flv', '.mkv', '.avi', '.mov', '.webm'))]
                selected_video = None
                if video_files:
                    selected_video = st.selectbox(
                        "🎬 Atau pilih video yang tersedia",
                        video_files,
                        key="file_select"
                    )
            
            # Tentukan video source
            if uploaded_file:
                video_source = uploaded_file.name
                with open(video_source, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                source_display = f"📁 {uploaded_file.name}"
                st.success(f"✅ Video '{uploaded_file.name}' berhasil diupload")
            elif selected_video:
                video_source = selected_video
                source_display = f"📁 {selected_video}"
            else:
                video_source = None
        
        elif input_method == "url":
            url_input = st.text_input(
                "🔗 Masukkan URL Video",
                placeholder="https://example.com/video.mp4",
                help="Masukkan URL langsung ke file video (mp4, flv, etc.)",
                key="url_input"
            )
            
            if url_input:
                with st.spinner("🔍 Memvalidasi URL..."):
                    is_valid, message = validate_video_url(url_input)
                    if is_valid:
                        st.success(f"✅ {message}")
                        video_source = url_input
                        # Potong URL jika terlalu panjang
                        if len(url_input) > 50:
                            source_display = f"🌐 {url_input[:50]}..."
                        else:
                            source_display = f"🌐 {url_input}"
                    else:
                        st.error(f"❌ {message}")
        
        elif input_method == "hls":
            hls_url = st.text_input(
                "📡 Masukkan HLS/M3U8 URL",
                placeholder="https://example.com/stream.m3u8",
                help="Masukkan URL playlist HLS (.m3u8)",
                key="hls_input"
            )
            
            if hls_url:
                with st.spinner("🔍 Memeriksa HLS stream..."):
                    is_valid, message = validate_video_url(hls_url)
                    if is_valid:
                        st.success(f"✅ {message}")
                        video_source = hls_url
                        # Potong URL jika terlalu panjang
                        if len(hls_url) > 50:
                            source_display = f"📡 {hls_url[:50]}..."
                        else:
                            source_display = f"📡 {hls_url}"
                        
                        # Tampilkan info HLS jika tersedia
                        info = get_hls_stream_info(hls_url)
                        if info and 'error' not in info:
                            with st.expander("📊 Info HLS Stream"):
                                if 'segment_count' in info:
                                    st.caption(f"📦 Segmen: {info['segment_count']}")
                                if 'is_variant' in info:
                                    st.caption(f"🔀 Variant: {'Ya' if info['is_variant'] else 'Tidak'}")
                                if 'has_endlist' in info:
                                    st.caption(f"🔚 Endlist: {'Ya' if info['has_endlist'] else 'Live Stream'}")
                    else:
                        st.error(f"❌ {message}")
        
        st.divider()
        st.markdown("### ⚙️ Konfigurasi Streaming")
        
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            live_title = st.text_input(
                "📝 Judul Live Streaming",
                value=f"Live Streaming {datetime.now().strftime('%H:%M')}",
                help="Judul untuk identifikasi live"
            )
            
            stream_key = st.text_input(
                "🔑 Facebook Stream Key",
                type="password",
                help="Dapatkan dari Facebook Creator Studio"
            )
            
            quality = st.select_slider(
                "🎚️ Kualitas Streaming",
                options=['Low', 'Medium', 'High', 'Ultra'],
                value='Medium'
            )
        
        with col_config2:
            is_vertical = st.checkbox(
                "📱 Mode Vertikal (720x1280)",
                help="Aktifkan untuk format Reels/Stories"
            )
            
            # Advanced options - DIPERBAIKI: gunakan slider untuk buffer size
            with st.expander("⚙️ Advanced Options"):
                buffer_size = st.slider(
                    "Buffer Size (KB)", 
                    min_value=1000, 
                    max_value=20000, 
                    value=5000,
                    step=1000
                )
                bitrate = st.selectbox(
                    "Bitrate Video", 
                    ['1500k', '2000k', '2500k', '3000k', '4000k'], 
                    index=2
                )
                audio_bitrate = st.selectbox(
                    "Bitrate Audio", 
                    ['64k', '96k', '128k', '192k', '256k'], 
                    index=2
                )
        
        # Tombol submit
        col_submit1, col_submit2, col_submit3 = st.columns([1, 2, 1])
        with col_submit2:
            if st.button(f"🚀 Mulai Live Streaming", use_container_width=True, type="primary"):
                if not video_source or not stream_key:
                    st.error("❌ Harap lengkapi sumber video dan Stream Key!")
                else:
                    # Generate unique live ID
                    live_id = str(uuid.uuid4())[:8]
                    
                    # Buat log callback function
                    def log_callback(live_id, message):
                        if live_id in st.session_state.active_lives:
                            if 'logs' not in st.session_state.active_lives[live_id]:
                                st.session_state.active_lives[live_id]['logs'] = []
                            st.session_state.active_lives[live_id]['logs'].append(
                                f"{datetime.now().strftime('%H:%M:%S')} - {message}"
                            )
                    
                    # Simpan info live ke session state
                    st.session_state.active_lives[live_id] = {
                        'title': live_title,
                        'video_source': video_source,
                        'source_display': source_display,
                        'input_type': input_method,
                        'stream_key': stream_key,
                        'is_vertical': is_vertical,
                        'quality': quality,
                        'bitrate': bitrate,
                        'audio_bitrate': audio_bitrate,
                        'buffer_size': buffer_size,
                        'status': 'running',
                        'started_at': datetime.now().strftime("%H:%M:%S"),
                        'logs': []
                    }
                    
                    # Jalankan streaming di thread terpisah
                    thread = threading.Thread(
                        target=run_ffmpeg_stream,
                        args=(video_source, stream_key, is_vertical, live_id, input_method, log_callback),
                        daemon=True
                    )
                    thread.start()
                    
                    st.success(f"✅ Live '{live_title}' berhasil dimulai!")
                    st.balloons()
                    time.sleep(1)
                    st.rerun()
    
    with tab3:
        st.markdown("### 📊 Analytics & Log")
        
        if not st.session_state.active_lives:
            st.info("📈 Tidak ada data analytics. Mulai live streaming terlebih dahulu.")
        else:
            # Ringkasan performa
            st.markdown("#### 📈 Ringkasan Performa")
            
            # Buat dataframe untuk analytics
            analytics_data = []
            for live_id, live_info in st.session_state.active_lives.items():
                analytics_data.append({
                    'Live ID': live_id,
                    'Judul': live_info['title'],
                    'Metode': live_info.get('input_type', 'file').upper(),
                    'Status': live_info.get('status', 'unknown'),
                    'Sumber': live_info['source_display'][:30] + '...' if len(live_info['source_display']) > 30 else live_info['source_display'],
                    'Dimulai': live_info['started_at'],
                    'Durasi': 'Aktif' if live_info.get('status') == 'running' else 'Selesai'
                })
            
            df = pd.DataFrame(analytics_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Log detail
            st.markdown("#### 📋 Log Detail")
            selected_live = st.selectbox(
                "Pilih Live untuk melihat log",
                list(st.session_state.active_lives.keys()),
                format_func=lambda x: f"{st.session_state.active_lives[x]['title']} ({x})",
                key="log_select"
            )
            
            if selected_live and 'logs' in st.session_state.active_lives[selected_live]:
                with st.expander("📜 Tampilkan Log Lengkap", expanded=True):
                    log_container = st.container()
                    with log_container:
                        for log in st.session_state.active_lives[selected_live]['logs']:
                            st.code(log, language=None)
                
                # Download log
                log_text = "\n".join(st.session_state.active_lives[selected_live]['logs'])
                st.download_button(
                    label="💾 Download Log",
                    data=log_text,
                    file_name=f"live_log_{selected_live}.txt",
                    mime="text/plain",
                    key="log_download"
                )

if __name__ == '__main__':
    main()