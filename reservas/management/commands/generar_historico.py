import random
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reservas.models import Availability, Booking, Resource
from reservas.services.reservas import FRANJA_FIN, FRANJA_INICIO

USUARIO_HISTORICO = 'demo_historico'


def probabilidad(dia, hora):
    """Probabilidad de que una franja esté reservada: más demanda en tardes y fines de semana."""
    p = 0.15
    if hora >= 17:
        p += 0.35
    elif hora >= 14:
        p += 0.10
    if dia.weekday() >= 5:
        p += 0.20
    return p


class Command(BaseCommand):
    help = ("Genera reservas pasadas del usuario demo_historico para el panel de demanda. "
            "--reset borra solo las reservas de demo_historico.")

    def add_arguments(self, parser):
        parser.add_argument('--semanas', type=int, default=26, help='Semanas hacia atrás (por defecto 26).')
        parser.add_argument('--seed', type=int, default=42, help='Semilla para que el resultado sea reproducible.')
        parser.add_argument('--reset', action='store_true',
                            help='Borra antes las reservas de demo_historico (y solo esas).')

    def handle(self, *args, semanas, seed, reset, **kwargs):
        usuario, _ = User.objects.get_or_create(username=USUARIO_HISTORICO)
        if reset:
            borradas, _ = Booking.objects.filter(user=usuario).delete()
            self.stdout.write(f'Se borraron {borradas} reservas de {USUARIO_HISTORICO}.')

        pistas = list(Resource.objects.order_by('id'))
        if not pistas:
            self.stdout.write(self.style.WARNING('No hay pistas. Ejecuta antes: python manage.py loaddata pistas'))
            return

        hoy = timezone.localdate()
        desde = hoy - timedelta(weeks=semanas)
        # Solo días ya pasados: [hoy - semanas, hoy)
        rango = (timezone.make_aware(datetime.combine(desde, time.min)),
                 timezone.make_aware(datetime.combine(hoy, time.min)))

        # Franjas ya ocupadas (reservas activas y bloqueos) para no crear solapes
        ocupados = {}
        for modelo in (Booking.objects.activas(), Availability.objects.all()):
            for resource_id, inicio, fin in modelo.filter(start_time__lt=rango[1], end_time__gt=rango[0]) \
                                                  .values_list('resource_id', 'start_time', 'end_time'):
                ocupados.setdefault(resource_id, []).append((inicio, fin))

        azar = random.Random(seed)
        nuevas = []
        dia = desde
        while dia < hoy:
            for pista in pistas:
                for hora in range(FRANJA_INICIO, FRANJA_FIN):
                    inicio = timezone.make_aware(datetime.combine(dia, time(hora)))
                    fin = inicio + timedelta(hours=1)
                    # Se sortea siempre, para que la misma semilla dé el mismo resultado
                    if azar.random() >= probabilidad(dia, hora):
                        continue
                    if any(o_ini < fin and o_fin > inicio for o_ini, o_fin in ocupados.get(pista.id, [])):
                        continue
                    nuevas.append(Booking(user=usuario, resource=pista, start_time=inicio, end_time=fin))
            dia += timedelta(days=1)

        with transaction.atomic():
            Booking.objects.bulk_create(nuevas)
        self.stdout.write(self.style.SUCCESS(
            f'Se crearon {len(nuevas)} reservas pasadas de {USUARIO_HISTORICO} '
            f'en {len(pistas)} pista(s) durante {semanas} semana(s).'
        ))
