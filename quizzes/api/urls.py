from django.urls import path
from .views import QuizCreateView, QuizDetailView

urlpatterns = [
    path('quizzes/', QuizCreateView.as_view(), name='quiz-list-create'),
    path('quizzes/<int:pk>/', QuizDetailView.as_view(), name='quiz-detail'),
]
