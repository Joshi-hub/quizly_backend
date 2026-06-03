import json
import os
import re
import shutil
import tempfile

import yt_dlp
from django.conf import settings
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi

_QUIZ_PROMPT = """\
Based on the following transcript, generate a quiz in valid JSON format.

The quiz must follow this exact structure:

{
  "title": "Create a concise quiz title based on the topic of the transcript.",
  "description": "Summarize the transcript in no more than 150 characters. Do not include any quiz questions or answers.",
  "questions": [
    {
      "question_title": "The question goes here.",
      "question_options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "The correct answer from the above options"
    }
  ]
}

Requirements:
- Each question must have exactly 4 distinct answer options.
- Only one correct answer is allowed per question, and it must be present in 'question_options'.
- The output must be valid JSON and parsable as-is (e.g., using Python's json.loads).
- Do not include explanations, comments, or any text outside the JSON.
- Exactly 10 questions.

Transcript:
"""


def _strip_markdown(text):
    """Removes markdown code fences from a string."""
    text = re.sub(r'^```(?:json)?\s*\n?', '', text.strip())
    return re.sub(r'\n?```\s*$', '', text).strip()


def _extract_video_id(canonical_url):
    """Extracts the 11-character video ID from a canonical YouTube watch URL."""
    match = re.search(r'[?&]v=([0-9A-Za-z_-]{11})', canonical_url)
    return match.group(1) if match else None


def _get_transcript_via_api(video_id):
    """Fetches the YouTube transcript using the Transcript API (no FFmpeg required).

    Tries a direct fetch first, then searches available languages as fallback.
    Raises ValueError if no transcript is available for this video.
    """
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id)
        return ' '.join(snippet.text for snippet in fetched)
    except Exception:
        try:
            transcript = api.list(video_id).find_generated_transcript(['en', 'de', 'fr', 'es'])
            return ' '.join(snippet.text for snippet in transcript.fetch())
        except Exception as exc:
            raise ValueError(f'No transcript available for this video: {exc}') from exc


def _get_ydl_opts(output_path):
    """Returns yt-dlp options that extract audio and convert to mp3 via FFMPEG."""
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
        'noplaylist': True,
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
    }
    if settings.FFMPEG_LOCATION:
        opts['ffmpeg_location'] = settings.FFMPEG_LOCATION
    return opts


def _download_audio(canonical_url, tmp_base):
    """Downloads YouTube audio as mp3 using yt-dlp and FFMPEG."""
    try:
        with yt_dlp.YoutubeDL(_get_ydl_opts(tmp_base)) as ydl:
            ydl.download([canonical_url])
    except yt_dlp.utils.DownloadError as exc:
        raise ValueError(f'Could not download audio: {exc}') from exc
    audio_path = tmp_base + '.mp3'
    if not os.path.exists(audio_path):
        raise RuntimeError('Audio download produced no output file.')
    return audio_path


def _ensure_ffmpeg_in_path():
    """Adds FFMPEG_LOCATION to PATH so Whisper can find ffmpeg."""
    ffmpeg_dir = settings.FFMPEG_LOCATION
    if ffmpeg_dir and ffmpeg_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ['PATH']


def _transcribe_audio(audio_path):
    """Transcribes an audio file to text using Whisper AI (base model)."""
    import whisper
    _ensure_ffmpeg_in_path()
    model = whisper.load_model('base')
    result = model.transcribe(audio_path)
    return result['text']


def _call_gemini(transcript):
    """Sends the transcript to Gemini and returns the raw response text."""
    client = genai.Client()
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=_QUIZ_PROMPT + transcript[:8000],
    )
    return response.text


def _parse_quiz_response(raw_text):
    """Parses and returns the quiz JSON dict from Gemini's response."""
    try:
        return json.loads(_strip_markdown(raw_text))
    except json.JSONDecodeError as exc:
        raise RuntimeError('AI returned an unparseable response. Please try again.') from exc


def generate_quiz(canonical_url):
    """Generates a quiz dict from a YouTube URL.

    Strategy:
    1. Fetch transcript via YouTube Transcript API (fast, no FFmpeg needed).
    2. If no transcript is available, fall back to yt-dlp + Whisper (requires FFmpeg).
    """
    video_id = _extract_video_id(canonical_url)

    # Primary path: YouTube Transcript API (no local dependencies needed)
    if video_id:
        try:
            transcript = _get_transcript_via_api(video_id)
            raw = _call_gemini(transcript)
            return _parse_quiz_response(raw)
        except ValueError:
            pass  # No transcript available — fall through to audio download

    # Fallback: download audio and transcribe locally with Whisper
    tmpdir = tempfile.mkdtemp()
    try:
        audio_path = _download_audio(canonical_url, os.path.join(tmpdir, 'audio'))
        transcript = _transcribe_audio(audio_path)
        raw = _call_gemini(transcript)
        return _parse_quiz_response(raw)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
