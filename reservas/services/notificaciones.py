"""
Correos de confirmación y cancelación (texto plano). Se llaman con
transaction.on_commit para enviarse solo si la reserva o la cancelación se guardó.
"""
import logging

from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def referencia(booking):
    """Número de referencia de una reserva: RES-<id>."""
    return f'RES-{booking.id}'


def _enviar(user, asunto, plantilla, contexto):
    """Envía el correo si el usuario tiene dirección. Nunca lanza excepciones al llamador."""
    if not user.email:
        return False
    cuerpo = render_to_string(plantilla, contexto)
    try:
        return send_mail(asunto, cuerpo, None, [user.email]) == 1
    except Exception:  # un fallo del servidor de correo no debe romper la reserva
        logger.exception('No se pudo enviar el correo "%s"', asunto)
        return False


def enviar_confirmacion(reservas):
    """
    Correo de confirmación. Acepta una reserva o una lista (reserva recurrente:
    un solo correo con todas las fechas y referencias).
    """
    if not isinstance(reservas, (list, tuple)):
        reservas = [reservas]
    if not reservas:
        return False
    primera = reservas[0]
    filas = [{'reserva': r, 'referencia': referencia(r)} for r in reservas]
    asunto = f'Reserva confirmada: {primera.resource.name}'
    return _enviar(primera.user, asunto, 'reservas/emails/confirmacion.txt',
                   {'usuario': primera.user, 'pista': primera.resource, 'filas': filas})


def enviar_cancelacion(booking):
    """Correo de cancelación de una reserva."""
    asunto = f'Reserva cancelada: {booking.resource.name} ({referencia(booking)})'
    return _enviar(booking.user, asunto, 'reservas/emails/cancelacion.txt',
                   {'usuario': booking.user, 'pista': booking.resource,
                    'reserva': booking, 'referencia': referencia(booking)})
