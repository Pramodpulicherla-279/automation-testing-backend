import os
import gdown
import uuid
import shutil
import sys
from androguard.core.apk import APK
sys.dont_write_bytecode = True

from app.core.paths import APK_ICON_DIR, APK_STORAGE_DIR, ensure_apk_dirs

ensure_apk_dirs()
DOWNLOAD_DIR = str(APK_STORAGE_DIR)
ICON_DIR = str(APK_ICON_DIR)

# --- Helper Class to Capture STDERR (for tqdm progress) ---
class ProgressCapture:
    def __init__(self, callback):
        self.callback = callback

    def write(self, message):
        # Only send non-empty messages
        if message and message.strip():
            self.callback(message)

    def flush(self):
        pass

def extract_app_icon(apk_path: str) -> str:
    """
    Extracts the icon from the APK and saves it as a PNG.
    Returns: The relative path to the saved icon image.
    """
    if not os.path.exists(ICON_DIR):
        os.makedirs(ICON_DIR, exist_ok=True)
    
    try:
        # 1. Parse the APK
        app = APK(apk_path)
        
        # 2. get_app_icon() returns the path/name of the icon file inside the APK
        icon_name = app.get_app_icon()
        if not icon_name:
            print("⚠️ No icon found in APK.")
            return None

        # 3. Read the actual bytes of that file from the APK
        icon_data = app.get_file(icon_name)
        if not icon_data:
            print(f"⚠️ Could not read icon file from APK: {icon_name}")
            return None

        # 4. Create a unique filename for the icon (same base name as APK)
        apk_filename = os.path.basename(apk_path)
        icon_filename = apk_filename.replace(".apk", ".png")
        icon_path = os.path.join(ICON_DIR, icon_filename)

        # 5. Save bytes to file
        with open(icon_path, "wb") as f:
            f.write(icon_data)
            
        print(f"🖼️ Icon extracted: {icon_path}")
        
        # Return URL-friendly path
        return f"/static/icons/{icon_filename}"

    except Exception as e:
        print(f"❌ Failed to extract icon: {e}")
        return None
    
def get_apk_info(apk_path: str) -> dict | None:
    """
    Returns basic metadata from the APK:
    { "app_name": str, "package_name": str, "version_name": str, "version_code": str }
    Returns APK metadata used by API + Jira context.
    """
    try:
        app = APK(apk_path)
        package_name = app.get_package() or ""
        app_name = app.get_app_name() or "Unknown App"
        app_version = app.get_androidversion_name() or str(app.get_androidversion_code() or "Unknown Version")

        # APK usually does not contain a clean "developer name" field.
        # Prefer explicit env override; fallback to package prefix inference.
        developer_name = os.getenv("APP_DEVELOPER_NAME", "").strip()
        if not developer_name:
            parts = [p for p in package_name.split(".") if p and p not in {"com", "in", "org", "net", "io"}]
            developer_name = parts[0].replace("_", " ").title() if parts else "Unknown Developer"


        version_name = None
        version_code = None

        for method in ["get_androidversion_name", "get_version_name", "androidversion_name"]:
            if hasattr(app, method):
                version_name = getattr(app, method)()
                if version_name:
                    break

        for method in ["get_androidversion_code", "get_version_code", "androidversion_code"]:
            if hasattr(app, method):
                version_code = getattr(app, method)()
                if version_code:
                    break
        print(f"📱 APK Info - Name: {app.get_app_name()}, Package: {app.get_package()}, Version Name: {version_name}, Version Code: {version_code}")

        return {
            "app_name": app_name,
            "package_name": package_name,
            "app_version": app_version,
            "developer_name": developer_name,
            "version_name": version_name,
            "version_code": version_code,
        }
    except Exception as e:
        print(f"Failed to read APK info: {e}")
        return None
    
def download_apk(gdrive_url: str, progress_callback=None) -> str:
    """
    Downloads APK from Google Drive into DOWNLOAD_DIR,
    keeping the original APK filename.
    Returns: The ABSOLUTE path to the downloaded file (Required for Appium).
    """
    # 1. Ensure the download directory exists
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    print(f"⬇️ Starting download from GDrive: {gdrive_url}")
    print(f"📂 Target Directory: {DOWNLOAD_DIR}")

    # Capture original stderr
    original_stderr = sys.stderr

    try:
        # Redirect stderr if callback provided
        if progress_callback:
            sys.stderr = ProgressCapture(progress_callback)

        # 2. Let gdown decide the filename (original name), download to current dir
        # Note: gdown 6.x removed the `fuzzy` flag — URL parsing for share-link
        # formats (e.g. /file/d/<id>/view) is now handled automatically.
        tmp_path = gdown.download(
            gdrive_url,
            quiet=False,
        )

        # 3. Verify the file actually exists and isn't empty
        if not tmp_path or not os.path.exists(tmp_path):
            raise Exception("Download failed - gdown returned no path.")

        if os.path.getsize(tmp_path) < 1000:
            raise Exception("Download failed - File is too small (likely an HTML error page).")

        # 4. Move the file into DOWNLOAD_DIR, keeping original filename
        filename = os.path.basename(tmp_path)
        final_path = os.path.join(DOWNLOAD_DIR, filename)

        # If it's not already there, move it
        if os.path.abspath(tmp_path) != os.path.abspath(final_path):
            shutil.move(tmp_path, final_path)

        abs_path = os.path.abspath(final_path)
        print(f"✅ APK Ready at: {abs_path}")
        return abs_path

    except Exception as e:
        msg = str(e)
        print(f"❌ Error downloading APK: {msg}")
        # Cleanup: Remove partial file if it exists
        if 'tmp_path' in locals() and tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        # Translate gdown's verbose errors into a concise, actionable message.
        low = msg.lower()
        if "public link" in low or "permission" in low or "anyone with the link" in low:
            raise Exception(
                "Google Drive file is not publicly accessible. In Drive open the file → "
                "Share → General access → set to 'Anyone with the link', then try again. "
                "(Or pick a file under 'Select Existing APK'.)"
            )
        if "too small" in low or "html error page" in low:
            raise Exception(
                "The downloaded file isn't a valid APK (got an HTML page). Make sure the "
                "Drive link points directly to the APK and is shared with 'Anyone with the link'."
            )
        raise Exception(f"APK download failed: {msg.splitlines()[0][:200]}")

    finally:
        # Restore stderr
        sys.stderr = original_stderr
    
def cleanup_apk(file_path: str):
    """
    Optional: Call this after test finishes to free up space
    """
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"🧹 Cleaned up temporary APK: {file_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python gdrive_loader.py <url>")
        sys.exit(1)
    
    url = sys.argv[1]

    # Callback to print normalized progress to STDOUT for server.py to read
    def cli_progress_callback(msg):
        # Remove Carriage Returns
        clean = msg.replace('\r', '').strip()
        if clean:
            # Prefix with 'PROGRESS:' so server knows it's a status update
            print(f"PROGRESS:{clean}")
            sys.stdout.flush()

    try:
        path = download_apk(url, cli_progress_callback)
        # Output the final result with a specific prefix
        print(f"RESULT:{path}")
    except Exception as e:
        # Print error to stderr so server wraps it in 400
        sys.stderr.write(str(e))
        sys.exit(1)