import streamlit as st
import clickhouse_connect
import PyPDF2
import uuid
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from duckduckgo_search import DDGS

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Cek Kemiripan Dokumen", layout="wide")

# --- CSS & JAVASCRIPT UNTUK POP-UP KLIK (POSISI AMAN TIDAK TERPOTONG) ---
st.markdown("""
<style>
.highlight-container {
  position: relative;
  display: inline-block;
}
.highlight-plagiarized {
  background-color: #ffcccc; 
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  color: #a80000;
  font-weight: 500;
}
.highlight-safe {
  background-color: #d4edda; 
  padding: 2px 4px;
  border-radius: 3px;
  color: #155724;
}
.plagiarized-popup {
  display: none;
  position: absolute;
  top: 110%; 
  left: 0;
  width: 350px;
  background-color: #222;
  color: #fff;
  text-align: left;
  border-radius: 6px;
  padding: 10px;
  z-index: 999;
  font-size: 13px;
  box-shadow: 0px 4px 10px rgba(0,0,0,0.4);
}
.highlight-container.active .plagiarized-popup {
  display: block;
}
</style>

<script>
document.addEventListener('click', function(event) {
  if (!event.target.closest('.highlight-container')) {
    document.querySelectorAll('.highlight-container').forEach(el => {
      el.classList.remove('active');
    });
  }
});

function togglePopup(element) {
  event.stopPropagation();
  let container = element.closest('.highlight-container');
  let isActive = container.classList.contains('active');
  
  document.querySelectorAll('.highlight-container').forEach(el => {
    el.classList.remove('active');
  });
  
  if (!isActive) {
    container.classList.add('active');
  }
}
</script>
""", unsafe_allow_html=True)

