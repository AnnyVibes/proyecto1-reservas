from django.contrib import admin
from .models import Resource, Availability, Booking, Payment, PaymentMethod

# --- CONFIGURACIÓN DEL PANEL ADMIN ---

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price_per_hour', 'description')  # Columnas que veremos en el admin
    search_fields = ('name',)                     # Buscar recursos por nombre


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ('id', 'resource', 'start_time', 'end_time')
    list_filter = ('resource',)                   # Filtro por recurso
    search_fields = ('resource__name',)
    verbose_name = 'Bloqueo'
    verbose_name_plural = 'Bloqueos'


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'resource', 'start_time', 'end_time', 'status', 'created_at')
    list_filter = ('status', 'resource', 'user')
    search_fields = ('user__username', 'resource__name')


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    # Solo datos no sensibles: nunca existe el número completo ni el CVV
    list_display = ('id', 'user', 'brand', 'last4', 'exp_month', 'exp_year', 'created_at')
    list_filter = ('brand',)
    search_fields = ('user__username', 'holder_name', 'last4')
    readonly_fields = ('token', 'created_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'booking', 'amount', 'status', 'payment_method', 'created_at')
    list_filter = ('status',)
    search_fields = ('reference', 'booking__user__username')
    readonly_fields = ('booking', 'payment_method', 'amount', 'status', 'reference', 'created_at')

