"""
Agregaciones de demanda y previsión por promedio móvil (Python puro, sin pandas).
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from reservas.models import Booking
from reservas.services.reservas import FRANJA_FIN, FRANJA_INICIO

DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def _reservas(resource):
    reservas = Booking.objects.activas()
    if resource is not None:
        reservas = reservas.filter(resource=resource)
    return reservas


def reservas_por_semana(resource=None, semanas=12):
    """
    Total de reservas activas por semana (de lunes a domingo, hora local) en las
    últimas `semanas` semanas completas; la semana en curso no se incluye.
    Devuelve [{"semana": "YYYY-MM-DD" (lunes), "total": int}, ...] de la más antigua a la más reciente.
    """
    hoy = timezone.localdate()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    primer_lunes = lunes_actual - timedelta(weeks=semanas)

    totales = {primer_lunes + timedelta(weeks=i): 0 for i in range(semanas)}
    desde = timezone.make_aware(datetime.combine(primer_lunes, time.min))
    hasta = timezone.make_aware(datetime.combine(lunes_actual, time.min))
    for inicio in _reservas(resource).filter(start_time__gte=desde, start_time__lt=hasta) \
                                     .values_list('start_time', flat=True):
        dia = timezone.localtime(inicio).date()
        totales[dia - timedelta(days=dia.weekday())] += 1

    return [{'semana': lunes.isoformat(), 'total': total} for lunes, total in sorted(totales.items())]


def prevision_promedio_movil(serie, ventana=4, horizonte=4):
    """
    Previsión plana: cada una de las `horizonte` semanas futuras vale el promedio de
    las últimas `ventana` semanas reales. Ejemplo: [10, 12, 14, 16] -> [13.0, 13.0, 13.0, 13.0].
    Si hay menos semanas que la ventana se promedian las disponibles; sin datos, 0.
    """
    ultimas = serie[-ventana:] if ventana > 0 else []
    promedio = sum(ultimas) / len(ultimas) if ultimas else 0.0
    return [round(float(promedio), 2)] * horizonte


def ocupacion_por_dia_hora(resource=None):
    """
    Cuántas veces se ha ocupado cada franja, por día de la semana y hora (9–20).
    Devuelve {"dias": [...], "horas": [9, ..., 20], "matriz": [[int] * 12] * 7}.
    """
    horas = list(range(FRANJA_INICIO, FRANJA_FIN))
    matriz = [[0] * len(horas) for _ in DIAS_SEMANA]
    for inicio, fin in _reservas(resource).values_list('start_time', 'end_time'):
        inicio, fin = timezone.localtime(inicio), timezone.localtime(fin)
        franja = inicio.replace(minute=0, second=0, microsecond=0)
        while franja < fin:
            if FRANJA_INICIO <= franja.hour < FRANJA_FIN:
                matriz[franja.weekday()][franja.hour - FRANJA_INICIO] += 1
            franja += timedelta(hours=1)
    return {'dias': DIAS_SEMANA, 'horas': horas, 'matriz': matriz}
