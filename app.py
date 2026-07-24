import streamlit as st
import clickhouse_connect
import PyPDF2

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Cek Kemiripan", layout="wide")

# --- CSS UNTUK TOOLTIP (Menampilkan Sumber Referensi) ---
st.markdown("""
<style>
.tooltip {
  position: relative;
  display: inline-block;
  background-color: #ffcccc; /* Warna sorotan merah muda ala Turnitin */
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

# --- HEADER APLIKASI ---
st.title("Sistem Pengecekan Kemiripan Dokumen")
st.caption("🔒 Mode: No Repository (Aman untuk Draf Publikasi)")

# --- INISIALISASI DATABASE CLICKHOUSE ---
@st.cache_resource
def init_connection():
    try:
        return clickhouse_connect.get_client(
            host=st.secrets["clickhouse"]["host"],
            port=st.secrets["clickhouse"]["port"],
            username=st.secrets["clickhouse"]["username"],
            password=st.secrets["clickhouse"]["password"],
            secure=True
        )
    except Exception as e:
        return None

client = init_connection()

if client is None:
    st.info("Koneksi database belum dikonfigurasi. Lengkapi Streamlit Secrets setelah deploy.")
else:
    st.success("Terkoneksi dengan Database Utama.")

# --- SIDEBAR (PENGATURAN) ---
st.sidebar.header("Filter Pengecekan")
exclude_quotes = st.sidebar.checkbox("Exclude Quotes (Abaikan Kutipan)", value=True)
exclude_biblio = st.sidebar.checkbox("Exclude Bibliography (Abaikan Daftar Pustaka)", value=True)

# --- AREA UNGGAH DOKUMEN ---
st.write("### Unggah Draf")
uploaded_file = st.file_uploader("Pilih dokumen berformat PDF", type="pdf")

if uploaded_file is not None:
    # Membaca PDF
    pdf_reader = PyPDF2.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    
    st.write(f"**Dokumen diterima:** {uploaded_file.name} ({total_pages} Halaman)")
    
    if st.button("Jalankan Pengecekan", type="primary"):
        with st.spinner("Memproses N-grams dan mencocokkan ke database..."):
            
            # TODO: Di sinilah logika pemrosesan teks dan kueri ClickHouse akan dibangun nanti
            
            # --- SIMULASI HASIL LAPORAN (Integrity Overview) ---
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
