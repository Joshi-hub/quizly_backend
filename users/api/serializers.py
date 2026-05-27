from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    confirmed_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'confirmed_password']
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, data):
        if data['password'] != data['confirmed_password']:
            raise serializers.ValidationError({'confirmed_password': 'Passwords do not match.'})
        return data

    def create(self, validated_data):
        validated_data.pop('confirmed_password')
        return User.objects.create_user(**validated_data)