"""
Reglas de negocio para crear reservas: horario, solapes, bloqueos y repeticiones.
"""
from datetime import time, timedelta

from django.db import transaction
from django.utils import timezone

from reservas.models import Availability, Booking
from reservas.services.notificaciones import enviar_cancelacion

FRANJA_INICIO = 9    # 09:00
FRANJA_FIN = 21      # 21:00
MAX_SEMANAS_REPETICION = 12
HORAS_MIN_CANCELACION = 2


class ReservaInvalida(Exception):
    """Los datos de la reserva no cumplen las reglas (fechas, horario, repeticiones)."""


class ConflictoHorario(Exception):
    """La franja se solapa con otra reserva o con un bloqueo."""


class CancelacionNoPermitida(Exception):
    """La reserva no se puede cancelar (ya cancelada, pasada o fuera de plazo)."""


def hay_conflicto(resource, inicio, fin, excluir_id=None):
    """
    Indica si la franja [inicio, fin) se solapa con una reserva o un bloqueo del recurso.
    """
    reservas = Booking.objects.activas().filter(resource=resource, start_time__lt=fin, end_time__gt=inicio)
    if excluir_id is not None:
        reservas = reservas.exclude(pk=excluir_id)
    bloqueos = Availability.objects.filter(resource=resource, start_time__lt=fin, end_time__gt=inicio)
    return reservas.exists() or bloqueos.exists()


def _validar(inicio, fin, repetir_semanas):
    if fin <= inicio:
        raise ReservaInvalida('La hora de fin debe ser posterior a la de inicio.')
    if inicio < timezone.now():
        raise ReservaInvalida('No se puede reservar en el pasado.')

    inicio_local = timezone.localtime(inicio)
    fin_local = timezone.localtime(fin)
    if (inicio_local.date() != fin_local.date()
            or inicio_local.time() < time(FRANJA_INICIO)
            or fin_local.time() > time(FRANJA_FIN)):
        raise ReservaInvalida(
            f'La reserva debe estar entre las {FRANJA_INICIO:02d}:00 y las {FRANJA_FIN:02d}:00.'
        )

    if isinstance(repetir_semanas, bool) or not isinstance(repetir_semanas, int):
        raise ReservaInvalida('El número de semanas a repetir debe ser un entero.')
    if not 0 <= repetir_semanas <= MAX_SEMANAS_REPETICION:
        raise ReservaInvalida(
            f'Solo se puede repetir entre 0 y {MAX_SEMANAS_REPETICION} semanas.'
        )


def crear_reservas(user, resource, inicio, fin, repetir_semanas=0):
    """
    Crea la reserva y sus repeticiones semanales. Es todo o nada: si una semana
    tiene conflicto, no se guarda ninguna.
    """
    _validar(inicio, fin, repetir_semanas)

    creadas = []
    with transaction.atomic():
        for semana in range(repetir_semanas + 1):
            desde = inicio + timedelta(weeks=semana)
            hasta = fin + timedelta(weeks=semana)
            if hay_conflicto(resource, desde, hasta):
                raise ConflictoHorario(
                    f'La franja de la semana {semana + 1} '
                    f'({timezone.localtime(desde):%d/%m/%Y %H:%M}) no está disponible.'
                )
            creadas.append(Booking.objects.create(
                user=user, resource=resource, start_time=desde, end_time=hasta,
            ))
    return creadas


def _motivo_no_cancelable(booking, ahora):
    """Devuelve por qué no se puede cancelar la reserva, o None si se puede."""
    if booking.status == Booking.Status.CANCELADA:
        return 'La reserva ya estaba cancelada.'
    if booking.start_time <= ahora:
        return 'No se puede cancelar una reserva que ya empezó o terminó.'
    if booking.start_time - ahora < timedelta(hours=HORAS_MIN_CANCELACION):
        return (f'Solo se puede cancelar con al menos {HORAS_MIN_CANCELACION} horas '
                'de anticipación.')
    return None


def puede_cancelar(booking, ahora=None):
    """Indica si la reserva está confirmada y empieza dentro de 2 horas o más."""
    return _motivo_no_cancelable(booking, ahora or timezone.now()) is None


def cancelar_reserva(booking):
    """
    Cancela la reserva: queda en estado cancelada y libera la franja.
    Lanza CancelacionNoPermitida si no cumple las reglas.
    """
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        ahora = timezone.now()
        motivo = _motivo_no_cancelable(booking, ahora)
        if motivo:
            raise CancelacionNoPermitida(motivo)
        booking.status = Booking.Status.CANCELADA
        booking.cancelled_at = ahora
        booking.save(update_fields=['status', 'cancelled_at'])
        transaction.on_commit(lambda: enviar_cancelacion(booking))
    return booking
