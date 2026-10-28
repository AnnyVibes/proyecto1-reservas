import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from reservas.models import Booking, Resource
from reservas.tests.test_api_crear_reserva import franja


class MisReservasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.otro = User.objects.create_user(username='luis', password='clave-segura-123')
        self.resource = Resource.objects.create(name='Pista 1')
        self.client.force_login(self.user)

    def reserva(self, horas, user=None, **kwargs):
        """Crea una reserva de 1 hora que empieza dentro de `horas` horas (negativo = pasado)."""
        inicio = timezone.now() + timedelta(hours=horas)
        return Booking.objects.create(user=user or self.user, resource=self.resource,
                                      start_time=inicio, end_time=inicio + timedelta(hours=1),
                                      **kwargs)

    def cancelar(self, reserva, client=None, **kwargs):
        client = client or self.client
        return client.post(reverse('cancelar_reserva', args=[reserva.id]), **kwargs)

    def mensajes(self, response):
        return [str(m) for m in response.context['messages']]

    # --- Página Mis reservas ---

    def test_mis_reservas_sin_sesion_redirige_a_login(self):
        """Mis reservas exige sesión: sin ella redirige al login con ?next=."""
        self.client.logout()
        response = self.client.get(reverse('mis_reservas'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('mis_reservas')}",
                             fetch_redirect_response=False)

    def test_mis_reservas_muestra_solo_las_propias_separadas(self):
        """Mis reservas muestra solo las del usuario, separadas en próximas y pasadas."""
        futura = self.reserva(48)
        pasada = self.reserva(-48)
        self.reserva(24, user=self.otro)

        response = self.client.get(reverse('mis_reservas'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['proximas']), [futura])
        self.assertEqual(list(response.context['pasadas']), [pasada])

    def test_reserva_cancelada_se_muestra_sin_boton_cancelar(self):
        """Una reserva cancelada aparece marcada como Cancelada y sin botón para cancelar."""
        cancelada = self.reserva(48, status=Booking.Status.CANCELADA, cancelled_at=timezone.now())

        response = self.client.get(reverse('mis_reservas'))
        self.assertIn(cancelada, response.context['proximas'])
        self.assertContains(response, 'Cancelada')
        self.assertNotContains(response, reverse('cancelar_reserva', args=[cancelada.id]))

    def test_enlace_mis_reservas_solo_con_sesion(self):
        """La barra de navegación muestra "Mis reservas" solo cuando hay sesión."""
        enlace = f'href="{reverse("mis_reservas")}"'
        for url in (reverse('home'), reverse('calendario_full', args=[self.resource.id])):
            with self.subTest(url=url):
                self.client.force_login(self.user)
                self.assertContains(self.client.get(url), enlace)
                self.client.logout()
                self.assertNotContains(self.client.get(url), enlace)

    # --- Cancelación ---

    def test_cancelacion_valida(self):
        """Una reserva propia con 2 horas o más de anticipación se cancela."""
        reserva = self.reserva(48)
        response = self.cancelar(reserva, follow=True)

        self.assertRedirects(response, reverse('mis_reservas'))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Booking.Status.CANCELADA)
        self.assertIsNotNone(reserva.cancelled_at)
        self.assertEqual(len(self.mensajes(response)), 1)
        self.assertIn('cancelada', self.mensajes(response)[0].lower())

    def test_cancelacion_fuera_de_plazo(self):
        """Con menos de 2 horas de anticipación no se puede cancelar y se informa el error."""
        reserva = self.reserva(1)
        response = self.cancelar(reserva, follow=True)

        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Booking.Status.CONFIRMADA)
        self.assertIsNone(reserva.cancelled_at)
        self.assertIn('2 horas', self.mensajes(response)[0])

    def test_no_se_cancela_reserva_pasada(self):
        """Una reserva que ya pasó no se puede cancelar."""
        reserva = self.reserva(-2)
        self.cancelar(reserva)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Booking.Status.CONFIRMADA)

    def test_no_se_cancela_dos_veces(self):
        """Una reserva ya cancelada no se vuelve a cancelar (cancelled_at no cambia)."""
        momento = timezone.now() - timedelta(days=1)
        reserva = self.reserva(48, status=Booking.Status.CANCELADA, cancelled_at=momento)
        self.cancelar(reserva)
        reserva.refresh_from_db()
        self.assertEqual(reserva.cancelled_at, momento)

    def test_reserva_ajena_devuelve_404(self):
        """Un usuario no puede cancelar la reserva de otro (404) y la reserva no cambia."""
        ajena = self.reserva(48, user=self.otro)
        response = self.cancelar(ajena)
        self.assertEqual(response.status_code, 404)
        ajena.refresh_from_db()
        self.assertEqual(ajena.status, Booking.Status.CONFIRMADA)

    def test_cancelar_sin_sesion_redirige_a_login(self):
        """Cancelar exige sesión: sin ella redirige al login y no cambia nada."""
        reserva = self.reserva(48)
        self.client.logout()
        response = self.cancelar(reserva)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith(reverse('login')))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Booking.Status.CONFIRMADA)

    def test_cancelar_con_get_devuelve_405(self):
        """Cancelar solo acepta POST (405 con GET)."""
        reserva = self.reserva(48)
        response = self.client.get(reverse('cancelar_reserva', args=[reserva.id]))
        self.assertEqual(response.status_code, 405)

    def test_cancelar_sin_token_csrf_devuelve_403(self):
        """Cancelar exige el token CSRF: sin él se rechaza (403)."""
        reserva = self.reserva(48)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = self.cancelar(reserva, client=csrf_client)
        self.assertEqual(response.status_code, 403)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Booking.Status.CONFIRMADA)

    def test_franja_queda_libre_tras_cancelar(self):
        """Tras cancelar, la franja desaparece del calendario y se puede volver a reservar."""
        inicio = franja(2, 10)
        fin = inicio + timedelta(hours=1)
        reserva = Booking.objects.create(user=self.user, resource=self.resource,
                                         start_time=inicio, end_time=fin)
        self.cancelar(reserva)

        eventos = self.client.get(reverse('api_reservas', args=[self.resource.id])).json()
        self.assertEqual(eventos, [])

        self.client.force_login(self.otro)
        response = self.client.post(reverse('api_crear_reserva'), json.dumps({
            'resource_id': self.resource.id,
            'start_time': inicio.isoformat(),
            'end_time': fin.isoformat(),
            'repeat_weeks': 0,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.filter(status=Booking.Status.CONFIRMADA).count(), 1)
