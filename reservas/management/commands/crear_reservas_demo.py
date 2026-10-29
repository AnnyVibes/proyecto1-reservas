from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from reservas.models import Booking, Resource


class Command(BaseCommand):
    help = "Crea un usuario demo y reservas de prueba para los próximos días (solo borra las del usuario demo)"

    def handle(self, *args, **kwargs):
        # Crear un usuario demo si no existe
        user, created = User.objects.get_or_create(username='demo_user')
        if created:
            user.set_password('demo1234')
            user.save()
            self.stdout.write(self.style.SUCCESS("Usuario demo_user creado."))

        # Crear un recurso demo si no existe
        recurso, creado = Resource.objects.get_or_create(name='Pista Pádel 1', defaults={'description': 'Pista de pádel exterior'})
        if creado:
            self.stdout.write(self.style.SUCCESS("Recurso Pista Pádel 1 creado."))

        # Limpia solo las reservas anteriores del usuario demo (nunca las de otros usuarios)
        Booking.objects.filter(user=user).delete()
        manana = timezone.localdate() + timedelta(days=1)

        creadas = 0
        for i in range(5):  # 5 días, empezando mañana
            for j in range(3):  # 3 reservas al día: 09:00, 11:00 y 13:00
                inicio = timezone.make_aware(datetime.combine(manana + timedelta(days=i), time(9 + j * 2)))
                fin = inicio + timedelta(hours=1)
                ocupada = Booking.objects.activas().filter(
                    resource=recurso, start_time__lt=fin, end_time__gt=inicio
                ).exists()
                if not ocupada:
                    Booking.objects.create(user=user, resource=recurso, start_time=inicio, end_time=fin)
                    creadas += 1
        self.stdout.write(self.style.SUCCESS(f"Reservas demo creadas correctamente: {creadas}."))
