import uuid
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class Resource(models.Model):
    """Recurso que puede reservarse (pistas, salas, etc.)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('10.00'))

    def __str__(self):
        return self.name


class Availability(models.Model):
    """Horarios disponibles para cada recurso."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='availabilities')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    def __str__(self):
        return f"{self.resource.name} - {self.start_time} a {self.end_time}"
    
    class Meta:
        verbose_name = 'Bloqueo'
        verbose_name_plural = 'Bloqueos'


class BookingQuerySet(models.QuerySet):
    def activas(self):
        """Reservas que ocupan la franja (excluye las canceladas)."""
        return self.filter(status=Booking.Status.CONFIRMADA)


class Booking(models.Model):
    """Reserva de un recurso por un usuario."""

    class Status(models.TextChoices):
        CONFIRMADA = 'confirmada', 'Confirmada'
        CANCELADA = 'cancelada', 'Cancelada'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='bookings')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMADA)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    objects = BookingQuerySet.as_manager()

    def __str__(self):
        return f"Reserva de {self.resource.name} por {self.user.username}"

    def clean(self):
        """
        Validación para evitar que la reserva se solape con otra reserva o con un bloqueo.
        """
        # Import local para evitar una importación circular (el servicio importa los modelos)
        from reservas.services.reservas import hay_conflicto

        # Excluimos la propia reserva al editar
        if hay_conflicto(self.resource, self.start_time, self.end_time, excluir_id=self.pk):
            raise ValidationError("La franja horaria ya está reservada o bloqueada.")

    class Meta:
        # Solo una reserva confirmada por franja: una cancelada no impide volver a reservarla
        constraints = [
            models.UniqueConstraint(
                fields=['resource', 'start_time', 'end_time'],
                condition=models.Q(status='confirmada'),
                name='reserva_confirmada_unica_por_franja',
            ),
        ]


class PaymentMethod(models.Model):
    """
    Tarjeta guardada para pagos SIMULADOS. Nunca se guarda el número completo
    ni el CVV: solo titular, marca, últimos 4 dígitos, vencimiento y un token.
    """

    class Brand(models.TextChoices):
        VISA = 'visa', 'Visa'
        MASTERCARD = 'mastercard', 'Mastercard'
        AMEX = 'amex', 'American Express'
        OTRA = 'otra', 'Otra'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods')
    holder_name = models.CharField(max_length=100)
    brand = models.CharField(max_length=20, choices=Brand.choices)
    last4 = models.CharField(max_length=4)
    exp_month = models.PositiveSmallIntegerField()
    exp_year = models.PositiveSmallIntegerField()
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tarjeta guardada'
        verbose_name_plural = 'Tarjetas guardadas'

    def __str__(self):
        return f"{self.get_brand_display()} terminada en {self.last4}"


class Payment(models.Model):
    """Pago simulado de una reserva."""

    class Status(models.TextChoices):
        APROBADO = 'aprobado', 'Aprobado'
        RECHAZADO = 'rechazado', 'Rechazado'

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices)
    reference = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'

    def __str__(self):
        return f"{self.reference} · {self.amount} ({self.get_status_display()})"

