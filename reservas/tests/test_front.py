from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from reservas.models import Resource


class PlantillaBaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.resource = Resource.objects.create(name='Pista 1')

    def test_paginas_usan_la_plantilla_base(self):
        """Todas las páginas extienden base.html (barra de navegación común)."""
        self.client.force_login(self.user)
        for url in (reverse('home'), reverse('mis_reservas'),
                    reverse('calendario_full', args=[self.resource.id])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'base.html')

    def test_login_usa_la_plantilla_base(self):
        """La página de login también usa base.html."""
        response = self.client.get(reverse('login'))
        self.assertTemplateUsed(response, 'base.html')

    def test_login_incorrecto_muestra_error(self):
        """Un login con datos incorrectos muestra el mensaje de error."""
        response = self.client.post(reverse('login'), {'username': 'ana', 'password': 'mala'})
        self.assertContains(response, 'Usuario o contraseña incorrectos')

    def test_barra_muestra_cerrar_sesion_como_formulario_post(self):
        """Con sesión, "Cerrar sesión" es un formulario POST con token CSRF."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))
        self.assertContains(response, f'<form method="post" action="{reverse("logout")}"')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_calendario_inexistente_devuelve_404(self):
        """El calendario de una pista que no existe devuelve 404."""
        response = self.client.get(reverse('calendario_full', args=[99999]))
        self.assertEqual(response.status_code, 404)


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.client.force_login(self.user)

    def test_logout_por_get_no_cierra_sesion(self):
        """Cerrar sesión por GET no está permitido (405) y la sesión sigue abierta."""
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_por_post_cierra_sesion(self):
        """Cerrar sesión por POST cierra la sesión y lleva al login."""
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_sin_token_csrf_devuelve_403(self):
        """Cerrar sesión exige el token CSRF."""
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(reverse('logout')).status_code, 403)


class CalendarioAntiguoTests(TestCase):
    def test_calendario_antiguo_redirige_al_interactivo(self):
        """La vista antigua /calendario/<id>/ redirige al calendario interactivo."""
        resource = Resource.objects.create(name='Pista 1')
        response = self.client.get(f'/calendario/{resource.id}/')
        self.assertRedirects(response, reverse('calendario_full', args=[resource.id]),
                             fetch_redirect_response=False)
