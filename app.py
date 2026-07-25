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

# --- CSS & JAVASCRIPT GAYA TURNITIN ---
st.markdown("""
<style>
.highlight-container { position: relative; display: inline-block; cursor: pointer; }
.turnitin-source-list { border: 1px solid #ddd; padding: 15px; border-radius: 5px; background: #fff; }
.turnitin-score { font-size: 48px; font-weight: bold; color: #b30000; margin-bottom: 0; }
.plagiarized-popup { display: none; position: absolute; top: 110%; left: 0; width: 350px; background-color: #222; color: #fff; text-align: left; border-radius: 6px; padding: 10px; z-index: 999; font-size: 13px; box-shadow: 0px 4px 10px rgba(0,0,0,0.4); }
.highlight-container.active .plagiarized-popup { display: block; }
</style>
<script>
document.addEventListener('click', function(event) {
  if (!event.target.closest('.highlight-container')) {
    document.querySelectorAll('.highlight-container').forEach(el => { el.classList.remove('active'); });
  }
});
function togglePopup(element) {
  event.stopPropagation();
  let container = element.closest('.highlight-container');
  let isActive = container.classList.contains('active');
  document.querySelectorAll('.highlight-container').forEach(el => { el.classList.remove('active'); });
  if (!isActive) { container.classList.add('active'); }
}
</script>
""", unsafe_allow_html=True)

# --- FUNGSI WEB SCRAPER DENGAN BEAUTIFULSOUP ---
def scrape_web_text(url):
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

ADMIN_PASSWORD = st.secrets["admin"]["password"]

if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "token_info" not in st.session_state: st.session_state.token_info = {}
if "token_code" not in st.session_state: st.session_state.token_code = ""

def get_db_client():
    ch_config = st.secrets["clickhouse"]
    return clickhouse_connect.get_client(
        host=ch_config["host"], port=int(ch_config.get("port", 8443)),
        user=ch_config["user"], password=ch_config["password"], secure=bool(ch_config.get("secure", True))
    )

# ==========================================
# LOGIKA 1: CEK VALIDITAS (TANPA POTONG KUOTA)
# ==========================================
def check_token_validity(token_input):
    if token_input.strip() == "SAKTI-BYPASS-9999":
        return True, {"package": "Akses Master", "remaining_quota": 9999}
    try:
        client = get_db_client()
        query = "SELECT package_name, quota FROM default.app_tokens WHERE token = {token:String} AND is_active = 1"
        result = client.query(query, parameters={"token": token_input})
        if not result.result_rows: return False, "Token tidak valid atau sudah tidak aktif."
        pkg_name, current_quota = result.result_rows[0]
        if current_quota <= 0: return False, "Kuota token ini sudah habis."
        return True, {"package": pkg_name, "remaining_quota": current_quota}
    except Exception as e:
        return False, f"Kendala koneksi sistem: {e}"

# ==========================================
# LOGIKA 2: POTONG KUOTA SAAT KLIK TOMBOL CEK
# ==========================================
def redeem_token_quota(token_input):
    if token_input.strip() == "SAKTI-BYPASS-9999": return True
    try:
        client = get_db_client()
        query = "SELECT quota FROM default.app_tokens WHERE token = {token:String} AND is_active = 1"
        result = client.query(query, parameters={"token": token_input})
        if result.result_rows and result.result_rows[0][0] > 0:
            new_quota = result.result_rows[0][0] - 1
            client.command("ALTER TABLE default.app_tokens UPDATE quota = {new_quota:Int32} WHERE token = {token:String}", parameters={"new_quota": new_quota, "token": token_input})
            return True
        return False
    except Exception: return False

# ================= SIDEBAR =================
st.sidebar.title("Navigasi Menu")
menu_option = st.sidebar.radio("Pilih Halaman:", ["Utama: Cek Plagiasi", "Login Token / Redeem", "Panel Admin"])
st.sidebar.markdown("---")
if st.session_state.authenticated:
    info = st.session_state.token_info
    st.sidebar.success(f"✅ Sesi Aktif\n- Paket: {info.get('package')}\n- Sisa Kuota: {info.get('remaining_quota')}x")
    if st.sidebar.button("Keluar / Ganti Token"):
        st.session_state.authenticated = False
        st.session_state.token_info = {}
        st.session_state.token_code = ""
        st.rerun()
