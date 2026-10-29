import json
from datetime import date, datetime, time, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Resource, Booking, Availability, PaymentMethod
from .services.demanda import ocupacion_por_dia_hora, prevision_promedio_movil, reservas_por_semana
from .services.disponibilidad import MAX_DIAS_RANGO, estado_dias
from .services.pagos import MetodoNoEncontrado, PagoInvalido, PagoRechazado, reservar_y_pagar
from .services.reservas import (
    MAX_SEMANAS_REPETICION, CancelacionNoPermitida, ConflictoHorario, ReservaInvalida,
    cancelar_reserva as cancelar_reserva_servicio, puede_cancelar,
)


def calendario_full(request, resource_id):
    """
    Calendario interactivo con FullCalendar. Reservas, bloqueos y disponibilidad
    se cargan por API según el rango visible.
    """
    resource = get_object_or_404(Resource, id=resource_id)
    tarjetas = []
    if request.user.is_authenticated:
        tarjetas = [
            {'id': t.id, 'marca': t.get_brand_display(), 'last4': t.last4,
             'vence': f'{t.exp_month:02d}/{t.exp_year % 100:02d}'}
            for t in request.user.payment_methods.order_by('-created_at')
        ]
    return render(request, 'reservas/calendario_full.html', {
        'resource': resource,
        'is_authenticated': request.user.is_authenticated,
        'tarjetas': tarjetas,
        'datos_pago': {'precio_hora': str(resource.price_per_hour), 'tarjetas': tarjetas},
        'semanas_repeticion': range(1, MAX_SEMANAS_REPETICION + 1),
    })


def _error(mensaje, status):
    return JsonResponse({'success': False, 'error': mensaje}, status=status)


def _leer_fecha(valor):
    """Convierte un texto ISO en datetime con zona horaria, o None si no es válido."""
    if not isinstance(valor, str):
        return None
    try:
        fecha = parse_datetime(valor)
    except ValueError:
        return None
    if fecha is not None and timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    return fecha


