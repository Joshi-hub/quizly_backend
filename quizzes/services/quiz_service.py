import glob
import json
import os
import re
import shutil
import tempfile
import time

import yt_dlp
from google import genai

_QUIZ_PROMPT = (
    "Based on the following audio, generate a quiz in valid JSON format.\n\n"
    "The quiz must follow this exact structure:\n\n"
    "{\n"
    '  "title": "Create a concise quiz title based on the topic of the audio.",\n'
    '  "description": "Summarize the content in no more than 150 characters. Do not include any quiz questions or answers.",\n'
    '  "questions": [\n'
    "    {\n"
    '      "question_title": "The question goes here.",\n'
    '      "question_options": ["Option A", "Option B", "Option C", "Option D"],\n'
    '      "answer": "The correct answer from the above options"\n'
    "    },\n"
    "    ...\n"
    "    (exactly 10 questions)\n"
    "  ]\n"
    "}\n\n"
    "Requirements:\n"
    "- Each question must have exactly 4 distinct answer options.\n"
    "- Only one correct answer is allowed per question, and it must be present in 'question_options'.\n"
    "- The output must be valid JSON and parsable as-is (e.g., using Python's json.loads).\n"
    "- Do not include explanations, comments, or any text outside the JSON."
)


def _strip_markdown(text):
    text = re.sub(r'^```(?:json)?\s*\n?', '', text.strip())
    text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def generate_quiz(canonical_url, api_key):
    """
    Downloads audio from a YouTube URL, uploads it to the Gemini Files API,
    generates a quiz and returns the parsed JSON data as a dict.

    Raises:
        ValueError  – caller error (unavailable video, download failed)
        RuntimeError – server error (Gemini processing/parse failure)
    """
    tmpdir = tempfile.mkdtemp()
    tmp_base = os.path.join(tmpdir, 'audio')
    client = genai.Client(api_key=api_key)
    gemini_file = None

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': tmp_base,
            'quiet': True,
            'noplaylist': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([canonical_url])
        except yt_dlp.utils.DownloadError as exc:
            raise ValueError(f'Could not download audio: {exc}') from exc

        downloaded = glob.glob(f'{tmp_base}.*')
        if not downloaded:
            raise RuntimeError('Audio download produced no output file.')
        audio_path = downloaded[0]

        gemini_file = client.files.upload(file=audio_path)

        while gemini_file.state.name == 'PROCESSING':
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == 'FAILED':
            raise RuntimeError('Gemini failed to process the audio file.')

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[gemini_file, _QUIZ_PROMPT],
        )

        try:
            return json.loads(_strip_markdown(response.text))
        except json.JSONDecodeError as exc:
            raise RuntimeError('AI returned an unparseable response. Please try again.') from exc

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
            except Exception:
                pass
