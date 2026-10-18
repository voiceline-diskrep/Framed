import os
import sys
import json
import subprocess
import urllib.request
import urllib.error

def get_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.splitlines():
        if line.startswith('password='):
            return line.split('=', 1)[1]
    raise ValueError("GitHub token not found in git credential manager")

def publish_release(
    tag: str = "v1.3.0-experimental",
    target_branch: str = "experimental",
    prerelease: bool = True
):
    token = get_token()
    repo = "voiceline-diskrep/Framed"
    name = "Framed v1.3.0-experimental — Google Drive Cloud Integration (OAuth 2.0)"
    body = (
        "## 🧪 Framed v1.3.0-experimental (Pre-Release)\n\n"
        "> **Note:** This is an **Experimental Pre-Release** build on the `experimental` branch. "
        "Stable users on `v1.2.1` remain on the stable update channel unless **Enable Experimental Mode** is turned on in **Settings → Preferences**.\n\n"
        "### ☁️ In-App Google Drive API (OAuth 2.0) Integration\n"
        "* **Experimental Mode & Beta Channel Toggle**: New toggle in **Preferences** that unlocks experimental features and switches the in-app auto-updater to include GitHub Pre-releases.\n"
        "* **In-App Google OAuth 2.0 Sign-In**: Load your Google Cloud `client_secret.json` (or paste Client ID & Secret) with a built-in **1-Minute Setup Guide**, and click **Sign in with Google** to authenticate via browser PKCE loopback.\n"
        "* **Google Drive Cloud Import (Photo & Video)**: Click **Google Drive...** in New Session Setup to browse your Google Drive folders (or paste a shared Drive folder link/ID) and download files into a local workspace cache for zero-lag culling.\n"
        "* **Google Drive Cloud Export (Photo & Video)**: Switch between **Local Disk** and **Google Drive (Experimental)** in the Export dialog. Includes category checkboxes (`Selected`, `Maybe`/`Similar`, and `Edited Result` checked by default; `Unselected` unchecked by default to save cloud storage).\n"
        "* **Full Real-Time Telemetry Progress Bar**: Both cloud downloads and resumable chunked uploads display live percentage (`0–100%`), file counter (`12 / 45 files`), transfer speed (`MB/s`), `ETA`, current filename, `Cancel` button, and an **Open in Google Drive** button upon completion.\n\n"
        "### 📦 Downloads\n"
        f"* **Windows Experimental Installer**: `Framed-Setup-{tag}.exe`\n"
    )

    exe_name = f"Framed-Setup-{tag}.exe"
    asset_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "installer", "Output", exe_name))
    if not os.path.exists(asset_path):
        raise FileNotFoundError(f"Installer binary not found at {asset_path}")

    asset_size = os.path.getsize(asset_path)
    print(f"Publishing {'pre-release' if prerelease else 'release'} {tag} ({asset_size / (1024*1024):.2f} MB)...")

    # Step 1: Check if release for tag already exists
    release_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    req = urllib.request.Request(release_url, headers={
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Framed-Release-Tool',
        'Accept': 'application/vnd.github+json'
    })
    
    release_data = None
    try:
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode())
            print(f"Existing release found for {tag} (ID: {release_data['id']})")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Creating new release for {tag}...")
        else:
            raise

    # Step 2: Create release if not exists
    if not release_data:
        create_url = f"https://api.github.com/repos/{repo}/releases"
        payload = json.dumps({
            "tag_name": tag,
            "target_commitish": target_branch,
            "name": name,
            "body": body,
            "draft": False,
            "prerelease": prerelease
        }).encode('utf-8')
        
        req = urllib.request.Request(create_url, data=payload, headers={
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Framed-Release-Tool',
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json'
        })
        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode())
            print(f"Release created successfully! (ID: {release_data['id']})")

    upload_url_template = release_data['upload_url']
    upload_url = upload_url_template.split('{')[0] + f"?name={exe_name}"

    # Step 3: Check if asset already uploaded
    for asset in release_data.get('assets', []):
        if asset['name'] == exe_name:
            print(f"Deleting existing asset {asset['name']} (ID: {asset['id']}) to re-upload...")
            del_req = urllib.request.Request(asset['url'], headers={
                'Authorization': f'Bearer {token}',
                'User-Agent': 'Framed-Release-Tool',
                'Accept': 'application/vnd.github+json'
            }, method='DELETE')
            urllib.request.urlopen(del_req)
            print("Existing asset deleted.")

    # Step 4: Upload asset
    print(f"Uploading {os.path.basename(asset_path)} ({asset_size / (1024*1024):.2f} MB)...")
    with open(asset_path, 'rb') as f:
        file_data = f.read()

    upload_req = urllib.request.Request(upload_url, data=file_data, headers={
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Framed-Release-Tool',
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/octet-stream',
        'Content-Length': str(len(file_data))
    })

    with urllib.request.urlopen(upload_req, timeout=300) as resp:
        asset_info = json.loads(resp.read().decode())
        print(f"Asset uploaded successfully! Download URL: {asset_info['browser_download_url']}")

    print("\n" + "=" * 60)
    print("  GITHUB PRE-RELEASE PUBLISHED SUCCESSFULLY!")
    print(f"  Release: {release_data['html_url']}")
    print(f"  Version: {tag} (prerelease={prerelease})")
    print("=" * 60)

if __name__ == '__main__':
    publish_release()
