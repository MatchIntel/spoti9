import os
import re
import zipfile
import tempfile
import traceback
import requests
from flask import Flask, request, render_template_string, send_file, jsonify, redirect, session, url_for
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import yt_dlp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-here")

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:5000/callback")

def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope="playlist-read-private playlist-read-collaborative",
        cache_handler=None,
    )

def get_spotify_client():
    token_info = session.get("token_info")
    if not token_info:
        return None
    return Spotify(auth=token_info["access_token"])

# -------------------- HTML TEMPLATE (same) --------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Spotify Playlist Downloader</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
    <style>
        body { background: linear-gradient(135deg, #1db954, #191414); min-height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card { background: rgba(255,255,255,0.95); border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.5); padding: 40px; max-width: 600px; width: 100%; }
        .logo { text-align: center; margin-bottom: 30px; }
        .logo h1 { color: #1db954; font-weight: 700; }
        .logo p { color: #666; }
        .btn-spotify { background: #1db954; color: white; font-weight: 600; padding: 12px 30px; border-radius: 50px; transition: all 0.3s; }
        .btn-spotify:hover { background: #1aa34a; color: white; transform: scale(1.02); }
        .btn-login { background: #191414; color: white; font-weight: 600; padding: 12px 30px; border-radius: 50px; transition: all 0.3s; }
        .btn-login:hover { background: #000; color: white; transform: scale(1.02); }
        .form-control { border-radius: 50px; padding: 14px 20px; border: 2px solid #ddd; font-size: 16px; }
        .form-control:focus { border-color: #1db954; box-shadow: 0 0 0 0.2rem rgba(29,185,84,0.25); }
        .info-text { color: #888; font-size: 14px; margin-top: 15px; text-align: center; }
        .alert { border-radius: 12px; margin-top: 15px; }
        .loading { display: none; text-align: center; margin-top: 20px; }
        .spinner-border { width: 3rem; height: 3rem; color: #1db954; }
        .user-info { text-align: center; margin-bottom: 20px; padding: 10px; background: #f8f9fa; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">
            <h1>🎵 Spotify Downloader</h1>
            <p>Download playlists or tracks as MP3</p>
        </div>

        {% if user %}
        <div class="user-info">
            👤 Logged in as <strong>{{ user.display_name }}</strong>
            <a href="/logout" class="btn btn-sm btn-outline-danger ms-2">Logout</a>
        </div>
        {% else %}
        <div class="d-grid mb-3">
            <a href="/login" class="btn btn-login">🔑 Login with Spotify</a>
        </div>
        {% endif %}

        <form id="downloadForm">
            <div class="mb-3">
                <label for="urlInput" class="form-label fw-semibold">Enter Spotify URL</label>
                <input type="url" class="form-control" id="urlInput" placeholder="https://open.spotify.com/playlist/..." required />
                <div class="form-text">Supports playlists and individual tracks.</div>
            </div>
            <div class="d-grid">
                <button type="submit" class="btn btn-spotify" id="downloadBtn" {% if not user %}disabled{% endif %}>
                    ⬇️ Download
                </button>
            </div>
            {% if not user %}
            <p class="text-muted mt-2 text-center" style="font-size: 14px;">Please login with Spotify first</p>
            {% endif %}
        </form>
        <div class="loading" id="loading">
            <div class="spinner-border" role="status"></div>
            <p class="mt-2 text-muted">Downloading songs... This may take a few minutes.</p>
        </div>
        <div id="message"></div>
        <div class="info-text"><small>Powered by Flask, Spotify API & yt‑dlp. For personal use only.</small></div>
    </div>

    <script>
        const form = document.getElementById("downloadForm");
        const loading = document.getElementById("loading");
        const downloadBtn = document.getElementById("downloadBtn");
        const message = document.getElementById("message");

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const url = document.getElementById("urlInput").value.trim();
            if (!url) {
                showMessage("Please enter a valid Spotify URL.", "danger");
                return;
            }
            loading.style.display = "block";
            downloadBtn.disabled = true;
            downloadBtn.innerHTML = "⏳ Processing...";
            message.innerHTML = "";

            try {
                const response = await fetch("/download", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({ url })
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const link = document.createElement("a");
                    link.href = URL.createObjectURL(blob);
                    link.download = "playlist.zip";
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    showMessage("✅ Download complete! Your ZIP file is ready.", "success");
                } else {
                    const error = await response.json();
                    showMessage(`❌ ${error.error || "Something went wrong."}`, "danger");
                }
            } catch (err) {
                showMessage("❌ Network error. Please try again.", "danger");
            } finally {
                loading.style.display = "none";
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = "⬇️ Download";
            }
        });

        function showMessage(text, type) {
            message.innerHTML = `<div class="alert alert-${type}">${text}</div>`;
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    user = None
    sp = get_spotify_client()
    if sp:
        try:
            user = sp.current_user()
        except:
            session.clear()
            user = None
    return render_template_string(HTML_TEMPLATE, user=user)

@app.route("/login")
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Error: No code provided", 400
    sp_oauth = get_spotify_oauth()
    try:
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info
        return redirect(url_for("index"))
    except Exception as e:
        return f"Error during authentication: {e}", 400

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------- NEW: Fetch playlist with raw requests (no spotipy) ----------
def fetch_playlist_tracks_oauth(playlist_id, token):
    """Fetch tracks using the /playlists/{id} endpoint with user's token."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Spotify API error: {resp.status_code} - {resp.text}")
    
    data = resp.json()
    tracks_data = data.get("tracks", {})
    tracks = tracks_data.get("items", [])
    
    while tracks_data.get("next"):
        resp = requests.get(tracks_data["next"], headers=headers)
        if resp.status_code != 200:
            raise Exception(f"Pagination error: {resp.status_code}")
        tracks_data = resp.json()
        tracks.extend(tracks_data.get("items", []))
    
    return tracks
# -----------------------------------------------------------------------

@app.route("/download", methods=["POST"])
def download():
    token_info = session.get("token_info")
    if not token_info:
        return jsonify({"error": "Please login with Spotify first."}), 401
    
    access_token = token_info["access_token"]
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    url = url.split("?")[0]
    playlist_id = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    track_id = re.search(r"track/([a-zA-Z0-9]+)", url)

    if not playlist_id and not track_id:
        return jsonify({"error": "Invalid Spotify URL"}), 400

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            downloaded = []

            if playlist_id:
                playlist_id = playlist_id.group(1)
                # Fetch tracks using raw requests with user token
                tracks = fetch_playlist_tracks_oauth(playlist_id, access_token)

                if not tracks:
                    return jsonify({"error": "No tracks found in playlist"}), 404

                for item in tracks:
                    track = item.get("track")
                    if not track:
                        continue
                    track_name = track.get("name", "Unknown")
                    artist_name = track["artists"][0]["name"] if track.get("artists") else "Unknown"

                    try:
                        query = f"{track_name} {artist_name}"
                        ydl_opts = {
                            "format": "bestaudio/best",
                            "postprocessors": [
                                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                                {"key": "FFmpegMetadata"},
                            ],
                            "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
                            "quiet": True,
                            "no_warnings": True,
                            "writethumbnail": True,
                            "embedthumbnail": True,
                        }
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(f"ytsearch:{query}", download=True)["entries"][0]
                            base = ydl.prepare_filename(info).replace(".webm", "").replace(".m4a", "")
                            mp3_path = f"{base}.mp3"
                            if os.path.exists(mp3_path):
                                downloaded.append(mp3_path)
                    except Exception as e:
                        print(f"Failed to download {track_name}: {e}")
                        continue

            elif track_id:
                track_id = track_id.group(1)
                # Fetch single track via raw request
                headers = {"Authorization": f"Bearer {access_token}"}
                resp = requests.get(f"https://api.spotify.com/v1/tracks/{track_id}", headers=headers)
                if resp.status_code != 200:
                    return jsonify({"error": f"Failed to get track: {resp.text}"}), 500
                track = resp.json()
                track_name = track["name"]
                artist_name = track["artists"][0]["name"]

                try:
                    query = f"{track_name} {artist_name}"
                    ydl_opts = {
                        "format": "bestaudio/best",
                        "postprocessors": [
                            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                            {"key": "FFmpegMetadata"},
                        ],
                        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
                        "quiet": True,
                        "no_warnings": True,
                        "writethumbnail": True,
                        "embedthumbnail": True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"ytsearch:{query}", download=True)["entries"][0]
                        base = ydl.prepare_filename(info).replace(".webm", "").replace(".m4a", "")
                        mp3_path = f"{base}.mp3"
                        if os.path.exists(mp3_path):
                            downloaded.append(mp3_path)
                except Exception as e:
                    print(f"Failed to download {track_name}: {e}")

            if not downloaded:
                return jsonify({"error": "No songs could be downloaded. Make sure the playlist contains playable tracks."}), 500

            zip_path = os.path.join(temp_dir, "playlist.zip")
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for f in downloaded:
                    zipf.write(f, os.path.basename(f))

            return send_file(zip_path, as_attachment=True, download_name="playlist.zip", mimetype="application/zip")

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
