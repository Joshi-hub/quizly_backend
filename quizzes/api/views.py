import re

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from ..models import Quiz, Question
from .serializers import QuizSerializer
from ..services.quiz_service import generate_quiz

_VIDEO_ID_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/)|youtu\.be/)([0-9A-Za-z_-]{11})'
)


def _extract_video_id(url):
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


class QuizDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _resolve_quiz(self, pk, user):
        try:
            quiz = Quiz.objects.prefetch_related('questions').get(pk=pk)
        except Quiz.DoesNotExist:
            return None, Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if quiz.user != user:
            return None, Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
        return quiz, None

    def get(self, request, pk):
        quiz, error = self._resolve_quiz(pk, request.user)
        if error:
            return error
        return Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)

class QuizCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        quizzes = Quiz.objects.filter(user=request.user).prefetch_related('questions')
        return Response(QuizSerializer(quizzes, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        url = request.data.get('url', '').strip()
        if not url:
            return Response({'detail': 'URL is required.'}, status=status.HTTP_400_BAD_REQUEST)

        video_id = _extract_video_id(url)
        if not video_id:
            return Response({'detail': 'Invalid YouTube URL.'}, status=status.HTTP_400_BAD_REQUEST)

        if not settings.GEMINI_API_KEY:
            return Response({'detail': 'GEMINI_API_KEY is not configured.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        canonical_url = f'https://www.youtube.com/watch?v={video_id}'

        try:
            data = generate_quiz(canonical_url, settings.GEMINI_API_KEY)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        quiz = Quiz.objects.create(
            user=request.user,
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

        return Response(QuizSerializer(quiz).data, status=status.HTTP_201_CREATED)
