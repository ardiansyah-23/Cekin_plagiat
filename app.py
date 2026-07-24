import streamlit as st
import clickhouse_connect
import PyPDF2
import uuid
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Cek Kemiripan Dokumen", layout="wide")

# --- CSS UNTUK TOOLTIP ---
st.markdown("""
<style>
.tooltip {
  position: relative;
  display: inline-block;
  background-color: #ffcccc; 
  cursor: pointer;
  padding: 0 4px;
  border-radius: 3px;
}
.tooltip .tooltiptext {
  visibility: hidden;
  width: 280px;
  background-color: #333;
  color: #fff;
  text-align: center;
  border-radius: 6px;
  padding: 8px;
  position: absolute;
  z-index: 1;
  bottom: 125%; 
  left: 50%;
  margin-left: -140px;
  opacity: 0;
  transition: opacity 0.3s;
  font-size: 14px;
}
.tooltip:hover .tooltiptext {
  visibility: visible;
  opacity: 1;
}
</style>
""", unsafe_allow_html=True)

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
# 1. LOGIKA VERIFIKASI TOKEN USER
# ==========================================
def verify_user_token(token_input):
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

# Status Sesi Token di Sidebar
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

# Filter Tambahan di Sidebar
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
    st.write("Silakan masukkan kode token yang Anda beli dari Admin melalui WhatsApp.")
    
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
    st.caption("🔒 Mode: No Repository (Aman untuk Draf Publikasi)")

    st.write("### Unggah Draf Dokumen")
    uploaded_file = st.file_uploader("Pilih dokumen berformat PDF", type="pdf")

    if uploaded_file is not None:
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        total_pages = len(pdf_reader.pages)
        
        st.write(f"**Dokumen diterima:** {uploaded_file.name} ({total_pages} Halaman)")
        
        if st.button("Jalankan Pengecekan", type="primary"):
            if not st.session_state.authenticated:
                st.warning("⚠️ Anda belum memasukkan token akses. Silakan masukkan token terlebih dahulu melalui menu **Login Token / Redeem** di sidebar.")
            else:
                with st.spinner("Memproses N-grams dan mencocokkan ke database..."):
                    
                    # --- SIMULASI HASIL LAPORAN ---
                    st.markdown("---")
                    st.subheader("Integrity Overview")
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Indeks Kemiripan", "12%", delta="-Normal", delta_color="inverse")
                    col2.metric("Sumber Terdeteksi", "1")
                    col3.metric("Kata Diproses", "4,520")
                    
                    # --- SIMULASI PREVIEW DOKUMEN DENGAN TOOLTIP ---
                    st.write("### Pratinjau Sorotan Teks")
                    st.markdown("""
                    <div style="border: 1px solid #ddd; padding: 20px; border-radius: 5px; background-color: #fafafa;">
                        Penelitian ini bertujuan untuk mengembangkan sistem baru. 
                        <span class="tooltip">Sistem ini dirancang dengan menggunakan arsitektur modern berbasis cloud
                          <span class="tooltiptext"><b>Sumber:</b> https://jurnal-komputasi.com/arsitektur<br><b>Kemiripan:</b> 100%</span>
                        </span>. 
                        Dengan demikian, performa pencarian dapat berjalan secara langsung dan efisien tanpa menyimpan data secara permanen.
                    </div>
                    """, unsafe_allow_html=True)
