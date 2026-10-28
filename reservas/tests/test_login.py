from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LoginNextTests(TestCase):
    def setUp(self):
        User.objects.create_user(username='ana', password='clave-segura-123')

    def login(self, next_url):
        return self.client.post(f"{reverse('login')}?next={next_url}",
                                {'username': 'ana', 'password': 'clave-segura-123'})

    def test_login_redirige_a_next(self):
        """Tras iniciar sesión se vuelve a la página indicada en ?next= (p. ej. Mis reservas)."""
        response = self.login(reverse('mis_reservas'))
        self.assertRedirects(response, reverse('mis_reservas'), fetch_redirect_response=False)

    def test_login_ignora_next_externo(self):
        """Un ?next= a otro dominio se ignora y se redirige al inicio (evita redirecciones abiertas)."""
        response = self.login('https://sitio-malicioso.example/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)
