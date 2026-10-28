import json
from datetime import datetime, timedelta, time
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Resource, Booking, Availability
from .services.reservas import (
    CancelacionNoPermitida, ConflictoHorario, ReservaInvalida,
    cancelar_reserva as cancelar_reserva_servicio, crear_reservas, puede_cancelar,
)


# Horario por defecto (si no hay Availability definida)
DEFAULT_START = time(9, 0)   # 09:00
DEFAULT_END = time(21, 0)    # 21:00


def calendario(request, resource_id):
    """
    Muestra un calendario semanal de reservas para un recurso.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = datetime.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # Lunes
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.filter(
        resource=resource,
        start_time__date__gte=inicio_semana,
        start_time__date__lte=inicio_semana + timedelta(days=6)
    ).order_by('start_time')

    reservas_por_dia = {date_format(dia, 'Y-m-d'): [] for dia in dias_semana}
    for reserva in reservas:
        clave = date_format(reserva.start_time, 'Y-m-d')
        reservas_por_dia[clave].append(reserva)

    return render(request, 'reservas/calendario.html', {
        'resource': resource,
        'dias_semana': dias_semana,
        'reservas_por_dia': reservas_por_dia,
    })


def calendario_navegable(request, resource_id):
    """
    Calendario semanal con botones de semana anterior/siguiente.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = datetime.today()
    delta = 0
    if request.GET.get('week') == 'prev':
        delta = -7
    elif request.GET.get('week') == 'next':
        delta = 7

    inicio_semana = (hoy - timedelta(days=hoy.weekday())) + timedelta(days=delta)
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.filter(
        resource=resource,
        start_time__date__gte=inicio_semana,
        start_time__date__lte=inicio_semana + timedelta(days=6)
    ).order_by('start_time')

    reservas_por_dia = {date_format(dia, 'Y-m-d'): [] for dia in dias_semana}
    for reserva in reservas:
        clave = date_format(reserva.start_time, 'Y-m-d')
        reservas_por_dia[clave].append(reserva)

    return render(request, 'reservas/calendario.html', {
        'resource': resource,
        'dias_semana': dias_semana,
        'reservas_por_dia': reservas_por_dia,
    })


def calendario_full(request, resource_id):
    """
    Calendario interactivo con FullCalendar.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    reservas = Booking.objects.activas().filter(resource=resource).order_by('start_time')
    bloqueos = Availability.objects.filter(resource=resource)

    # Lista de reservas
    reservas_json = [
        {
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "title": f"Reservado por {reserva.user.username}",
            "color": "#10b981",  # Verde reservas
        }
        for reserva in reservas
    ]

    # Lista de bloqueos (rojo)
    bloqueos_json = [
        {
            "start": bloqueo.start_time.isoformat(),
            "end": bloqueo.end_time.isoformat(),
        }
        for bloqueo in bloqueos
    ]

    return render(request, 'reservas/calendario_full.html', {
        'resource': resource,
        'reservas_json': json.dumps(reservas_json),
        'bloqueos_json': json.dumps(bloqueos_json),
        'is_authenticated': request.user.is_authenticated,
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

    try:
        reservas = crear_reservas(request.user, resource, inicio, fin, repeat_weeks)
    except ReservaInvalida as e:
        return _error(str(e), 400)
    except ConflictoHorario as e:
        return _error(str(e), 409)

    return JsonResponse({
        'success': True,
        'reservas': [
            {'start': r.start_time.isoformat(), 'end': r.end_time.isoformat()}
            for r in reservas
        ],
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


def logout_view(request):
    """
    Cerrar sesión.
    """
    logout(request)
    return redirect('/login/')

def api_reservas(request, resource_id):
    """
    API que devuelve las reservas activas (no canceladas) de un recurso en formato JSON.
    """
    reservas = Booking.objects.activas().filter(resource_id=resource_id).order_by('start_time')
    eventos = [
        {
            "title": f"Reservado por {reserva.user.username}",
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "color": "#10b981",  # Verde
        }
        for reserva in reservas
    ]
    return JsonResponse(eventos, safe=False)

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
    reservas = Booking.objects.filter(user=request.user).select_related('resource')

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


