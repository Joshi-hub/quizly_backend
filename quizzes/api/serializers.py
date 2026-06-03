from rest_framework import serializers
from ..models import Quiz, Question


class QuestionSerializer(serializers.ModelSerializer):
    """Serializes a single question with all fields including timestamps."""

    class Meta:
        model = Question
        fields = ['id', 'question_title', 'question_options', 'answer', 'created_at', 'updated_at']


class QuizSerializer(serializers.ModelSerializer):
    """Serializes a Quiz with its nested questions; video_url and timestamps are read-only."""

    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ['id', 'title', 'description', 'created_at', 'updated_at', 'video_url', 'questions']
        read_only_fields = ['id', 'video_url', 'created_at', 'updated_at']
