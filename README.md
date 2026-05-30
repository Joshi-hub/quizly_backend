# Quizly Backend

Django REST API backend for Quizly — generates quizzes from YouTube videos using Whisper AI and Google Gemini.

## How It Works

1. User submits a YouTube URL
2. **yt-dlp** downloads the video audio and converts it to mp3 via **FFMPEG**
3. **Whisper AI** transcribes the audio locally
4. **Gemini Flash** generates 10 multiple-choice questions from the transcript
5. The quiz is saved to the database and returned to the frontend

## Prerequisites

### 1. FFMPEG (required)
FFMPEG must be installed globally on your system.

**Windows (winget):**
```bash
winget install --id Gyan.FFmpeg -e
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

Verify installation:
```bash
ffmpeg -version
```

### 2. Python 3.10+

### 3. Gemini API Key
Get a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey).

---

## Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd quizly-backend

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY

# 5. Apply migrations
python manage.py migrate

# 6. Create admin user
python manage.py createsuperuser

# 7. Start the server
python manage.py runserver
```

---

## Environment Variables

Create a `.env` file in the project root:

```
GEMINI_API_KEY=AIzaSy...your_key_here
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/register/` | Register new user | No |
| POST | `/api/login/` | Login, sets JWT cookies | No |
| POST | `/api/logout/` | Logout, clears cookies | Yes |
| POST | `/api/token/refresh/` | Refresh access token | Cookie |

### Quiz Management
| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/quizzes/` | List all user quizzes | Yes |
| POST | `/api/quizzes/` | Create quiz from YouTube URL | Yes |
| GET | `/api/quizzes/{id}/` | Get single quiz | Yes |
| PATCH | `/api/quizzes/{id}/` | Update title/description | Yes |
| DELETE | `/api/quizzes/{id}/` | Delete quiz permanently | Yes |

---

## Authentication

JWT tokens are stored as **HTTP-only cookies** (`access_token`, `refresh_token`).
All requests to protected endpoints must include `credentials: 'include'`.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Django 5.1 + Django REST Framework |
| Auth | JWT via `djangorestframework-simplejwt` |
| Audio download | yt-dlp |
| Audio conversion | FFMPEG |
| Transcription | Whisper AI (local, `base` model) |
| Quiz generation | Google Gemini 2.0 Flash |
| Database | SQLite (development) |

---

## Admin Panel

Access at `http://127.0.0.1:8000/admin/`

- View, edit, and delete quizzes
- Edit individual quiz questions inline
- Filter by user and creation date
