from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from ..models import Quiz, Question
from ..utils import extract_video_id, build_canonical_url
from ..throttles import QuizCreateThrottle
from .serializers import QuizSerializer
from ..services.quiz_service import generate_quiz


class QuizDetailView(APIView):
    """Handles GET, PATCH and DELETE for a single quiz owned by the user."""

    permission_classes = [IsAuthenticated]

    def _resolve_quiz(self, pk, user):
        """Returns (quiz, error_response), distinguishing 404 from 403."""
        try:
            quiz = Quiz.objects.prefetch_related('questions').get(pk=pk)
        except Quiz.DoesNotExist:
            return None, Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if quiz.user != user:
            return None, Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
        return quiz, None

    def get(self, request, pk):
        """Returns a single quiz with all questions."""
        quiz, error = self._resolve_quiz(pk, request.user)
        if error:
            return error
        return Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        """Partially updates title and/or description of a quiz."""
        quiz, error = self._resolve_quiz(pk, request.user)
        if error:
            return error
        serializer = QuizSerializer(quiz, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """Permanently deletes a quiz and all its questions."""
        quiz, error = self._resolve_quiz(pk, request.user)
        if error:
            return error
        quiz.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuizListCreateView(APIView):
    """Handles GET (list) and POST (create) for the authenticated user's quizzes."""

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == 'POST':
            return [QuizCreateThrottle()]
        return super().get_throttles()

    def get(self, request):
        """Returns all quizzes belonging to the authenticated user."""
        quizzes = Quiz.objects.filter(user=request.user).prefetch_related('questions')
        return Response(QuizSerializer(quizzes, many=True).data, status=status.HTTP_200_OK)

    def _get_canonical_url(self, url):
        """Validates the URL and returns (canonical_url, error_response)."""
        if not url:
            return None, Response({'detail': 'URL is required.'}, status=status.HTTP_400_BAD_REQUEST)
        video_id = extract_video_id(url)
        if not video_id:
            return None, Response({'detail': 'Invalid YouTube URL.'}, status=status.HTTP_400_BAD_REQUEST)
        return build_canonical_url(video_id), None

    def _save_quiz(self, user, data, canonical_url):
        """Creates Quiz and Question records in the database and returns the Quiz."""
        quiz = Quiz.objects.create(
            user=user,
            title=data['title'],
            description=data['description'],
            video_url=canonical_url,
        )
        for q in data.get('questions', []):
            Question.objects.create(
                quiz=quiz,
                question_title=q['question_title'],
                question_options=q['question_options'],
                answer=q['answer'],
            )
        return quiz

    def post(self, request):
        """Creates a new quiz from a YouTube URL using Whisper and Gemini."""
        url = request.data.get('url', '').strip()
        canonical_url, error = self._get_canonical_url(url)
        if error:
            return error
        if not settings.GEMINI_API_KEY:
            return Response({'detail': 'GEMINI_API_KEY is not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        try:
            data = generate_quiz(canonical_url)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        quiz = self._save_quiz(request.user, data, canonical_url)
        return Response(QuizSerializer(quiz).data, status=status.HTTP_201_CREATED)
