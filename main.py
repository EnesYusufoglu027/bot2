import os
import random
import asyncio
import datetime
import pickle
import subprocess

import edge_tts
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# === Ayarlar ===
BG_FOLDER = "Backgrounds"
MUSIC_FOLDER = "music"
QUOTES_FILE = "jp_quotes.txt"
UPLOADED_VIDEOS_FILE = "uploaded_videos.txt"

video_category_id = "22"  # People & Blogs
privacy_status = "public"
made_for_kids = False

video_tags = ["motivasyon", "ilham", "shorts", "türkçe", "günlük motivasyon"]
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# === YouTube API Auth ===
def authenticate_youtube():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    youtube = build("youtube", "v3", credentials=creds)
    return youtube

# === Ses üretimi ===
async def generate_voice(text, audio_path):
    communicate = edge_tts.Communicate(text, voice="tr-TR-EmelNeural")  # Kadın sesi
    await communicate.save(audio_path)

def get_audio_duration(path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    return float(subprocess.check_output(cmd).decode().strip())

# === Video oluşturma ===
def create_video(quote, timestamp):
    audio_path = f"voice_{timestamp}.mp3"
    video_path = f"video_{timestamp}.mp4"

    # Ses dosyası oluştur
    asyncio.run(generate_voice(quote, audio_path))

    # Arka plan resmi seç
    valid_image_exts = [".jpg", ".jpeg", ".png"]
    bg_images = [f for f in os.listdir(BG_FOLDER) if os.path.splitext(f)[1].lower() in valid_image_exts]
    bg_image_path = os.path.join(BG_FOLDER, random.choice(bg_images))

    # Müzik seç
    music_files = [f for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith(".mp3")]
    music_path = os.path.join(MUSIC_FOLDER, random.choice(music_files))

    # Süre hesapla
    music_duration = get_audio_duration(music_path)
    voice_duration = get_audio_duration(audio_path)
    final_duration = max(10, voice_duration)

    # Müziği rastgele başlat
    max_start = max(0, music_duration - final_duration)
    start_time = random.uniform(0, max_start)

    # Sesleri birleştir
    merged_audio_path = f"merged_audio_{timestamp}.mp3"
    subprocess.run([
        "ffmpeg",
        "-ss", str(start_time),
        "-i", music_path,
        "-i", audio_path,
        "-filter_complex",
        "[1:a]volume=1[a0];[0:a]volume=0.3[a1];[a0][a1]amix=inputs=2:duration=first",
        "-c:a", "mp3",
        "-y",
        merged_audio_path
    ], check=True)

    # Videoya yazı ekle
    text_filter = (
        f"drawtext=text='{quote}':"
        "fontcolor=white:"
        "fontsize=48:"
        "box=1:boxcolor=black@0.5:boxborderw=10:"
        "x=(w-text_w)/2:"
        "y=(h-text_h)/2:"
        "enable='between(t,0,10)',"
        "fade=t=in:st=0:d=1"
    )

    subprocess.run([
        "ffmpeg",
        "-loop", "1",
        "-i", bg_image_path,
        "-i", merged_audio_path,
        "-t", str(final_duration),
        "-vf", f"scale=1080:1920,{text_filter}",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-y",
        video_path
    ], check=True)

    # Geçici dosyaları sil
    for temp_file in [audio_path, merged_audio_path]:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    return video_path

# === Video yükleme ===
def upload_video(youtube, video_file, title, description, tags, category_id, privacy, kids_flag):
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy,
            "madeForKids": kids_flag
        }
    }

    media = MediaFileUpload(video_file)
    response = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    ).execute()

    print(f"✅ Yüklendi: https://youtube.com/watch?v={response['id']}")
    return response["id"]

# === Ana görev ===
def job():
    print("✨ Video botu çalışıyor:", datetime.datetime.now())

    with open(QUOTES_FILE, "r", encoding="utf-8") as f:
        quotes = [line.strip() for line in f if line.strip()]
    quote = random.choice(quotes)

    video_title = f"{quote} - Günlük Motivasyon #Shorts"
    video_description = (
        "Her güne ilham verici bir sözle başla!\n"
        "Kanalımıza abone olmayı unutma.\n"
        "#Shorts #Motivasyon #Türkçe"
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_file = create_video(quote, timestamp)

    try:
        youtube = authenticate_youtube()
        upload_video(
            youtube,
            video_file,
            video_title,
            video_description,
            video_tags,
            video_category_id,
            privacy_status,
            made_for_kids,
        )
    except Exception as e:
        print("❌ Video yüklenirken hata:", e)

# === Başlatıcı ===
if __name__ == "__main__":
    job()
