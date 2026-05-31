from django.contrib.auth import get_user_model, authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """Validates and creates a new user with password confirmation."""

    confirmed_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'confirmed_password']
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, data):
        """Ensures both password fields match."""
        if data['password'] != data['confirmed_password']:
            raise serializers.ValidationError({'confirmed_password': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        """Creates and returns a new User instance."""
        validated_data.pop('confirmed_password')
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    """Validates login credentials and returns the authenticated user."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        """Authenticates the user and raises 401 on invalid credentials."""
        user = authenticate(**data)
        if not user:
            raise AuthenticationFailed('Ungültige Anmeldedaten.')
        return {'user': user}
