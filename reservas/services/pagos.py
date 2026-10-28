"""
Pagos SIMULADOS. Nunca se guarda (ni en BD, ni en logs, ni en sesión) el número
completo de la tarjeta ni el CVV: solo titular, marca, últimos 4 dígitos,
vencimiento y un token generado.
"""
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from reservas.models import Payment, PaymentMethod
from reservas.services.reservas import crear_reservas

# Tarjeta de prueba que el procesador simulado SIEMPRE rechaza
TARJETA_RECHAZADA = '4000000000000002'


class PagoInvalido(Exception):
    """Los datos de pago no son válidos (número, vencimiento, CVV o falta el método)."""


class PagoRechazado(Exception):
    """El procesador simulado rechazó el pago."""


class MetodoNoEncontrado(Exception):
    """La tarjeta guardada no existe o es de otro usuario."""


def limpiar_numero(numero):
    """Quita espacios y guiones del número de tarjeta."""
    return str(numero or '').replace(' ', '').replace('-', '')


def luhn_valido(numero):
    """Algoritmo de Luhn sobre un número de tarjeta (solo dígitos)."""
    if not numero.isdigit():
        return False
    total = 0
    for i, digito in enumerate(reversed(numero)):
        n = int(digito)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def detectar_marca(numero):
    """visa (4), mastercard (51–55 / 2221–2720), amex (34/37) u otra."""
    numero = limpiar_numero(numero)
    if numero.startswith('4'):
        return PaymentMethod.Brand.VISA
    if numero[:2] in ('34', '37'):
        return PaymentMethod.Brand.AMEX
    if numero[:2].isdigit() and 51 <= int(numero[:2]) <= 55:
        return PaymentMethod.Brand.MASTERCARD
    if numero[:4].isdigit() and 2221 <= int(numero[:4]) <= 2720:
        return PaymentMethod.Brand.MASTERCARD
    return PaymentMethod.Brand.OTRA


def _vencimiento(mes, anio):
    """Devuelve (mes, anio) como enteros o lanza PagoInvalido. Acepta años de 2 o 4 dígitos."""
    try:
        mes, anio = int(mes), int(anio)
    except (TypeError, ValueError):
        raise PagoInvalido('La fecha de vencimiento no es válida.')
    if anio < 100:
        anio += 2000
    if not 1 <= mes <= 12:
        raise PagoInvalido('El mes de vencimiento no es válido.')
    return mes, anio


def _vencida(mes, anio):
    hoy = timezone.localdate()
    return (anio, mes) < (hoy.year, hoy.month)


def validar_tarjeta(numero, mes, anio, cvv):
    """
    Valida una tarjeta: Luhn, vencimiento futuro (vale hasta el final del mes) y
    CVV de 3–4 dígitos. Devuelve el número limpio o lanza PagoInvalido.
    Los mensajes de error nunca incluyen el número ni el CVV.
    """
    numero = limpiar_numero(numero)
    if not (13 <= len(numero) <= 19) or not luhn_valido(numero):
        raise PagoInvalido('El número de tarjeta no es válido.')
    mes, anio = _vencimiento(mes, anio)
    if _vencida(mes, anio):
        raise PagoInvalido('La tarjeta está vencida.')
    cvv = str(cvv or '')
    if not (cvv.isdigit() and 3 <= len(cvv) <= 4):
        raise PagoInvalido('El CVV debe tener 3 o 4 dígitos.')
    return numero


def procesar_pago_simulado(monto, numero=None, metodo=None):
    """
    Simula el cobro. La tarjeta de prueba 4000 0000 0000 0002 siempre se rechaza;
    el resto se aprueba. Devuelve (aprobado, referencia).
    """
    referencia = f'PAY-{uuid.uuid4().hex[:12].upper()}'
    if numero is not None and limpiar_numero(numero) == TARJETA_RECHAZADA:
        return False, referencia
    return True, referencia


def guardar_metodo(user, titular, numero, mes, anio):
    """
    Guarda solo titular, marca, últimos 4 dígitos, vencimiento y un token generado.
    Si el usuario ya tiene guardada la misma tarjeta (marca, últimos 4 y vencimiento), la reutiliza.
    """
    numero = limpiar_numero(numero)
    mes, anio = _vencimiento(mes, anio)
    datos = {'user': user, 'brand': detectar_marca(numero), 'last4': numero[-4:],
             'exp_month': mes, 'exp_year': anio}
    # filter().first() y no get_or_create: no falla aunque ya existieran duplicados
    existente = PaymentMethod.objects.filter(**datos).order_by('created_at').first()
    if existente:
        return existente
    return PaymentMethod.objects.create(holder_name=(titular or '').strip()[:100], **datos)


def importe_por_reserva(resource, inicio, fin):
    """Precio de una reserva: precio por hora × horas (redondeado a céntimos)."""
    horas = Decimal((fin - inicio).total_seconds()) / Decimal(3600)
    return (resource.price_per_hour * horas).quantize(Decimal('0.01'))


def reservar_y_pagar(user, resource, inicio, fin, repetir_semanas=0,
                     payment_method_id=None, tarjeta=None, guardar=False):
    """
    Crea la(s) reserva(s) y su pago en UNA sola transacción: si el pago se
    rechaza o falla cualquier paso, no queda ni reserva ni pago ni tarjeta.

    - payment_method_id: tarjeta guardada del propio usuario, o
    - tarjeta: {"titular", "numero", "mes", "anio", "cvv"} y guardar=True/False.

    Devuelve (reservas, pagos, metodo). Lanza PagoInvalido, MetodoNoEncontrado,
    PagoRechazado, ReservaInvalida o ConflictoHorario.
    """
    metodo = None
    numero = None
    if payment_method_id is not None:
        try:
            metodo = PaymentMethod.objects.get(pk=int(payment_method_id), user=user)
        except (TypeError, ValueError, PaymentMethod.DoesNotExist):
            raise MetodoNoEncontrado('La tarjeta guardada no existe.')
        if _vencida(metodo.exp_month, metodo.exp_year):
            raise PagoInvalido('La tarjeta guardada está vencida.')
    elif isinstance(tarjeta, dict):
        numero = validar_tarjeta(tarjeta.get('numero'), tarjeta.get('mes'),
                                 tarjeta.get('anio'), tarjeta.get('cvv'))
        if not str(tarjeta.get('titular') or '').strip():
            raise PagoInvalido('Indica el nombre del titular de la tarjeta.')
    else:
        raise PagoInvalido('Indica un método de pago.')

    with transaction.atomic():
        reservas = crear_reservas(user, resource, inicio, fin, repetir_semanas)
        importe = importe_por_reserva(resource, inicio, fin)
        aprobado, referencia = procesar_pago_simulado(importe * len(reservas), numero=numero, metodo=metodo)
        if not aprobado:
            raise PagoRechazado('El pago fue rechazado. Prueba con otra tarjeta.')

        if numero is not None and guardar:
            metodo = guardar_metodo(user, tarjeta.get('titular'), numero, tarjeta.get('mes'), tarjeta.get('anio'))

        pagos = [
            Payment.objects.create(
                booking=reserva, payment_method=metodo, amount=importe,
                status=Payment.Status.APROBADO, reference=f'{referencia}-{i}',
            )
            for i, reserva in enumerate(reservas, start=1)
        ]
    return reservas, pagos, metodo
