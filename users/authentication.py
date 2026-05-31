from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CookieJWTAuthentication(JWTAuthentication):
    """Reads the JWT access token from the access_token HTTP-only cookie."""

    def authenticate(self, request):
        """Returns (user, token) from cookie, or None if absent or invalid."""
        raw_token = request.COOKIES.get('access_token')
        if raw_token is None:
            return None
        try:
            validated_token = self.get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            return None
        return self.get_user(validated_token), validated_token
