"""
Legal Document Verifier Launcher
Runs Streamlit directly in-process to avoid subprocess issues with PyInstaller.
"""
import sys
import os
import webbrowser
import threading
import multiprocessing

def open_browser_delayed():
    """Open browser after a delay to let server start"""
    import time
    time.sleep(4)
    print("Opening browser...")
    webbrowser.open("http://localhost:8501")

def main():
    # CRITICAL: freeze_support must be called before anything else
    multiprocessing.freeze_support()
    
    # Get the directory where this script is located
    if getattr(sys, 'frozen', False):
        # Running as compiled exe - files are in _MEIPASS
        base_dir = sys._MEIPASS
        print(f"[PyInstaller] Running from: {base_dir}")
    else:
        # Running as script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[Dev] Running from: {base_dir}")
    
    # Verify app.py exists
    app_path = os.path.join(base_dir, 'app.py')
    print(f"Looking for app at: {app_path}")
    
    if not os.path.exists(app_path):
        print(f"ERROR: app.py not found at {app_path}")
        print(f"Contents of {base_dir}:")
        for f in os.listdir(base_dir)[:20]:
            print(f"  - {f}")
        input("Press Enter to exit...")
        return
    
    # Change to base directory so file server works
    os.chdir(base_dir)
    
    # Add base_dir to path so imports work
    sys.path.insert(0, base_dir)
    
    print("Starting Legal Doc Verifier...")
    
    # Open browser in background thread (only ONCE)
    browser_thread = threading.Thread(target=open_browser_delayed, daemon=True)
    browser_thread.start()
    
    # Run Streamlit directly (not via subprocess)
    from streamlit.web import cli as stcli
    
    # Set up streamlit arguments - use absolute path and force port 8501
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port", "8501",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false"
    ]
    
    print(f"Starting Streamlit with: {sys.argv}")
    stcli.main()

if __name__ == "__main__":
    main()
