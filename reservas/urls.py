from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path('', views.home, name='home'),  # Página principal
    # Vista antigua: redirige al calendario interactivo
    path('calendario/<int:resource_id>/', RedirectView.as_view(pattern_name='calendario_full'), name='calendario'),
    path('calendario_full/<int:resource_id>/', views.calendario_full, name='calendario_full'),
    path('api/reservas/<int:resource_id>/', views.api_reservas, name='api_reservas'),
    path('api/reservas/crear/', views.api_crear_reserva, name='api_crear_reserva'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('reservas/<int:booking_id>/cancelar/', views.cancelar_reserva, name='cancelar_reserva'),



]
