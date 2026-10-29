import json
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from reservas.models import Availability, Booking, Resource


# Tarjeta de prueba válida (Luhn) que el pago simulado aprueba
TARJETA_DE_PRUEBA = {
    'titular': 'Ana Prueba', 'numero': '4242 4242 4242 4242',
    'mes': 12, 'anio': timezone.localdate().year + 2, 'cvv': '987',
}


def franja(dias, hora):
    """Devuelve el inicio de la franja de `hora` dentro de `dias` días (hora local, con zona)."""
    fecha = timezone.localdate() + timedelta(days=dias)
    return timezone.make_aware(datetime.combine(fecha, time(hora, 0)))


class ApiCrearReservaTests(TestCase):
    def setUp(self):
        self.url = reverse('api_crear_reserva')
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.resource = Resource.objects.create(name='Pista 1')
        self.client.force_login(self.user)

    def payload(self, inicio, fin, repeat_weeks=0, resource_id=None):
        return json.dumps({
            'resource_id': resource_id if resource_id is not None else self.resource.id,
            'start_time': inicio.isoformat(),
            'end_time': fin.isoformat(),
            'repeat_weeks': repeat_weeks,
            'tarjeta': TARJETA_DE_PRUEBA,   # HU-01: reservar exige un método de pago
        })

    def post(self, inicio, fin, client=None, **kwargs):
        client = client or self.client
        return client.post(self.url, self.payload(inicio, fin, **kwargs),
                           content_type='application/json')

    def test_reserva_valida_se_crea(self):
        """Un usuario autenticado puede reservar una franja libre (201)."""
        inicio = franja(1, 10)
        response = self.post(inicio, inicio + timedelta(hours=1))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.count(), 1)
        reserva = Booking.objects.get()
        self.assertEqual(reserva.user, self.user)
        self.assertEqual(reserva.start_time, inicio)

    def test_sin_sesion_devuelve_401(self):
        """Sin sesión no se puede reservar (401) y no se crea nada."""
        self.client.logout()
        inicio = franja(1, 10)
        response = self.post(inicio, inicio + timedelta(hours=1))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Booking.objects.count(), 0)

    def test_solape_con_reserva_existente_devuelve_409(self):
        """No se puede reservar una franja ya ocupada por otra reserva (409)."""
        inicio = franja(1, 10)
        fin = inicio + timedelta(hours=1)
        otro = User.objects.create_user(username='luis', password='clave-segura-123')
        Booking.objects.create(user=otro, resource=self.resource, start_time=inicio, end_time=fin)

        response = self.post(inicio, fin)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_franja_bloqueada_devuelve_409(self):
        """El servidor rechaza una franja bloqueada por Availability (409)."""
        inicio = franja(1, 10)
        fin = inicio + timedelta(hours=1)
        Availability.objects.create(resource=self.resource, start_time=inicio, end_time=fin)

        response = self.post(inicio, fin)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 0)

    def test_recurrente_con_conflicto_no_crea_ninguna(self):
        """Una reserva recurrente es atómica: si una semana choca, no se crea ninguna."""
        inicio = franja(1, 10)
        fin = inicio + timedelta(hours=1)
        otro = User.objects.create_user(username='luis', password='clave-segura-123')
        Booking.objects.create(user=otro, resource=self.resource,
                               start_time=inicio + timedelta(weeks=2),
                               end_time=fin + timedelta(weeks=2))

        response = self.post(inicio, fin, repeat_weeks=2)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(Booking.objects.filter(user=self.user).exists())

    def test_repeat_weeks_excesivo_devuelve_400(self):
        """repeat_weeks tiene un límite máximo; 500 se rechaza (400) sin crear nada."""
        inicio = franja(1, 10)
        response = self.post(inicio, inicio + timedelta(hours=1), repeat_weeks=500)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_fin_anterior_al_inicio_devuelve_400(self):
        """El fin de la reserva debe ser posterior al inicio (400)."""
        inicio = franja(1, 10)
        response = self.post(inicio, inicio - timedelta(hours=1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_fecha_en_el_pasado_devuelve_400(self):
        """No se puede reservar una franja en el pasado (400)."""
        inicio = franja(-1, 10)
        response = self.post(inicio, inicio + timedelta(hours=1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_fuera_del_horario_devuelve_400(self):
        """Solo se puede reservar entre las 09:00 y las 21:00 (400 fuera de ese horario)."""
        for hora in (8, 21):
            with self.subTest(hora=hora):
                inicio = franja(1, hora)
                response = self.post(inicio, inicio + timedelta(hours=1))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Booking.objects.count(), 0)

    def test_post_sin_token_csrf_devuelve_403(self):
        """La API exige el token CSRF: un POST sin token se rechaza (403)."""
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        inicio = franja(1, 10)
        response = self.post(inicio, inicio + timedelta(hours=1), client=csrf_client)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Booking.objects.count(), 0)

    def test_resource_inexistente_devuelve_404(self):
        """Reservar una pista que no existe devuelve 404 y no crea nada."""
        inicio = franja(1, 10)
        response = self.post(inicio, inicio + timedelta(hours=1), resource_id=99999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Booking.objects.count(), 0)