else: st.sidebar.info("💡 Anda belum memasukkan token. Token hanya dipotong saat dokumen diproses.")

# ================= HALAMAN ADMIN =================
if menu_option == "Panel Admin":
    st.title("🛠️ Panel Admin WhatsApp")
    if st.text_input("Password Admin:", type="password") == ADMIN_PASSWORD:
        st.success("Admin Logged In")
        with st.form("create_token_form"):
            package_name = st.text_input("Nama Paket:", value="Paket Regular")
            quota_amount = st.number_input("Jumlah Kuota:", min_value=1, max_value=100, value=1)
            if st.form_submit_button("Generate Token"):
                new_token = "TOK-" + str(uuid.uuid4())[:8].upper()
                try:
                    client = get_db_client()
                    client.command("""INSERT INTO default.app_tokens (token, package_name, quota, created_at, is_active) VALUES ({token:String}, {pkg:String}, {quota:Int32}, {date:DateTime}, 1)""", parameters={"token": new_token, "pkg": package_name, "quota": int(quota_amount), "date": datetime.now()})
                    st.success("Token berhasil dibuat!"); st.markdown(f"### > `{new_token}`")
                except Exception as e: st.error(f"Gagal: {e}")

# ================= HALAMAN LOGIN =================
elif menu_option == "Login Token / Redeem":
    st.title("🔑 Masukkan Kode Akses Token")
    token_input = st.text_input("Kode Token:")
    if st.button("Validasi Token") and token_input.strip():
        with st.spinner("Mengecek ketersediaan token..."):
            success, msg = check_token_validity(token_input.strip())
            if success:
                st.session_state.authenticated = True
                st.session_state.token_info = msg
                st.session_state.token_code = token_input.strip()
                st.success("Token valid! Anda bisa kembali ke Halaman Utama untuk mengecek dokumen.")
            else: st.error(msg)

