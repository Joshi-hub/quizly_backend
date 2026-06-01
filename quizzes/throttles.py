from rest_framework.throttling import UserRateThrottle


class QuizCreateThrottle(UserRateThrottle):
    """Limits quiz generation to settings.DEFAULT_THROTTLE_RATES['quiz_create'] per user."""
    scope = 'quiz_create'
