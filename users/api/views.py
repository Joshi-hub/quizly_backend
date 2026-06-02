from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import RegisterSerializer, LoginSerializer


class RegisterView(APIView):
    """Registers a new user account."""

    permission_classes = [AllowAny]

    def post(self, request):
        """Validates and saves a new user, returns 201 on success."""
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'detail': 'User created successfully!'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """Authenticates a user and sets JWT cookies."""

    permission_classes = [AllowAny]

    def post(self, request):
        """Validates credentials and sets access_token and refresh_token cookies."""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        response = Response({
            'detail': 'Login successfully!',
            'user': {'id': user.id, 'username': user.username, 'email': user.email},
        }, status=status.HTTP_200_OK)
        response.set_cookie('access_token', str(refresh.access_token), httponly=True, samesite='Lax')
        response.set_cookie('refresh_token', str(refresh), httponly=True, samesite='Lax')
        return response


class TokenRefreshCookieView(APIView):
    """Issues a new access token using the refresh token cookie."""

    permission_classes = [AllowAny]

    def post(self, request):
        """Reads refresh_token cookie and returns a new access_token cookie."""
        raw_refresh = request.COOKIES.get('refresh_token')
        if not raw_refresh:
            return Response({'detail': 'Refresh token missing.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            new_access = str(RefreshToken(raw_refresh).access_token)
        except TokenError:
            return Response({'detail': 'Refresh token invalid or expired.'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        response = Response({'detail': 'Token refreshed'}, status=status.HTTP_200_OK)
        response.set_cookie('access_token', new_access, httponly=True, samesite='Lax')
        return response


class LogoutView(APIView):
    """Logs out the user, blacklists the refresh token and clears cookies."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Blacklists the refresh token and deletes both JWT cookies."""
        try:
            RefreshToken(request.COOKIES.get('refresh_token')).blacklist()
        except Exception:
            pass
        response = Response(
            {'detail': 'Log-Out successfully! Refresh token is now invalid.'},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        return response