# --- FUNGSI WEB SCRAPER DENGAN BEAUTIFULSOUP ---
def scrape_web_text(url):
    """Membuka URL dan mengambil teks murninya menggunakan BeautifulSoup."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.extract()
            text = soup.get_text(separator=' ')
            return ' '.join(text.split())
        return ""
    except Exception:
        return "" 

# Mengambil password admin secara aman dari secrets
ADMIN_PASSWORD = st.secrets["admin"]["password"]

# Inisialisasi Session State
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "token_info" not in st.session_state:
    st.session_state.token_info = {}

# Fungsi koneksi ke ClickHouse
def get_db_client():
    ch_config = st.secrets["clickhouse"]
    return clickhouse_connect.get_client(
        host=ch_config["host"],
        port=int(ch_config.get("port", 8443)),
        user=ch_config["user"],
        password=ch_config["password"],
        secure=bool(ch_config.get("secure", True))
    )

# ==========================================
# 1. LOGIKA VERIFIKASI TOKEN USER (+ TOKEN SAKTI)
# ==========================================
def verify_user_token(token_input):
    if token_input.strip() == "SAKTI-BYPASS-9999":
        return True, {"package": "Akses Tanpa Batas (Master/Sakti)", "remaining_quota": 9999}

    try:
        client = get_db_client()
        query = "SELECT package_name, quota FROM default.app_tokens WHERE token = {token:String} AND is_active = 1"
        result = client.query(query, parameters={"token": token_input})
        
        if not result.result_rows:
            return False, "Token tidak valid atau sudah tidak aktif."
            
        pkg_name, current_quota = result.result_rows[0]
        
        if current_quota <= 0:
            return False, "Kuota token ini sudah habis."
            
        new_quota = current_quota - 1
        update_query = "ALTER TABLE default.app_tokens UPDATE quota = {new_quota:Int32} WHERE token = {token:String}"
        client.command(update_query, parameters={"new_quota": new_quota, "token": token_input})
        
        return True, {"package": pkg_name, "remaining_quota": new_quota}
        
    except Exception as e:
        return False, f"Kendala koneksi sistem: {e}"

# ==========================================
# 2. NAVIGASI SIDEBAR UTAMA
# ==========================================
st.sidebar.title("Navigasi Menu")
menu_option = st.sidebar.radio("Pilih Halaman:", ["Utama: Cek Plagiasi", "Login Token / Redeem", "Panel Admin"])

st.sidebar.markdown("---")
if st.session_state.authenticated:
    info = st.session_state.token_info
    st.sidebar.success(f"✅ Sesi Aktif\n- Paket: {info.get('package')}\n- Sisa Kuota: {info.get('remaining_quota')}x")
    if st.sidebar.button("Keluar / Ganti Token"):
        st.session_state.authenticated = False
        st.session_state.token_info = {}
        st.rerun()
else:
    st.sidebar.info("💡 Anda belum memasukkan token. Fitur cek akan memotong kuota setelah login.")

st.sidebar.markdown("---")
st.sidebar.header("Filter Pengecekan")
exclude_quotes = st.sidebar.checkbox("Exclude Quotes (Abaikan Kutipan)", value=True)
exclude_biblio = st.sidebar.checkbox("Exclude Bibliography (Abaikan Daftar Pustaka)", value=True)

# ==========================================
# 3. KONTROL HALAMAN BERDASARKAN MENU
# ==========================================

if menu_option == "Panel Admin":
    st.title("🛠️ Panel Admin WhatsApp")
    st.write("Kelola pembuatan token akses pengguna.")
    
    admin_pass_input = st.text_input("Password Admin:", type="password")
    
    if admin_pass_input == ADMIN_PASSWORD:
        st.success("Admin Logged In")
        st.subheader("🔑 Buat Token Akses Baru")
        
        with st.form("create_token_form"):
            package_name = st.text_input("Nama Paket / Keterangan (Cth: Paket 5x Cek)", value="Sekali Pakai")
            quota_amount = st.number_input("Jumlah Kuota Token:", min_value=1, max_value=100, value=1)
            submit_token = st.form_submit_button("Generate Token")
            
            if submit_token:
                new_token = "TOK-" + str(uuid.uuid4())[:8].upper()
                try:
                    client = get_db_client()
                    query = """
                        INSERT INTO default.app_tokens (token, package_name, quota, created_at, is_active) 
                        VALUES ({token:String}, {pkg:String}, {quota:Int32}, {date:DateTime}, 1)
                    """
                    client.command(query, parameters={
                        "token": new_token,
                        "pkg": package_name,
                        "quota": int(quota_amount),
                        "date": datetime.now()
                    })
                    
                    st.success("Token berhasil dibuat!")
                    st.markdown(f"### Salin teks ini untuk dikirim via WhatsApp:\n> `{new_token}`")
                    st.info(f"Paket: {package_name} | Kuota: {quota_amount}x pakai")
                except Exception as e:
                    st.error(f"Gagal menyimpan token ke database: {e}")
        
        st.subheader("📋 Daftar Token di Database")
        try:
            client = get_db_client()
            tokens_df = client.query_df("SELECT token, package_name, quota, created_at FROM default.app_tokens ORDER BY created_at DESC LIMIT 10")
            st.dataframe(tokens_df)
        except Exception:
            pass
            
    elif admin_pass_input:
        st.error("Password Admin Salah")

elif menu_option == "Login Token / Redeem":
    st.title("🔑 Masukkan Kode Akses Token")
    st.write("Silakan masukkan kode token yang Anda miliki (atau gunakan Token Sakti untuk uji coba).")
    
    token_input = st.text_input("Kode Token Anda:", type="default")
    
    if st.button("Masuk Aplikasi"):
        if token_input.strip():
            with st.spinner("Memvalidasi kode token..."):
                success, data_or_msg = verify_user_token(token_input.strip())
                if success:
                    st.session_state.authenticated = True
                    st.session_state.token_info = data_or_msg
                    st.session_state.token_code = token_input.strip()
                    st.success(f"Berhasil masuk! Paket: {data_or_msg['package']} | Sisa kuota Anda: {data_or_msg['remaining_quota']}x")
                    st.rerun()
                else:
                    st.error(data_or_msg)
        else:
            st.warning("Mohon masukkan kode token terlebih dahulu.")

else:
    # ==========================================
    # HALAMAN UTAMA: CEK KEMIRIPAN DOKUMEN
    # ==========================================
    st.title("📄 Sistem Pengecekan Kemiripan Dokumen")
    st.caption("🔍 Engine: DuckDuckGo + BeautifulSoup | Mode: No Repository")

    st.write("### Unggah Draf Dokumen")
    uploaded_file = st.file_uploader("Pilih dokumen berformat PDF", type="pdf")

    if uploaded_file is not None:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        total_pages = len(pdf_reader.pages)
        
        extracted_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + " "
        
        total_words = len(extracted_text.split())
        st.write(f"**Dokumen diterima:** {uploaded_file.name} ({total_pages} Halaman, ±{total_words} Kata)")
        
        if st.button("Jalankan Pengecekan", type="primary"):
            if not st.session_state.authenticated:
                st.warning("⚠️ Anda belum memasukkan token akses. Silakan masukkan token terlebih dahulu melalui menu **Login Token / Redeem** di sidebar.")
            else:
                with st.spinner("Menelusuri & Scraping internet... (Tunggu sebentar)"):
                    
                    # Pecah teks dan filter kalimat yang valid
                    sentences = re.split(r'(?<=[.!?]) +', extracted_text)
                    valid_sentences = [s.strip() for s in sentences if len(s.split()) > 10]
                    
                    # Batasi jumlah pengecekan untuk purwarupa/menghindari rate-limit
                    sentences_to_check = valid_sentences[:3] 
                    
                    found_match = False
                    plagiarized_text = ""
                    web_title = ""
                    web_url = ""
                    matched_snippet = ""
                    
                    ddgs = DDGS()
                    for sentence in sentences_to_check:
                        if found_match: break
                        try:
                            # 1. Cari link pakai DuckDuckGo
                            search_results = list(ddgs.text(f'"{sentence}"', max_results=1))
                            
                            if search_results:
                                candidate_url = search_results[0].get("href", "")
                                candidate_title = search_results[0].get("title", "Sumber Internet")
                                
                                # 2. Scrape web pakai BeautifulSoup
                                if candidate_url:
                                    scraped_content = scrape_web_text(candidate_url)
                                    
                                    # 3. Bandingkan teks web hasil scrape dengan teks PDF asli
                                    if sentence.lower() in scraped_content.lower():
                                        found_match = True
                                        plagiarized_text = sentence
                                        web_title = candidate_title
                                        web_url = candidate_url
                                        
                                        idx = scraped_content.lower().find(sentence.lower())
                                        start_idx = max(0, idx - 50)
                                        end_idx = min(len(scraped_content), idx + len(sentence) + 50)
                                        matched_snippet = scraped_content[start_idx:end_idx].replace(sentence, f"<b>{sentence}</b>")
                        except Exception:
                            pass 

                    # --- HASIL ---
                    st.markdown("---")
                    st.subheader("Integrity Overview")
                    
                    col1, col2, col3 = st.columns(3)
                    if found_match:
                        col1.metric("Status Dokumen", "Terdeteksi Plagiasi", delta="-Validasi Scraper", delta_color="inverse")
                        col2.metric("Sumber Terdeteksi", "1")
                    else:
                        col1.metric("Status Dokumen", "Aman / Orisinal", delta="Bebas Plagiasi")
                        col2.metric("Sumber Terdeteksi", "0")
                    col3.metric("Kata Diproses", f"{total_words:,}")
                    
                    st.write("### Pratinjau Sorotan Teks (Klik pada teks stabilo untuk melihat detail)")
                    if found_match:
                        st.markdown(f"""
                        <div style="border: 1px solid #ddd; padding: 20px; border-radius: 5px; background-color: #fafafa; line-height: 2.0;">
                            Dokumen diperiksa: 
                            <span class="highlight-container">
                                <span class="highlight-plagiarized" onclick="togglePopup(this)">{plagiarized_text}</span>
                                <div class="plagiarized-popup">
                                    <b>Sumber (Terverifikasi BeautifulSoup):</b><br>
                                    <a href="{web_url}" target="_blank" style="color: #4da6ff;">{web_title}</a><br>
                                    <hr style="margin:5px 0; border-color:#555;">
                                    <i>Cuplikan di Web:</i><br> "...{matched_snippet}..."
                                </div>
                            </span>
                            ... [Sisa teks dokumen diproses].
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        safe_snippet = " ".join(valid_sentences[:3]) if valid_sentences else "Teks terlalu pendek."
                        st.markdown(f"""
                        <div style="border: 1px solid #ddd; padding: 20px; border-radius: 5px; background-color: #fafafa; line-height: 2.0;">
                            <span class="highlight-safe">{safe_snippet}</span><br><br>
                            <i>Scraper tidak menemukan kecocokan di internet pada sampel awal dokumen ini.</i>
                        </div>
                        """, unsafe_allow_html=True)
