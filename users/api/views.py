from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import RegisterSerializer, LoginSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'detail': 'User created successfully!'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        
        response = Response({
            "detail": "Login successfully!",
            "user": {"id": user.id, "username": user.username, "email": user.email}
        }, status=status.HTTP_200_OK)
        
        response.set_cookie('access_token', str(refresh.access_token), httponly=True, samesite='Lax')
        response.set_cookie('refresh_token', str(refresh), httponly=True, samesite='Lax')
        
        return response    


class TokenRefreshCookieView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get('refresh_token')
        if not raw_refresh:
            return Response({"detail": "Refresh token missing."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(raw_refresh)
            new_access = str(refresh.access_token)
        except TokenError:
            return Response({"detail": "Refresh token invalid or expired."}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = Response({"detail": "Token refreshed"}, status=status.HTTP_200_OK)
        response.set_cookie('access_token', new_access, httponly=True, samesite='Lax')
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
        except Exception:
            pass

        response = Response(
            {"detail": "Log-Out successfully! All Tokens will be deleted. Refresh token is now invalid."},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        return response