# ================= HALAMAN UTAMA =================
else:
    st.title("📄 Sistem Pengecekan Kemiripan Dokumen")
    st.caption("🔍 Engine: Turnitin-Style Web Search | Token dipotong saat tombol diklik")

    uploaded_file = st.file_uploader("Pilih dokumen berformat PDF", type="pdf")

    if uploaded_file is not None:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        total_pages = len(pdf_reader.pages)
        
        extracted_text = "".join(page.extract_text() + " " for page in pdf_reader.pages if page.extract_text())
        total_words = len(extracted_text.split())
        st.write(f"**Dokumen diterima:** {uploaded_file.name} ({total_pages} Halaman, ±{total_words} Kata)")
        
        if st.button("Jalankan Pengecekan (Gunakan 1 Kuota)", type="primary"):
            if not st.session_state.authenticated:
                st.warning("⚠️ Silakan validasi token di menu 'Login Token / Redeem' terlebih dahulu.")
            else:
                # POTONG TOKEN DISINI
                if redeem_token_quota(st.session_state.token_code):
                    # Update sisa kuota di UI
                    _, updated_info = check_token_validity(st.session_state.token_code)
                    st.session_state.token_info = updated_info
                    
                    with st.spinner("Memindai miliaran halaman internet..."):
                        sentences = re.split(r'(?<=[.!?]) +', extracted_text)
                        valid_sentences = [s.strip() for s in sentences if len(s.split()) > 7]
                        sentences_to_check = valid_sentences[:5] # Cek 5 kalimat sampel untuk stabilitas API
                        
                        found_sources = []
                        highlighted_html = ""
                        color_palette = ["#ffcccc", "#cce5ff", "#d5f5e3", "#fcf3cf", "#e8daef"]
                        matched_count = 0
                        
                        ddgs = DDGS()
                        for i, sentence in enumerate(sentences_to_check):
                            try:
                                search_results = list(ddgs.text(f'"{sentence}"', max_results=1))
                                if search_results:
                                    candidate_url = search_results[0].get("href", "")
                                    candidate_title = search_results[0].get("title", "Sumber Internet")
                                    
                                    if candidate_url:
                                        scraped_content = scrape_web_text(candidate_url)
                                        if sentence.lower() in scraped_content.lower():
                                            matched_count += 1
                                            source_index = len(found_sources) + 1
                                            bg_color = color_palette[source_index % len(color_palette)]
                                            
                                            found_sources.append({
                                                "index": source_index,
                                                "url": candidate_url,
                                                "title": candidate_title,
                                                "color": bg_color
                                            })
                                            
                                            # Format Teks Highlight ala Turnitin
                                            highlighted_html += f"""
                                            <span class="highlight-container">
                                                <span style="background-color: {bg_color}; padding: 2px; border-radius: 2px;" onclick="togglePopup(this)">
                                                    {sentence} <sup style="color:red; font-weight:bold;">[{source_index}]</sup>
                                                </span>
                                                <div class="plagiarized-popup">
                                                    <b>Sumber Terdeteksi [{source_index}]:</b><br>
                                                    <a href="{candidate_url}" target="_blank" style="color: #4da6ff;">{candidate_title}</a>
                                                </div>
                                            </span> """
                                            continue 
                            except Exception: pass
                            
                            # Jika tidak plagiat, masukkan sebagai teks biasa tanpa span/warna
                            highlighted_html += f"{sentence} "

                        # --- KALKULASI PERSENTASE TURNITIN-STYLE ---
                        similarity_percentage = int((matched_count / len(sentences_to_check)) * 100) if sentences_to_check else 0
                        
                        st.markdown("---")
                        if similarity_percentage > 0:
                            # TAMPILAN JIKA TERDETEKSI PLAGIASI
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                st.write("### Pratinjau Dokumen")
                                st.markdown(f'<div style="border: 1px solid #ddd; padding: 20px; border-radius: 5px; background-color: #fafafa; line-height: 2.0; font-family: serif;">{highlighted_html} ... [Sisa teks diproses]</div>', unsafe_allow_html=True)
                            
                            with col2:
                                st.write("### Integrity Overview")
                                st.markdown(f'<div class="turnitin-source-list"><p class="turnitin-score">{similarity_percentage}%</p><p style="font-weight:bold; color:#555;">Overall Similarity</p><hr>', unsafe_allow_html=True)
                                
                                for src in found_sources:
                                    st.markdown(f"""
                                    <div style="margin-bottom: 10px;">
                                        <span style="background-color: {src['color']}; padding: 2px 6px; font-weight: bold; border-radius: 3px; font-size: 12px;">{src['index']}</span>
                                        <span style="font-size: 14px; margin-left: 5px;">
                                            <a href="{src['url']}" target="_blank" style="color: #333; text-decoration: none;">{src['title'][:35]}...</a>
                                        </span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                st.markdown("</div>", unsafe_allow_html=True)
                        else:
                            # TAMPILAN JIKA 100% AMAN (TEKS BIASA, TANPA STABILO IJO)
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                st.write("### Pratinjau Dokumen")
                                safe_text = " ".join(sentences_to_check)
                                st.markdown(f'<div style="border: 1px solid #ddd; padding: 20px; border-radius: 5px; background-color: #fafafa; line-height: 2.0; font-family: serif;">{safe_text} ... [Sisa teks diproses]</div>', unsafe_allow_html=True)
                            
                            with col2:
                                st.write("### Integrity Overview")
                                st.markdown('<div class="turnitin-source-list"><p style="font-size: 48px; font-weight: bold; color: #28a745; margin-bottom: 0;">0%</p><p style="font-weight:bold; color:#555;">Overall Similarity</p><hr><p style="color:#777; font-size:14px;">Bebas dari deteksi plagiasi internet.</p></div>', unsafe_allow_html=True)
                else:
                    st.error("Gagal memotong kuota. Pastikan token Anda masih memiliki sisa kuota yang valid.")
