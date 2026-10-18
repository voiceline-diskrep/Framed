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

def publish_release():
    token = get_token()
    repo = "voiceline-diskrep/Framed"
    tag = "v1.2.1"
    name = "Framed v1.2.1 — Session Isolation & Workstation Polish"
    body = (
        "## What's Changed in Framed v1.2.1\n\n"
        "### 🛠️ Session Isolation & Bug Fixes\n"
        "* **Session Isolation Carryover**: Fixed a race condition where exiting to the dashboard and opening another session could display pictures and cached buffers from the previous session.\n"
        "* **Incremental Session Generation Tokens**: Preload requests and background decoding workers are now tagged with generational IDs. Any in-flight decodes from an older session are immediately discarded.\n"
        "* **Explicit Lifecycle Unload (`unload_project`)**: Review screens now completely reset the canvas scene, purge cached frames, clear the undo stack, and reset optical telemetry when switching sessions or returning to the dashboard.\n"
        "* **Immediate Canvas Reset**: The canvas is cleared immediately when loading new sessions to prevent stale preview retention during background preloads.\n\n"
        "### 🎨 Workstation Themes & Enhancements (v1.2.0)\n"
        "* **6 Clean Descriptive Themes**: Dark Amber, OLED, Dark Blue, Dark Green, Neutral Gray, and Light.\n"
        "* **Quick Theme Switcher**: Available directly in the Dashboard header and Settings dialog.\n"
        "* **RAM Scaling Beyond 32 Photos**: Smooth multi-gigabyte memory buffer preloading calibrated to system RAM.\n\n"
        "### 📦 Downloads\n"
        "* **Windows Installer**: `Framed-Setup-v1.2.1.exe`\n"
    )

    asset_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "installer", "Output", "Framed-Setup-v1.2.1.exe"))
    if not os.path.exists(asset_path):
        raise FileNotFoundError(f"Installer binary not found at {asset_path}")

    asset_size = os.path.getsize(asset_path)
    print(f"Publishing release {tag} ({asset_size / (1024*1024):.2f} MB)...")

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
            "target_commitish": "master",
            "name": name,
            "body": body,
            "draft": False,
            "prerelease": False
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

    upload_url_template = release_data['upload_url'] # e.g. https://uploads.github.com/repos/.../assets{?name,label}
    upload_url = upload_url_template.split('{')[0] + f"?name=Framed-Setup-v1.2.1.exe"

    # Step 3: Check if asset already uploaded
    for asset in release_data.get('assets', []):
        if asset['name'] == 'Framed-Setup-v1.2.1.exe':
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

    with urllib.request.urlopen(upload_req) as resp:
        asset_info = json.loads(resp.read().decode())
        print(f"Asset uploaded successfully! Download URL: {asset_info['browser_download_url']}")

    print("\n" + "=" * 60)
    print("  GITHUB RELEASE PUBLISHED SUCCESSFULLY!")
    print(f"  Release: {release_data['html_url']}")
    print(f"  Version: {tag}")
    print("=" * 60)

if __name__ == '__main__':
    publish_release()
