import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from reservas.models import Booking, Resource
from reservas.services.notificaciones import enviar_cancelacion, enviar_confirmacion
from reservas.tests.test_api_crear_reserva import TARJETA_DE_PRUEBA, franja


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CorreosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123',
                                             email='ana@example.com')
        self.resource = Resource.objects.create(name='Pista de tenis')
        self.client.force_login(self.user)
        self.inicio = franja(1, 10)

    def reservar(self, repeat_weeks=0, tarjeta=TARJETA_DE_PRUEBA):
        return self.client.post(reverse('api_crear_reserva'), json.dumps({
            'resource_id': self.resource.id,
            'start_time': self.inicio.isoformat(),
            'end_time': (self.inicio + timedelta(hours=1)).isoformat(),
            'repeat_weeks': repeat_weeks,
            'tarjeta': tarjeta,
        }), content_type='application/json')

    def test_confirmacion_al_reservar(self):
        """Al crear una reserva se envía, tras el commit, un correo con pista, fecha, horas y referencia."""
        with self.captureOnCommitCallbacks(execute=True):
            response = self.reservar()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        reserva = Booking.objects.get()
        self.assertEqual(correo.to, ['ana@example.com'])
        self.assertEqual(correo.from_email, 'reservas@gestor.local')
        self.assertIn('Pista de tenis', correo.subject)
        local = timezone.localtime(reserva.start_time)
        for texto in ('Pista de tenis', local.strftime('%d/%m/%Y'), '10:00', '11:00', f'RES-{reserva.id}'):
            with self.subTest(texto=texto):
                self.assertIn(texto, correo.body)

    def test_no_se_envia_antes_del_commit(self):
        """El correo se envía con transaction.on_commit: no sale si la transacción no se confirma."""
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.reservar()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(callbacks), 1)

    def test_recurrente_envia_un_correo_con_todas_las_referencias(self):
        """Una reserva recurrente envía un solo correo con la referencia de cada semana."""
        with self.captureOnCommitCallbacks(execute=True):
            self.reservar(repeat_weeks=2)
        self.assertEqual(len(mail.outbox), 1)
        for reserva in Booking.objects.all():
            self.assertIn(f'RES-{reserva.id}', mail.outbox[0].body)

    def test_pago_rechazado_no_envia_correo(self):
        """Si el pago se rechaza no hay reserva ni correo."""
        with self.captureOnCommitCallbacks(execute=True):
            response = self.reservar(tarjeta=dict(TARJETA_DE_PRUEBA, numero='4000 0000 0000 0002'))
        self.assertEqual(response.status_code, 402)
        self.assertEqual(len(mail.outbox), 0)

    def test_usuario_sin_correo_no_falla(self):
        """Si el usuario no tiene correo no se envía nada y la reserva se crea igual."""
        self.user.email = ''
        self.user.save()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.reservar()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)

    def test_cancelacion_envia_correo(self):
        """Al cancelar se envía un correo de cancelación con la referencia."""
        reserva = Booking.objects.create(user=self.user, resource=self.resource,
                                         start_time=self.inicio, end_time=self.inicio + timedelta(hours=1))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancelar_reserva', args=[reserva.id]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('cancelada', mail.outbox[0].subject.lower())
        self.assertIn(f'RES-{reserva.id}', mail.outbox[0].body)

    def test_cancelacion_no_permitida_no_envia_correo(self):
        """Si la cancelación no se permite (menos de 2 horas) no se envía correo."""
        inicio = timezone.now() + timedelta(hours=1)
        reserva = Booking.objects.create(user=self.user, resource=self.resource,
                                         start_time=inicio, end_time=inicio + timedelta(hours=1))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('cancelar_reserva', args=[reserva.id]))
        self.assertEqual(len(mail.outbox), 0)

    def test_funciones_directas_sin_correo_devuelven_false(self):
        """enviar_confirmacion y enviar_cancelacion no fallan si el usuario no tiene correo."""
        sin_correo = User.objects.create_user(username='luis', password='clave-segura-123')
        reserva = Booking.objects.create(user=sin_correo, resource=self.resource,
                                         start_time=self.inicio, end_time=self.inicio + timedelta(hours=1))
        self.assertFalse(enviar_confirmacion(reserva))
        self.assertFalse(enviar_cancelacion(reserva))


class ConfiguracionCorreoTests(TestCase):
    def test_remitente_por_defecto(self):
        """El remitente por defecto es reservas@gestor.local."""
        self.assertEqual(settings.DEFAULT_FROM_EMAIL, 'reservas@gestor.local')
