from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from reservas.models import Booking, Resource


class BookingCleanTests(TestCase):
    def test_clean_rechaza_solape(self):
        """Booking.clean() lanza ValidationError si la franja se solapa con otra reserva."""
        user = User.objects.create_user(username='ana', password='clave-segura-123')
        resource = Resource.objects.create(name='Pista 1')
        fecha = timezone.localdate() + timedelta(days=1)
        inicio = timezone.make_aware(datetime.combine(fecha, time(10, 0)))
        Booking.objects.create(user=user, resource=resource,
                               start_time=inicio, end_time=inicio + timedelta(hours=1))

        solapada = Booking(user=user, resource=resource,
                           start_time=inicio + timedelta(minutes=30),
                           end_time=inicio + timedelta(minutes=90))
        with self.assertRaises(ValidationError):
            solapada.clean()

    def test_clean_ignora_reservas_canceladas(self):
        """Una reserva cancelada no cuenta como conflicto en Booking.clean()."""
        user = User.objects.create_user(username='ana', password='clave-segura-123')
        resource = Resource.objects.create(name='Pista 1')
        fecha = timezone.localdate() + timedelta(days=1)
        inicio = timezone.make_aware(datetime.combine(fecha, time(10, 0)))
        fin = inicio + timedelta(hours=1)
        Booking.objects.create(user=user, resource=resource, start_time=inicio, end_time=fin,
                               status=Booking.Status.CANCELADA, cancelled_at=timezone.now())

        nueva = Booking(user=user, resource=resource, start_time=inicio, end_time=fin)
        nueva.clean()  # no debe lanzar ValidationError
