from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class Resource(models.Model):
    """Recurso que puede reservarse (pistas, salas, etc.)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

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
