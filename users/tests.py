from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class RegisterViewTests(APITestCase):
    URL = '/api/register/'

    def test_success(self):
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'StrongPass123!',
            'confirmed_password': 'StrongPass123!',
        }
        response = self.client.post(self.URL, data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['detail'], 'User created successfully!')
        self.assertTrue(User.objects.filter(username='testuser').exists())

    def test_passwords_dont_match(self):
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'StrongPass123!',
            'confirmed_password': 'Different456!',
        }
        response = self.client.post(self.URL, data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('confirmed_password', response.data)

    def test_duplicate_username(self):
        User.objects.create_user(username='testuser', email='a@example.com', password='Pass123!')
        data = {
            'username': 'testuser',
            'email': 'b@example.com',
            'password': 'Pass123!',
            'confirmed_password': 'Pass123!',
        }
        response = self.client.post(self.URL, data)
        self.assertEqual(response.status_code, 400)

    def test_missing_fields(self):
        response = self.client.post(self.URL, {})
        self.assertEqual(response.status_code, 400)

    def test_user_not_created_on_validation_error(self):
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'abc',
            'confirmed_password': 'xyz',
        }
        self.client.post(self.URL, data)
        self.assertFalse(User.objects.filter(username='testuser').exists())


class LoginViewTests(APITestCase):
    URL = '/api/login/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='StrongPass123!'
        )

    def test_success(self):
        response = self.client.post(self.URL, {'username': 'testuser', 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['detail'], 'Login successfully!')
        self.assertEqual(response.data['user']['username'], 'testuser')
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)

    def test_cookies_are_httponly(self):
        response = self.client.post(self.URL, {'username': 'testuser', 'password': 'StrongPass123!'})
        self.assertTrue(response.cookies['access_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['httponly'])

    def test_wrong_password(self):
        response = self.client.post(self.URL, {'username': 'testuser', 'password': 'WrongPass!'})
        self.assertEqual(response.status_code, 401)

    def test_unknown_user(self):
        response = self.client.post(self.URL, {'username': 'nobody', 'password': 'Pass123!'})
        self.assertEqual(response.status_code, 401)

    def test_missing_fields(self):
        response = self.client.post(self.URL, {})
        self.assertEqual(response.status_code, 400)


class LogoutViewTests(APITestCase):
    URL = '/api/logout/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='StrongPass123!'
        )

    def _authenticate(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies['refresh_token'] = str(refresh)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        return refresh

    def test_success(self):
        self._authenticate()
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Log-Out successfully', response.data['detail'])

    def test_cookies_are_cleared(self):
        self._authenticate()
        response = self.client.post(self.URL)
        self.assertEqual(response.cookies['access_token'].value, '')
        self.assertEqual(response.cookies['refresh_token'].value, '')

    def test_refresh_token_is_blacklisted(self):
        refresh = self._authenticate()
        self.client.post(self.URL)
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=refresh['jti']).exists()
        )

    def test_unauthenticated(self):
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, 401)


class TokenRefreshViewTests(APITestCase):
    URL = '/api/token/refresh/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='StrongPass123!'
        )

    def test_success(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies['refresh_token'] = str(refresh)
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['detail'], 'Token refreshed')

    def test_new_access_token_cookie_is_set(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies['refresh_token'] = str(refresh)
        response = self.client.post(self.URL)
        self.assertIn('access_token', response.cookies)
        self.assertTrue(len(response.cookies['access_token'].value) > 0)

    def test_new_cookie_is_httponly(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies['refresh_token'] = str(refresh)
        response = self.client.post(self.URL)
        self.assertTrue(response.cookies['access_token']['httponly'])

    def test_missing_cookie(self):
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, 401)

    def test_invalid_token(self):
        self.client.cookies['refresh_token'] = 'invalid.token.value'
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, 401)

    def test_blacklisted_token(self):
        refresh = RefreshToken.for_user(self.user)
        refresh.blacklist()
        self.client.cookies['refresh_token'] = str(refresh)
        response = self.client.post(self.URL)
        self.assertEqual(response.status_code, 401)