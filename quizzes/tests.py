import json
from unittest.mock import patch

import yt_dlp
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from quizzes.models import Quiz, Question
from quizzes.utils import extract_video_id, build_canonical_url
from quizzes.services.quiz_service import (
    _strip_markdown,
    _parse_quiz_response,
    _download_audio,
    generate_quiz,
)

User = get_user_model()

QUIZ_LIST_URL = '/api/quizzes/'
QUIZ_DETAIL_URL = '/api/quizzes/{}/'

SAMPLE_QUIZ_DATA = {
    'title': 'Test Quiz',
    'description': 'A quiz about testing.',
    'questions': [
        {
            'question_title': f'Question {i}',
            'question_options': ['A', 'B', 'C', 'D'],
            'answer': 'A',
        }
        for i in range(10)
    ],
}


def _authenticate(client, user):
    """Sets a valid access_token cookie on the test client."""
    refresh = RefreshToken.for_user(user)
    client.cookies['access_token'] = str(refresh.access_token)
    return refresh


def _make_quiz(user, title='My Quiz', n_questions=3):
    """Creates a Quiz with n_questions Questions for the given user."""
    quiz = Quiz.objects.create(
        user=user,
        title=title,
        description='A description.',
        video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    )
    for i in range(n_questions):
        Question.objects.create(
            quiz=quiz,
            question_title=f'Q{i + 1}',
            question_options=['A', 'B', 'C', 'D'],
            answer='A',
        )
    return quiz


# ---------------------------------------------------------------------------
# Utils – extract_video_id
# ---------------------------------------------------------------------------

class ExtractVideoIdTests(APITestCase):

    def test_standard_watch_url(self):
        self.assertEqual(extract_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), 'dQw4w9WgXcQ')

    def test_watch_url_with_extra_params(self):
        self.assertEqual(
            extract_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30&list=PL'),
            'dQw4w9WgXcQ',
        )

    def test_shorts_url(self):
        self.assertEqual(extract_video_id('https://www.youtube.com/shorts/dQw4w9WgXcQ'), 'dQw4w9WgXcQ')

    def test_youtu_be_url(self):
        self.assertEqual(extract_video_id('https://youtu.be/dQw4w9WgXcQ'), 'dQw4w9WgXcQ')

    def test_embed_url(self):
        self.assertEqual(extract_video_id('https://www.youtube.com/embed/dQw4w9WgXcQ'), 'dQw4w9WgXcQ')

    def test_invalid_url_returns_none(self):
        self.assertIsNone(extract_video_id('https://www.google.com'))

    def test_random_string_returns_none(self):
        self.assertIsNone(extract_video_id('not a url at all'))

    def test_empty_string_returns_none(self):
        self.assertIsNone(extract_video_id(''))

    def test_too_short_video_id_returns_none(self):
        self.assertIsNone(extract_video_id('https://youtu.be/short'))


# ---------------------------------------------------------------------------
# Utils – build_canonical_url
# ---------------------------------------------------------------------------

class BuildCanonicalUrlTests(APITestCase):

    def test_returns_watch_url_format(self):
        self.assertEqual(
            build_canonical_url('dQw4w9WgXcQ'),
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        )

    def test_video_id_is_embedded(self):
        result = build_canonical_url('abc12345678')
        self.assertTrue(result.startswith('https://www.youtube.com/watch?v='))
        self.assertIn('abc12345678', result)


# ---------------------------------------------------------------------------
# GET /api/quizzes/
# ---------------------------------------------------------------------------

class QuizListViewTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Pass123!')
        self.other = User.objects.create_user(username='bob', password='Pass123!')

    def test_returns_own_quizzes(self):
        _make_quiz(self.user)
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_returns_empty_list_when_no_quizzes(self):
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_excludes_other_users_quizzes(self):
        _make_quiz(self.other)
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_LIST_URL)
        self.assertEqual(len(response.data), 0)

    def test_returns_multiple_own_quizzes(self):
        _make_quiz(self.user, title='A')
        _make_quiz(self.user, title='B')
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_LIST_URL)
        self.assertEqual(len(response.data), 2)

    def test_response_includes_nested_questions(self):
        _make_quiz(self.user, n_questions=4)
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_LIST_URL)
        self.assertEqual(len(response.data[0]['questions']), 4)

    def test_unauthenticated_returns_401(self):
        response = self.client.get(QUIZ_LIST_URL)
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# POST /api/quizzes/
# ---------------------------------------------------------------------------

class QuizCreateViewTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Pass123!')
        _authenticate(self.client, self.user)

    def test_missing_url_field_returns_400(self):
        response = self.client.post(QUIZ_LIST_URL, {})
        self.assertEqual(response.status_code, 400)
        self.assertIn('URL is required', response.data['detail'])

    def test_whitespace_only_url_returns_400(self):
        response = self.client.post(QUIZ_LIST_URL, {'url': '   '})
        self.assertEqual(response.status_code, 400)
        self.assertIn('URL is required', response.data['detail'])

    def test_non_youtube_url_returns_400(self):
        response = self.client.post(QUIZ_LIST_URL, {'url': 'https://www.google.com'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid YouTube URL', response.data['detail'])

    def test_random_string_url_returns_400(self):
        response = self.client.post(QUIZ_LIST_URL, {'url': 'not-a-url'})
        self.assertEqual(response.status_code, 400)

    @override_settings(GEMINI_API_KEY='')
    def test_missing_gemini_key_returns_500(self):
        response = self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertEqual(response.status_code, 500)
        self.assertIn('GEMINI_API_KEY', response.data['detail'])

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', side_effect=ValueError('Video unavailable'))
    def test_download_failure_returns_400(self, _mock):
        response = self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Video unavailable', response.data['detail'])

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', side_effect=RuntimeError('AI parse error'))
    def test_gemini_failure_returns_500(self, _mock):
        response = self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertEqual(response.status_code, 500)
        self.assertIn('AI parse error', response.data['detail'])

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', return_value=SAMPLE_QUIZ_DATA)
    def test_successful_creation_returns_201(self, _mock):
        response = self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertEqual(response.status_code, 201)

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', return_value=SAMPLE_QUIZ_DATA)
    def test_quiz_is_saved_to_db(self, _mock):
        self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertTrue(Quiz.objects.filter(user=self.user).exists())

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', return_value=SAMPLE_QUIZ_DATA)
    def test_ten_questions_are_saved(self, _mock):
        self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        quiz = Quiz.objects.get(user=self.user)
        self.assertEqual(quiz.questions.count(), 10)

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', return_value=SAMPLE_QUIZ_DATA)
    def test_url_normalised_to_canonical(self, _mock):
        self.client.post(QUIZ_LIST_URL, {'url': 'https://www.youtube.com/shorts/dQw4w9WgXcQ'})
        quiz = Quiz.objects.get(user=self.user)
        self.assertEqual(quiz.video_url, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    @override_settings(GEMINI_API_KEY='test-key')
    @patch('quizzes.api.views.generate_quiz', return_value=SAMPLE_QUIZ_DATA)
    def test_quiz_is_assigned_to_authenticated_user(self, _mock):
        self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        quiz = Quiz.objects.get(title='Test Quiz')
        self.assertEqual(quiz.user, self.user)

    def test_unauthenticated_returns_401(self):
        self.client.cookies.clear()
        response = self.client.post(QUIZ_LIST_URL, {'url': 'https://youtu.be/dQw4w9WgXcQ'})
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# GET /api/quizzes/<id>/
# ---------------------------------------------------------------------------

class QuizDetailGetTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Pass123!')
        self.other = User.objects.create_user(username='bob', password='Pass123!')
        self.quiz = _make_quiz(self.user)

    def test_returns_own_quiz_with_200(self):
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.quiz.pk)

    def test_response_includes_nested_questions(self):
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertIn('questions', response.data)
        self.assertEqual(len(response.data['questions']), 3)

    def test_other_users_quiz_returns_403(self):
        _authenticate(self.client, self.other)
        response = self.client.get(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_quiz_returns_404(self):
        _authenticate(self.client, self.user)
        response = self.client.get(QUIZ_DETAIL_URL.format(9999))
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401(self):
        response = self.client.get(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# PATCH /api/quizzes/<id>/
# ---------------------------------------------------------------------------

class QuizDetailPatchTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Pass123!')
        self.other = User.objects.create_user(username='bob', password='Pass123!')
        self.quiz = _make_quiz(self.user)
        _authenticate(self.client, self.user)

    def test_patch_title_returns_200(self):
        response = self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk), {'title': 'New Title'}, format='json'
        )
        self.assertEqual(response.status_code, 200)

    def test_patch_title_updates_db(self):
        self.client.patch(QUIZ_DETAIL_URL.format(self.quiz.pk), {'title': 'Updated'}, format='json')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, 'Updated')

    def test_patch_description_updates_db(self):
        self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk), {'description': 'New desc'}, format='json'
        )
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.description, 'New desc')

    def test_patch_title_and_description_together(self):
        self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk),
            {'title': 'T', 'description': 'D'},
            format='json',
        )
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, 'T')
        self.assertEqual(self.quiz.description, 'D')

    def test_video_url_is_read_only(self):
        original = self.quiz.video_url
        self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk),
            {'video_url': 'https://www.youtube.com/watch?v=aaaaaaaaaaa'},
            format='json',
        )
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.video_url, original)

    def test_questions_preserved_after_patch(self):
        response = self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk), {'title': 'X'}, format='json'
        )
        self.assertEqual(len(response.data['questions']), 3)

    def test_other_users_quiz_returns_403(self):
        _authenticate(self.client, self.other)
        response = self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk), {'title': 'Hack'}, format='json'
        )
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_quiz_returns_404(self):
        response = self.client.patch(QUIZ_DETAIL_URL.format(9999), {'title': 'X'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401(self):
        self.client.cookies.clear()
        response = self.client.patch(
            QUIZ_DETAIL_URL.format(self.quiz.pk), {'title': 'X'}, format='json'
        )
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# DELETE /api/quizzes/<id>/
# ---------------------------------------------------------------------------

class QuizDetailDeleteTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='Pass123!')
        self.other = User.objects.create_user(username='bob', password='Pass123!')
        self.quiz = _make_quiz(self.user)
        _authenticate(self.client, self.user)

    def test_delete_own_quiz_returns_204(self):
        response = self.client.delete(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertEqual(response.status_code, 204)

    def test_quiz_removed_from_db_after_delete(self):
        self.client.delete(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertFalse(Quiz.objects.filter(pk=self.quiz.pk).exists())

    def test_questions_cascade_deleted(self):
        question_ids = list(self.quiz.questions.values_list('id', flat=True))
        self.client.delete(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertFalse(Question.objects.filter(id__in=question_ids).exists())

    def test_other_users_quiz_returns_403(self):
        _authenticate(self.client, self.other)
        response = self.client.delete(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_delete_quiz(self):
        _authenticate(self.client, self.other)
        self.client.delete(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertTrue(Quiz.objects.filter(pk=self.quiz.pk).exists())

    def test_nonexistent_quiz_returns_404(self):
        response = self.client.delete(QUIZ_DETAIL_URL.format(9999))
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401(self):
        self.client.cookies.clear()
        response = self.client.delete(QUIZ_DETAIL_URL.format(self.quiz.pk))
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# Service – _strip_markdown
# ---------------------------------------------------------------------------

class StripMarkdownTests(APITestCase):

    def test_strips_json_code_fence(self):
        self.assertEqual(_strip_markdown('```json\n{"k": 1}\n```'), '{"k": 1}')

    def test_strips_plain_code_fence(self):
        self.assertEqual(_strip_markdown('```\n{"k": 1}\n```'), '{"k": 1}')

    def test_plain_json_unchanged(self):
        self.assertEqual(_strip_markdown('{"k": 1}'), '{"k": 1}')

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(_strip_markdown('  {"k": 1}  '), '{"k": 1}')


# ---------------------------------------------------------------------------
# Service – _parse_quiz_response
# ---------------------------------------------------------------------------

class ParseQuizResponseTests(APITestCase):

    def test_valid_json_returns_dict(self):
        result = _parse_quiz_response(json.dumps(SAMPLE_QUIZ_DATA))
        self.assertEqual(result['title'], 'Test Quiz')
        self.assertEqual(len(result['questions']), 10)

    def test_valid_json_inside_markdown_fence(self):
        raw = f'```json\n{json.dumps(SAMPLE_QUIZ_DATA)}\n```'
        result = _parse_quiz_response(raw)
        self.assertIn('questions', result)

    def test_invalid_json_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            _parse_quiz_response('not valid json {{{')

    def test_empty_string_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            _parse_quiz_response('')


# ---------------------------------------------------------------------------
# Service – _download_audio
# ---------------------------------------------------------------------------

class DownloadAudioTests(APITestCase):

    @patch('quizzes.services.quiz_service.os.path.exists', return_value=True)
    @patch('quizzes.services.quiz_service.yt_dlp.YoutubeDL')
    def test_returns_mp3_path_on_success(self, _mock_ydl, _mock_exists):
        result = _download_audio('https://url', '/tmp/test/audio')
        self.assertEqual(result, '/tmp/test/audio.mp3')

    @patch('quizzes.services.quiz_service.yt_dlp.YoutubeDL')
    def test_raises_value_error_on_download_error(self, mock_ydl):
        mock_ydl.return_value.__enter__.return_value.download.side_effect = (
            yt_dlp.utils.DownloadError('video unavailable')
        )
        with self.assertRaises(ValueError) as ctx:
            _download_audio('https://url', '/tmp/test/audio')
        self.assertIn('Could not download audio', str(ctx.exception))

    @patch('quizzes.services.quiz_service.os.path.exists', return_value=False)
    @patch('quizzes.services.quiz_service.yt_dlp.YoutubeDL')
    def test_raises_runtime_error_when_no_output_file(self, _mock_ydl, _mock_exists):
        with self.assertRaises(RuntimeError):
            _download_audio('https://url', '/tmp/test/audio')


# ---------------------------------------------------------------------------
# Service – generate_quiz (integration with mocked helpers)
# ---------------------------------------------------------------------------

class GenerateQuizTests(APITestCase):

    @patch('quizzes.services.quiz_service.shutil.rmtree')
    @patch('quizzes.services.quiz_service._call_gemini', return_value=json.dumps(SAMPLE_QUIZ_DATA))
    @patch('quizzes.services.quiz_service._transcribe_audio', return_value='Sample transcript')
    @patch('quizzes.services.quiz_service._download_audio', return_value='/tmp/fake/audio.mp3')
    def test_returns_parsed_quiz_dict(self, _dl, _tr, _gemini, _rmtree):
        result = generate_quiz('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(result['title'], 'Test Quiz')
        self.assertEqual(len(result['questions']), 10)

    @patch('quizzes.services.quiz_service.shutil.rmtree')
    @patch('quizzes.services.quiz_service._download_audio', side_effect=ValueError('unavailable'))
    def test_propagates_value_error_from_download(self, _dl, _rmtree):
        with self.assertRaises(ValueError):
            generate_quiz('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    @patch('quizzes.services.quiz_service.shutil.rmtree')
    @patch('quizzes.services.quiz_service._call_gemini', return_value='bad json {{{')
    @patch('quizzes.services.quiz_service._transcribe_audio', return_value='transcript')
    @patch('quizzes.services.quiz_service._download_audio', return_value='/tmp/fake/audio.mp3')
    def test_propagates_runtime_error_from_parse(self, _dl, _tr, _gemini, _rmtree):
        with self.assertRaises(RuntimeError):
            generate_quiz('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    @patch('quizzes.services.quiz_service.shutil.rmtree')
    @patch('quizzes.services.quiz_service._download_audio', side_effect=ValueError('fail'))
    @patch('quizzes.services.quiz_service.tempfile.mkdtemp', return_value='/tmp/fake')
    def test_cleanup_runs_even_on_failure(self, _mkdtemp, _dl, mock_rmtree):
        try:
            generate_quiz('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        except ValueError:
            pass
        mock_rmtree.assert_called_once_with('/tmp/fake', ignore_errors=True)