@require_POST
def api_crear_reserva(request):
    """
    Endpoint para crear una nueva reserva, con soporte para repeticiones semanales.
    Las reglas de negocio están en reservas.services.reservas.
    """
    if not request.user.is_authenticated:
        return _error('Debes iniciar sesión para reservar.', 401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error('El cuerpo de la petición no es JSON válido.', 400)
    if not isinstance(data, dict):
        return _error('El cuerpo de la petición no es JSON válido.', 400)

    inicio = _leer_fecha(data.get('start_time'))
    fin = _leer_fecha(data.get('end_time'))
    if inicio is None or fin is None:
        return _error('Las fechas de inicio y fin son obligatorias y deben tener formato ISO.', 400)

    repeat_weeks = data.get('repeat_weeks', 0)
    if isinstance(repeat_weeks, bool) or not isinstance(repeat_weeks, int):
        return _error('El número de semanas a repetir debe ser un entero.', 400)

    resource_id = data.get('resource_id')
    try:
        resource = Resource.objects.get(pk=int(resource_id))
    except (TypeError, ValueError, Resource.DoesNotExist):
        return _error('La pista no existe.', 404)

    # Pago: tarjeta guardada (payment_method_id) o tarjeta nueva (tarjeta + guardar)
    try:
        reservas, pagos, metodo = reservar_y_pagar(
            request.user, resource, inicio, fin, repeat_weeks,
            payment_method_id=data.get('payment_method_id'),
            tarjeta=data.get('tarjeta'),
            guardar=data.get('guardar') is True,
        )
    except (ReservaInvalida, PagoInvalido) as e:
        return _error(str(e), 400)
    except MetodoNoEncontrado as e:
        return _error(str(e), 404)
    except ConflictoHorario as e:
        return _error(str(e), 409)
    except PagoRechazado as e:
        return _error(str(e), 402)

    return JsonResponse({
        'success': True,
        'reservas': [
            {'start': r.start_time.isoformat(), 'end': r.end_time.isoformat()}
            for r in reservas
        ],
        'pago': {
            'importe': str(sum(p.amount for p in pagos)),
            'referencia': pagos[0].reference.rsplit('-', 1)[0],
            'tarjeta': str(metodo) if metodo else 'Tarjeta no guardada',
        },
    }, status=201)


def login_view(request):
    """
    Vista para el inicio de sesión de usuarios.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            # Volver a la página que pidió el login, solo si es de este mismo sitio
            next_url = request.GET.get('next', '')
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
                return redirect(next_url)
            return redirect('/')
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")
    return render(request, 'reservas/login.html')


@require_POST
def logout_view(request):
    """
    Cerrar sesión (solo por POST, para que un enlace externo no pueda cerrarla).
    """
    logout(request)
    return redirect('/login/')

def _leer_dia(valor):
    """
    Lee 'YYYY-MM-DD' o el formato con hora que envía FullCalendar
    ('YYYY-MM-DDTHH:MM:SS-05:00'); devuelve la fecha o None si no es válida.
    """
    try:
        return date.fromisoformat((valor or '')[:10])
    except ValueError:
        return None


def _leer_rango(request):
    """
    Devuelve (desde, hasta) de los parámetros start/end (hasta exclusivo),
    (None, None) si no se enviaron, o lanza ValueError si no son válidos.
    """
    if 'start' not in request.GET and 'end' not in request.GET:
        return None, None
    desde = _leer_dia(request.GET.get('start'))
    hasta = _leer_dia(request.GET.get('end'))
    if desde is None or hasta is None or hasta <= desde:
        raise ValueError
    return desde, hasta


def _filtrar_rango(queryset, desde, hasta):
    if desde is None:
        return queryset
    inicio = timezone.make_aware(datetime.combine(desde, time.min))
    fin = timezone.make_aware(datetime.combine(hasta, time.min))
    return queryset.filter(start_time__lt=fin, end_time__gt=inicio)


def api_reservas(request, resource_id):
    """
    Reservas activas (no canceladas) de un recurso en el rango start/end, para FullCalendar.
    No expone quién reservó: las propias se marcan como "Tu reserva".
    """
    try:
        desde, hasta = _leer_rango(request)
    except ValueError:
        return _error('Rango de fechas inválido (start/end en formato YYYY-MM-DD).', 400)

    reservas = _filtrar_rango(
        Booking.objects.activas().filter(resource_id=resource_id), desde, hasta
    ).order_by('start_time')
    eventos = [
        {
            "title": "Tu reserva" if reserva.user_id == request.user.id else "Reservado",
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "color": "#2563eb" if reserva.user_id == request.user.id else "#10b981",
        }
        for reserva in reservas
    ]
    return JsonResponse(eventos, safe=False)


def api_bloqueos(request, resource_id):
    """
    Bloqueos (Availability) de un recurso en el rango start/end, para FullCalendar.
    """
    try:
        desde, hasta = _leer_rango(request)
    except ValueError:
        return _error('Rango de fechas inválido (start/end en formato YYYY-MM-DD).', 400)

    bloqueos = _filtrar_rango(Availability.objects.filter(resource_id=resource_id), desde, hasta)
    eventos = [
        {
            "title": "Bloqueado",
            "start": bloqueo.start_time.isoformat(),
            "end": bloqueo.end_time.isoformat(),
            "color": "#ef4444",
        }
        for bloqueo in bloqueos.order_by('start_time')
    ]
    return JsonResponse(eventos, safe=False)


def api_disponibilidad(request, resource_id):
    """
    Estado de cada día (libre, parcial, completo, pasado) en el rango start/end.
    Máximo MAX_DIAS_RANGO días.
    """
    resource = Resource.objects.filter(pk=resource_id).first()
    if resource is None:
        return _error('La pista no existe.', 404)
    try:
        desde, hasta = _leer_rango(request)
    except ValueError:
        desde = None
    if desde is None:
        return _error('Rango de fechas inválido (start/end en formato YYYY-MM-DD).', 400)
    if (hasta - desde).days > MAX_DIAS_RANGO:
        return _error(f'El rango no puede superar {MAX_DIAS_RANGO} días.', 400)
    return JsonResponse(estado_dias(resource, desde, hasta), safe=False)


def home(request):
    """
    Vista principal que muestra todas las pistas (resources).
    """
    resources = Resource.objects.all()  # Obtenemos todas las pistas
    return render(request, 'reservas/home.html', {'resources': resources})


@login_required
def mis_reservas(request):
    """
    Reservas del usuario actual, separadas en próximas y pasadas.
    """
    ahora = timezone.now()
    reservas = Booking.objects.filter(user=request.user).select_related('resource', 'payment')

    proximas = list(reservas.filter(start_time__gte=ahora).order_by('start_time'))
    for reserva in proximas:
        reserva.cancelable = puede_cancelar(reserva, ahora)
    pasadas = list(reservas.filter(start_time__lt=ahora).order_by('-start_time'))

    return render(request, 'reservas/mis_reservas.html', {
        'proximas': proximas,
        'pasadas': pasadas,
    })


@login_required
@require_POST
def cancelar_reserva(request, booking_id):
    """
    Cancela una reserva del usuario actual. Las reservas de otros usuarios dan 404.
    """
    booking = get_object_or_404(Booking.objects.select_related('resource'),
                                pk=booking_id, user=request.user)
    try:
        cancelar_reserva_servicio(booking)
    except CancelacionNoPermitida as e:
        messages.error(request, str(e))
    else:
        inicio = timezone.localtime(booking.start_time)
        messages.success(
            request,
            f'Reserva de {booking.resource.name} del {inicio:%d/%m/%Y a las %H:%M} cancelada. '
            'La franja vuelve a estar disponible.'
        )
    return redirect('mis_reservas')



@login_required
def mis_tarjetas(request):
    """
    Tarjetas guardadas del usuario (solo marca, últimos 4 y vencimiento).
    """
    return render(request, 'reservas/mis_tarjetas.html', {
        'tarjetas': PaymentMethod.objects.filter(user=request.user).order_by('-created_at'),
    })


@login_required
@require_POST
def eliminar_tarjeta(request, tarjeta_id):
    """
    Elimina una tarjeta guardada del usuario. Las de otros usuarios dan 404.
    Los pagos ya hechos se conservan (quedan sin tarjeta asociada).
    """
    tarjeta = get_object_or_404(PaymentMethod, pk=tarjeta_id, user=request.user)
    descripcion = str(tarjeta)
    tarjeta.delete()
    messages.success(request, f'Se eliminó la tarjeta {descripcion}.')
    return redirect('mis_tarjetas')

SEMANAS_HISTORICO = 12
VENTANA_PREVISION = 4
HORIZONTE_PREVISION = 4


@staff_member_required
def panel_demanda(request):
    """
    Panel para el administrador: histórico semanal, previsión por promedio móvil
    y ocupación por día de la semana y hora. Se puede filtrar por pista (?pista=<id>).
    """
    pista = None
    pista_id = request.GET.get('pista')
    if pista_id:
        if not pista_id.isdigit():
            raise Http404
        pista = get_object_or_404(Resource, pk=pista_id)

    semanas = reservas_por_semana(pista, SEMANAS_HISTORICO)
    serie = [s['total'] for s in semanas]
    prevision = prevision_promedio_movil(serie, VENTANA_PREVISION, HORIZONTE_PREVISION)
    hoy = timezone.localdate()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    semanas_futuras = [(lunes_actual + timedelta(weeks=i)).isoformat() for i in range(HORIZONTE_PREVISION)]

    # Mapa de calor: intensidad de cada celda respecto al máximo
    ocupacion = ocupacion_por_dia_hora(pista)
    maximo = max((v for fila in ocupacion['matriz'] for v in fila), default=0) or 1
    filas_calor = [
        (dia, [(v, round(v / maximo, 2)) for v in fila])
        for dia, fila in zip(ocupacion['dias'], ocupacion['matriz'])
    ]
    franja_top = None
    if any(v for fila in ocupacion['matriz'] for v in fila):
        _, d, h = max((v, d, h) for d, fila in enumerate(ocupacion['matriz']) for h, v in enumerate(fila))
        franja_top = f"{ocupacion['dias'][d]} a las {ocupacion['horas'][h]:02d}:00"

    return render(request, 'reservas/panel_demanda.html', {
        'pistas': Resource.objects.order_by('name'),
        'pista': pista,
        'semanas': semanas,
        'prevision': prevision,
        'total_historico': sum(serie),
        'promedio_ventana': prevision[0] if prevision else 0,
        'ventana': VENTANA_PREVISION,
        'semanas_historico': SEMANAS_HISTORICO,
        'horas': ocupacion['horas'],
        'filas_calor': filas_calor,
        'franja_top': franja_top,
        'datos_grafico': {
            'etiquetas': [s['semana'] for s in semanas] + semanas_futuras,
            'historico': serie + [None] * HORIZONTE_PREVISION,
            # La línea de previsión arranca en la última semana real para que se vean unidas
            'prevision': [None] * (len(serie) - 1) + ([serie[-1]] if serie else []) + prevision,
        },
    })
