import streamlit as st
import os
import json
import tempfile
import time
import base64
from pathlib import Path
import shutil
import streamlit.components.v1 as components

# Import existing logic
from legal_extraction import extract_legal_data
from highlight_evidence_pure import highlight_evidence_pure

st.set_page_config(layout="wide", page_title="Legal Doc Verifier")

# Custom CSS for green primary button
st.markdown("""
<style>
    .stButton > button[kind="primary"] {
        background-color: #28a745 !important;
        border-color: #28a745 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #218838 !important;
        border-color: #1e7e34 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Password Protection ---
# Set APP_PASSWORD in Streamlit Secrets to enable protection
# If not set, password protection is disabled (for local dev)
def check_password():
    """Returns True if authenticated, False otherwise."""
    app_password = None
    try:
        app_password = st.secrets.get("APP_PASSWORD")
    except:
        pass
    
    # If no password is configured, allow access (for local dev)
    if not app_password:
        return True
    
    if st.session_state.get("authenticated"):
        return True
    
    # Show login form
    st.title("🔐 Legal Doc Verifier")
    st.markdown("This app is password protected.")
    
    # Use form so Enter key submits
    with st.form("login_form"):
        password = st.text_input("Enter Password", type="password", key="password_input")
        submitted = st.form_submit_button("Login", type="primary")
        
        if submitted:
            if password == app_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
    
    return False

if not check_password():
    st.stop()

# --- PDF Display Helper ---
def get_pdf_base64(file_path):
    """Reads a PDF file and returns a base64 encoded string."""
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode('utf-8')
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
        return None

PDF_DIR = os.path.join(os.getcwd(), "temp_pdfs") 
if not os.path.exists(PDF_DIR):
    os.makedirs(PDF_DIR)

# --- Session State ---
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False

if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {} 

if 'citation_map' not in st.session_state:
    st.session_state.citation_map = {}

if 'highlighted_filename' not in st.session_state:
    st.session_state.highlighted_filename = None

if 'uploaded_file_name' not in st.session_state:
    st.session_state.uploaded_file_name = None

if 'preview_filename' not in st.session_state:
    st.session_state.preview_filename = None

if 'nav_count' not in st.session_state:
    st.session_state.nav_count = 0

# --- UI Layout ---

st.sidebar.title("📄 Legal Verifier")

# API Key Config File (stored in user's home directory for persistence)
API_KEY_FILE = os.path.join(os.path.expanduser("~"), ".legal_verifier_api_key")

def load_saved_api_key():
    """Load API key from config file if it exists"""
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r") as f:
                return f.read().strip()
        except:
            pass
    return ""

def save_api_key(key):
    """Save API key to config file"""
    try:
        with open(API_KEY_FILE, "w") as f:
            f.write(key)
    except Exception as e:
        st.warning(f"Could not save API key: {e}")

# Check for API key in Streamlit secrets first
secrets_api_key = None
try:
    secrets_api_key = st.secrets.get("GEMINI_API_KEY")
except:
    pass

# Load saved key on first run (secrets take priority)
if "api_key" not in st.session_state:
    if secrets_api_key:
        st.session_state.api_key = secrets_api_key
    else:
        st.session_state.api_key = load_saved_api_key()

# Only show API Key input if NOT configured via secrets
if not secrets_api_key:
    st.sidebar.subheader("🔑 API Configuration")
    api_key = st.sidebar.text_input(
        "Gemini API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        help="Enter your Google Gemini API key. It will be saved for next time."
    )
    
    # Save if changed
    if api_key and api_key != st.session_state.get("api_key", ""):
        st.session_state.api_key = api_key
        save_api_key(api_key)
        st.sidebar.success("✅ API key saved!")
    
    st.sidebar.divider()

# If secrets_api_key is set, no API section is shown at all


uploaded_file = st.sidebar.file_uploader("Upload Contract (PDF)", type=["pdf"])

# Immediate save for preview
if uploaded_file:
    # Check if we need to save (new upload)
    if st.session_state.uploaded_file_name != uploaded_file.name:
        st.session_state.uploaded_file_name = uploaded_file.name
        st.session_state.analysis_complete = False
        st.session_state.highlighted_filename = None
        st.session_state.extracted_data = {}
        st.session_state.citation_map = {}
        
        # Save for preview serving
        # Use a safe name to avoid weird URL chars
        safe_preview_name = f"preview_{int(time.time())}.pdf"
        preview_path = os.path.join(PDF_DIR, safe_preview_name)
        with open(preview_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        st.session_state.preview_filename = safe_preview_name

def run_analysis():
    if not uploaded_file or not st.session_state.preview_filename:
        return

    # Don't re-run if done
    if st.session_state.analysis_complete:
        return

    with st.spinner("⏳ Analyzing document with Gemini & highlighting evidence..."):
        # Input path is the preview file we already saved
        input_path = os.path.join(PDF_DIR, st.session_state.preview_filename)
        
        # Check for API key
        api_key = st.session_state.get("api_key", "")
        if not api_key:
            st.error("⚠️ Please enter your Gemini API key in the sidebar first.")
            return
        
        # A. Extract Data
        try:
            json_str = extract_legal_data(input_path, api_key=api_key)
            
            print("--- RAW GEMINI RESPONSE ---")
            print(json_str)
            
            cleaned_json = json_str.strip()
            if cleaned_json.startswith("```json"):
                cleaned_json = cleaned_json[7:]
            if cleaned_json.endswith("```"):
                cleaned_json = cleaned_json[:-3]
            
            try:
                extracted_data = json.loads(cleaned_json)
                
                # Handle list wrapping (e.g. [{...}])
                if isinstance(extracted_data, list):
                    if len(extracted_data) > 0 and isinstance(extracted_data[0], dict):
                        # Merge if multiple, or just take first? 
                        # Usually it's just one object wrapped.
                        temp_data = {}
                        for item in extracted_data:
                            if isinstance(item, dict):
                                temp_data.update(item)
                        extracted_data = temp_data
                    else:
                         st.error("Unexpected data format: List does not contain dictionaries.")
                         return

                if not isinstance(extracted_data, dict):
                     st.error("Unexpected data format from AI. Expected dictionary.")
                     return
            except json.JSONDecodeError:
                st.error("Invalid JSON received.")
                return

        except Exception as e:
            st.error(f"Extraction failed: {e}")
            return
            
        # B. Highlight & Map Pages
        # Construct evidence list for new API
        evidence = []
        for key, item in extracted_data.items():
            if isinstance(item, dict):
                evidence.append({
                    "label": key,
                    "quote": item.get('verbatim_quote'), 
                    "gemini_page": item.get('page_number')
                })
        
        safe_highlight_name = f"highlighted_{int(time.time())}.pdf"
        output_pdf_path = os.path.join(PDF_DIR, safe_highlight_name)
        
        citations = highlight_evidence_pure(input_path, output_pdf_path, evidence)
        
        # --- SPLIT PDF INTO INDIVIDUAL PAGES ---
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(output_pdf_path)
        page_base_name = f"page_{int(time.time())}"
        
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            page_filename = f"{page_base_name}_{i+1}.pdf"
            page_path = os.path.join(PDF_DIR, page_filename)
            with open(page_path, "wb") as f:
                writer.write(f)
        
        st.session_state.extracted_data = extracted_data
        st.session_state.citation_map = citations
        st.session_state.highlighted_filename = safe_highlight_name
        st.session_state.page_base_name = page_base_name
        st.session_state.total_pages = len(reader.pages)
        st.session_state.analysis_complete = True


if uploaded_file:
    if st.sidebar.button("Analyze Document"):
        run_analysis()
        
    # --- Sidebar Results ---
    if st.session_state.analysis_complete:
        st.sidebar.markdown("---")
        st.sidebar.subheader("📌 Extracted Data")
        
        data_dict = st.session_state.extracted_data
        
        for label, item in data_dict.items():
            if not isinstance(item, dict): continue
            
            val = item.get('value')
            if val is None:
                val = "N/A"
            quote = item.get('verbatim_quote', None)
            
            # Lookup by Label now
            cit_info = st.session_state.citation_map.get(label, {})
            page_num = cit_info.get("page")
            status = cit_info.get("status", "missing")
            
            st.sidebar.markdown(f"**{label}**")
            
            # Layout: [Nav Button (Original Style)] [Copy Code]
            # Col 1: Wide button with "Value (Pg X)"
            # Col 2: Narrow code block for copying just the value
            col_nav, col_copy = st.sidebar.columns([0.85, 0.15])
            
            with col_nav:
                # Reconstruct the original label with verification icon
                # Verified: ✅ Value (Pg X)
                # Unverified: ⚠️ Value (Approx Pg X)
                # Missing: ❌ Value
                
                btn_label = f"{val}"
                
                if page_num:
                    if status == "verified":
                        btn_label = f"✅ {val} (Pg {page_num})"
                    elif status == "unverified":
                        btn_label = f"⚠️ {val} (Approx Pg {page_num})"
                    else:
                         btn_label = f"{val} (Pg {page_num})"
                else:
                    btn_label += " ❌"

                if st.button(btn_label, key=f"btn_{label}"):
                    if page_num:
                        st.session_state.current_page = page_num
                        st.session_state.nav_count += 1
                        st.session_state.needs_refresh = True
                        st.session_state.view_whole_pdf = False  # Switch to single page mode
                        st.rerun()
            
            with col_copy:
                 # Custom HTML/JS button to copy text without showing it
                 # Escaping for JS string
                 safe_val = val.replace("'", "\\'")
                 components.html(
                    f"""
                    <div style="display: flex; align-items: center; justify-content: center; height: 100%;">
                        <button onclick="copyToClipboard()" style="border: none; background: none; cursor: pointer; font-size: 1.2rem;" title="Copy '{safe_val}'">
                            📋
                        </button>
                    </div>
                    <script>
                        function copyToClipboard() {{
                            navigator.clipboard.writeText('{safe_val}');
                        }}
                    </script>
                    """,
                    height=40
                 )
            
            st.sidebar.caption(f"\"{quote}\"")
            st.sidebar.markdown("---")

# --- Main View ---
col1, col2 = st.columns([1, 10])

with col2:
    # Determine which file to show: Highlighted (if done) or Preview (if uploaded)
    target_filename = None
    if st.session_state.highlighted_filename:
        target_filename = st.session_state.highlighted_filename
    elif st.session_state.preview_filename:
        target_filename = st.session_state.preview_filename

    if target_filename:
        # --- BLINK REFRESH LOGIC ---
        if st.session_state.get('needs_refresh', False):
            st.session_state.needs_refresh = False
            st.write("Loading...")
            st.rerun()
            st.stop()

        current_page = st.session_state.current_page
        nav_id = st.session_state.get('nav_count', 0)
        
        # --- VIEW MODE TOGGLE ---
        page_base_name = st.session_state.get('page_base_name')
        total_pages = st.session_state.get('total_pages', 1)
        view_whole = st.session_state.get('view_whole_pdf', False)
        
        # Button to toggle view mode
        if page_base_name:
            if not view_whole:
                # "View Whole PDF" button - full width, green
                if st.button("📑 View Whole PDF", use_container_width=True, type="primary"):
                    st.session_state.view_whole_pdf = True
                    st.rerun()
            else:
                # "View Single Page" button - compact (in column)
                col_view, col_spacer = st.columns([1, 4])
                with col_view:
                    if st.button("📄 View Single Page"):
                        st.session_state.view_whole_pdf = False
                        st.rerun()
        
        # --- SINGLE PAGE OR FULL PDF LOADING ---
        target_path = None
        pdf_base64 = None
        
        if page_base_name and not view_whole:
            # Load the specific page file (single-page PDF)
            target_path = os.path.join(PDF_DIR, f"{page_base_name}_{current_page}.pdf")
            st.info(f"Viewing Page {current_page} of {total_pages}")
        elif st.session_state.get('highlighted_filename'):
            # Load full highlighted PDF
            target_path = os.path.join(PDF_DIR, st.session_state.highlighted_filename)
            st.info(f"Viewing Full PDF (Page {current_page})")
        else:
            # Fallback: Load preview before analysis
            target_path = os.path.join(PDF_DIR, target_filename)
            st.info(f"Preview: {target_filename}")
        
        if target_path and os.path.exists(target_path):
            try:
                import fitz  # PyMuPDF
                
                doc = fitz.open(target_path)
                
                if view_whole:
                    # Render ALL pages in the document
                    # Note: If target_path is the highlighted file, it has all pages.
                    for i, page in enumerate(doc):
                        # Create an anchor for scrolling? Streamlit native anchors might be hard to jump to automatically
                        # But we can at least label them
                        st.markdown(f"### Page {i+1}")
                        
                        # Render high-res
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)) # 1.5x zoom
                        img_bytes = pix.tobytes("png")
                        st.image(img_bytes, use_container_width=True)
                        st.divider()
                else:
                    # Single page mode - render just the first page of this split file
                    # (Or the specific page if target_path was somehow the full file)
                    p_idx = 0
                    if len(doc) > 1:
                         # Fallback safety: if we somehow loaded a multi-page doc in single mode
                         p_idx = max(0, current_page - 1)
                    
                    if p_idx < len(doc):
                        page = doc.load_page(p_idx)
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
                        img_bytes = pix.tobytes("png")
                        st.image(img_bytes, use_container_width=True, caption=f"Page {current_page}")
                    else:
                        st.error("Page not found.")

                doc.close()
                
                # Keep download button as backup
                with open(target_path, "rb") as f:
                    pdf_bytes = f.read()
                    
                st.download_button(
                    label="📥 Download PDF",
                    data=pdf_bytes,
                    file_name=f"document.pdf",
                    mime="application/pdf"
                )
                
            except ImportError:
                st.error("PyMuPDF (fitz) not installed. Please add 'pymupdf' to requirements.txt")
            except Exception as e:
                st.error(f"Error rendering PDF: {e}")
        else:
             st.error("Could not load PDF file.")
        
    else:
        st.title("Welcome to Legal Verifier")
        st.markdown("""
        Upload a contract to:
        1. Extract key dates and clauses.
        2. Auto-highlight evidence in the PDF.
        3. Click to jump to the exact source.
        """)
