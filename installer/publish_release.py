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
    tag: str = "v1.4.0",
    target_branch: str = "master",
    prerelease: bool = False
):
    token = get_token()
    repo = "voiceline-diskrep/Framed"
    name = "Framed v1.4.0 — Complete Premium UI/UX Redesign & Nested Workspace Folders"
    body = (
        "## What's Changed in Framed v1.4.0\n\n"
        "### 🎨 Complete Premium UI/UX Visual Redesign\n"
        "* **New 'Studio Pro' Theme**: Refined Apple & Adobe creative workstation interface (#101114, #15171B, #191C21, #202329, #F59E0B) with warm amber accents, subtle borders, and 10px rounded corners.\n"
        "* **Top KPI Summary Cards**: 4 live statistics cards (Sessions, Photos, Videos, Completed) featuring custom dynamic bezier sparkline graphs computed in real-time from storage.\n"
        "* **Instant Search & Status Filter Bar**: Client-side instant session title filtering plus status filter pills (All, Photos, Videos, Completed, In Progress) and view mode switchers.\n"
        "* **Cover Photo Thumbnails**: Asynchronously loaded 120x80px rounded cover photo previews (first kept/selected photo or shoot hero photo) with camera aperture fallback placeholder.\n"
        "* **Misty Mountain Sidebar Landscape**: Subtle dark mountain silhouette in the sidebar bottom corner smoothly fading into dark charcoal.\n\n"
        "### 📁 Nested Workspace Folders\n"
        "* **Subfolders at Any Depth**: Create and organize nested subfolders inside workspace categories.\n"
        "* **Collapsible Sidebar Tree**: Native carets (▸/▾) with right-aligned session count badges.\n"
        "* **Hierarchical Disk & Cloud Sync**: Folder trees are automatically mirrored on disk exports and Google Drive.\n"
        "* **Breadcrumb Navigation**: Header path display (Projects › Category › Subfolder).\n\n"
        "### 📦 Downloads\n"
        f"* **Windows Installer**: `Framed-Setup-{tag}.exe`\n"
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
