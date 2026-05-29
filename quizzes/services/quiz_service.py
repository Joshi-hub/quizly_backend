import json
import os
import re
import shutil
import tempfile

import whisper
import yt_dlp
from django.conf import settings
from google import genai

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
    """Downloads YouTube audio, transcribes with Whisper, generates quiz with Gemini.

    Raises:
        ValueError  – caller error (download failed, video unavailable)
        RuntimeError – server error (Gemini failure, parse error)
    """
    tmpdir = tempfile.mkdtemp()
    tmp_base = os.path.join(tmpdir, 'audio')
    try:
        audio_path = _download_audio(canonical_url, tmp_base)
        transcript = _transcribe_audio(audio_path)
        raw = _call_gemini(transcript)
        return _parse_quiz_response(raw)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
