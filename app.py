from flask import Flask, request, render_template, jsonify
import os
from dotenv import load_dotenv
import google.generativeai as genai
from supadata import Supadata
import re
import yt_dlp
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector
from flask import Flask, request, send_file
from gtts import gTTS
from io import BytesIO
import asyncio
import edge_tts


load_dotenv()
SUPADATA_API_KEY = os.getenv("SUPADATA_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

supadata = Supadata(api_key=SUPADATA_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
app = Flask(__name__, template_folder="templates")


def fetch_transcript(video_id):
    try:
        transcript_obj = supadata.youtube.transcript(video_id=video_id, text=True, lang="en")
        return transcript_obj.content
    except Exception as e:
        print("Transcript error:", e)
        return None


def generate_detailed_notes_gemini(transcript_text):
    try:
        prompt = f"""
        You are an expert video summarizer. Based on the transcript below, generate:
        1. A detailed summary.
        2. Key points.
        3. Important insights.

        Transcript: {transcript_text}
        """
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw_notes = response.text

        # Format for HTML display
        formatted_notes = raw_notes.replace("## Detailed Summary:", "<h2>Detailed Summary</h2>")
        formatted_notes = formatted_notes.replace("## Key Points:", "<h2>Key Points</h2>")
        formatted_notes = formatted_notes.replace("## Important Insights:", "<h2>Important Insights</h2>")
        formatted_notes = re.sub(r"^\* (.+)$", r"<li>\1</li>", formatted_notes, flags=re.MULTILINE)
        # Wrap <li> in <ul>
        formatted_notes = re.sub(r"(<li>.*?</li>)", r"<ul>\1</ul>", formatted_notes)
        formatted_notes = formatted_notes.replace("\n\n", "<br><br>")

        return formatted_notes

    except Exception as e:
        print("Gemini API error:", e)
        return "Failed to generate notes. Please check API key and transcript."


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/get_notes", methods=["POST"])
def get_notes():
    data = request.json
    video_url = data.get("video_url")
    if not video_url:
        return jsonify({"notes": "No video URL provided."})

    # Extract video ID
    if "v=" in video_url:
        video_id = video_url.split("v=")[1].split("&")[0]
    else:
        video_id = video_url

    transcript = fetch_transcript(video_id)
    if not transcript:
        return jsonify({"notes": "Transcript not available yet. Please try again."})

    notes = generate_detailed_notes_gemini(transcript)
    return jsonify({"notes": notes})



@app.route("/quiz")
def quiz():
    return "Quiz page (transcript ready in backend)"


@app.route("/get_topics", methods=["POST"])
def get_topics():
    data = request.json
    video_url = data.get("video_url")
    if not video_url:
        return jsonify({"error": "No video URL provided"})

    # Extract video ID
    if "v=" in video_url:
        video_id = video_url.split("v=")[1].split("&")[0]
    else:
        video_id = video_url

    # Fetch transcript
    try:
        transcript_obj = supadata.youtube.transcript(video_id=video_id, text=True, lang="en")
        transcript = transcript_obj.content

        segments = []
        if hasattr(transcript_obj, "segments"):
            for s in transcript_obj.segments:
                start_sec = s.start.total_seconds()
                end_sec = s.end.total_seconds()
                segments.append({"start": start_sec, "end": end_sec})
        else:
            segments.append({"start": 0, "end": 0})
    except Exception as e:
        print("Transcript error:", e)
        return jsonify({"error": "Transcript not available."})

    # Generate topics using Gemini
    try:
        prompt = f"""
        You are an expert video segmenter. 
        Based on the transcript below and segment timestamps, divide the video into meaningful topics.
        Return ONLY a JSON array of objects with keys:
        "topic" (string), "start_time" (seconds), "end_time" (seconds).

        Transcript: {transcript}
        Segments: {segments}
        """
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        import json
        try:
            topics = json.loads(raw_text)
        except:
            start = raw_text.find("[")
            end = raw_text.rfind("]")+1
            topics = json.loads(raw_text[start:end])
    except Exception as e:
        print("Gemini API error:", e)
        topics = []

    return jsonify({"topics": topics})

@app.route("/tts", methods=["GET"])
def tts_edge():
    text = request.args.get("text", "")
    if not text:
        return "No text provided", 400

    async def generate_audio():
        communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
        audio_fp = BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_fp.write(chunk["data"])
        audio_fp.seek(0)
        return audio_fp

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    audio_fp = loop.run_until_complete(generate_audio())
    loop.close()

    return send_file(audio_fp, mimetype="audio/wav")


if __name__ == "__main__":
    app.run(debug=True)
