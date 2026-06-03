from django.conf import settings
from django.db import models


class Quiz(models.Model):
    """Stores a generated quiz linked to a YouTube video and its owner."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quizzes',
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    video_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    """A single multiple-choice question belonging to a Quiz."""

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_title = models.TextField()
    question_options = models.JSONField()
    answer = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.question_title
