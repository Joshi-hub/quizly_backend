import re

_VIDEO_ID_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/)|youtu\.be/)([0-9A-Za-z_-]{11})'
)


def extract_video_id(url):
    """Extracts the 11-character video ID from any YouTube URL format."""
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def build_canonical_url(video_id):
    """Returns the canonical watch URL for a given YouTube video ID."""
    return f'https://www.youtube.com/watch?v={video_id}'
