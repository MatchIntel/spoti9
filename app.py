import os
import re
import zipfile
import tempfile
from flask import Flask, request, render_template_string, send_file, jsonify
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp

app = Flask(__name__)

# Spotify credentials from environment variables
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

# Initialize Spotify client
client_credentials_manager = SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET
)
sp = Spotify(client_credentials_manager=client_credentials_manager)

# -------------------- HTML TEMPLATE (embedded) --------------------
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
        .form-control { border-radius: 50px; padding: 14px 20px; border: 2px solid #ddd; font-size: 16px; }
        .form-control:focus { border-color: #1db954; box-shadow: 0 0 0 0.2rem rgba(29,185,84,0.25); }
        .info-text { color: #888; font-size: 14px; margin-top: 15px; text-align: center; }
        .alert { border-radius: 12px; margin-top: 15px; }
        .loading { display: none; text-align: center; margin-top: 20px; }
        .spinner-border { width: 3rem; height: 3rem; color: #1db954; }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">
            <h1>🎵 Spotify Downloader</h1>
            <p>Download playlists or tracks as MP3</p>
        </div>
        <form id="downloadForm">
            <div class="mb-3">
                <label for="urlInput" class="form-label fw-semibold">Enter Spotify URL</label>
                <input type="url" class="form-control" id="urlInput" placeholder="https://open.spotify.com/playlist/..." required />
                <div class="form-text">Supports playlists and individual tracks.</div>
            </div>
            <div class="d-grid">
                <button type="submit" class="btn btn-spotify" id="downloadBtn">⬇️ Download</button>
            </div>
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
# ------------------------------------------------------------------

def extract_playlist_id(url):
    match = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None

def extract_track_id(url):
    match = re.search(r"track/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None

def get_playlist_tracks(playlist_id):
    results = sp.playlist_tracks(playlist_id)
    tracks = results["items"]
    while results["next"]:
        results = sp.next(results)
        tracks.extend(results["items"])
    return tracks

def get_track_info(track_id):
    track = sp.track(track_id)
    return {
        "name": track["name"],
        "artists": [artist["name"] for artist in track["artists"]],
        "album": track["album"]["name"],
        "cover_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
    }

def download_track(track_name, artist_name, album_name, cover_art_url, output_dir):
    query = f"{track_name} {artist_name}"
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
            {"key": "FFmpegMetadata"},
        ],
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "writethumbnail": True,
        "embedthumbnail": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)["entries"][0]
            base = ydl.prepare_filename(info).replace(".webm", "").replace(".m4a", "")
            return f"{base}.mp3"
        except Exception as e:
            print(f"Failed: {track_name} - {e}")
            return None

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    playlist_id = extract_playlist_id(url)
    track_id = extract_track_id(url)
    if not playlist_id and not track_id:
        return jsonify({"error": "Invalid Spotify URL"}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        downloaded = []

        if playlist_id:
            for item in get_playlist_tracks(playlist_id):
                track = item.get("track")
                if not track:
                    continue
                info = {
                    "name": track["name"],
                    "artist": track["artists"][0]["name"],
                    "album": track["album"]["name"],
                    "cover": track["album"]["images"][0]["url"] if track["album"]["images"] else None,
                }
                mp3 = download_track(info["name"], info["artist"], info["album"], info["cover"], temp_dir)
                if mp3 and os.path.exists(mp3):
                    downloaded.append(mp3)
        elif track_id:
            info = get_track_info(track_id)
            mp3 = download_track(info["name"], info["artists"][0], info["album"], info["cover_art"], temp_dir)
            if mp3 and os.path.exists(mp3):
                downloaded.append(mp3)

        if not downloaded:
            return jsonify({"error": "No songs could be downloaded"}), 500

        zip_path = os.path.join(temp_dir, "playlist.zip")
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for f in downloaded:
                zipf.write(f, os.path.basename(f))

        return send_file(zip_path, as_attachment=True, download_name="playlist.zip", mimetype="application/zip")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
