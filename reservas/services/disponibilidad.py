"""
Disponibilidad por día de un recurso, para colorear el calendario mensual.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from reservas.models import Availability, Booking
from reservas.services.reservas import FRANJA_FIN, FRANJA_INICIO

TOTAL_FRANJAS = FRANJA_FIN - FRANJA_INICIO   # 12 franjas de 1 hora
MAX_DIAS_RANGO = 62


def _momento(dia, hora):
    return timezone.make_aware(datetime.combine(dia, time(hora, 0)))


def _solapa(inicio, fin, ocupados):
    return any(o_inicio < fin and o_fin > inicio for o_inicio, o_fin in ocupados)


def estado_dias(resource, desde, hasta):
    """
    Devuelve, para cada día de [desde, hasta) (hasta exclusivo, como FullCalendar):
    {"fecha": "YYYY-MM-DD", "estado": "libre|parcial|completo|pasado", "libres": int, "total": 12}

    Una franja está ocupada si la solapa una reserva activa o un bloqueo. Hoy, las
    franjas que ya empezaron tampoco cuentan como libres.
    """
    ahora = timezone.now()
    hoy = timezone.localdate()
    rango_inicio = _momento(desde, FRANJA_INICIO)
    rango_fin = _momento(hasta - timedelta(days=1), FRANJA_FIN)

    ocupados = list(
        Booking.objects.activas()
        .filter(resource=resource, start_time__lt=rango_fin, end_time__gt=rango_inicio)
        .values_list('start_time', 'end_time')
    ) + list(
        Availability.objects
        .filter(resource=resource, start_time__lt=rango_fin, end_time__gt=rango_inicio)
        .values_list('start_time', 'end_time')
    )

    dias = []
    dia = desde
    while dia < hasta:
        libres = 0
        for hora in range(FRANJA_INICIO, FRANJA_FIN):
            inicio = _momento(dia, hora)
            fin = inicio + timedelta(hours=1)
            if inicio >= ahora and not _solapa(inicio, fin, ocupados):
                libres += 1

        if dia < hoy:
            estado = 'pasado'
        elif libres == TOTAL_FRANJAS:
            estado = 'libre'
        elif libres == 0:
            estado = 'completo'
        else:
            estado = 'parcial'

        dias.append({'fecha': dia.isoformat(), 'estado': estado,
                     'libres': libres, 'total': TOTAL_FRANJAS})
        dia += timedelta(days=1)
    return dias
