from datetime import datetime, time, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservas.models import Booking, Resource
from reservas.services.demanda import (
    ocupacion_por_dia_hora, prevision_promedio_movil, reservas_por_semana,
)


def momento(dia, hora):
    return timezone.make_aware(datetime.combine(dia, time(hora, 0)))


class PrevisionPromedioMovilTests(TestCase):
    def test_serie_conocida(self):
        """Cada semana futura es el promedio de las últimas 4 semanas reales (previsión plana)."""
        self.assertEqual(prevision_promedio_movil([10, 12, 14, 16]), [13.0, 13.0, 13.0, 13.0])

    def test_usa_solo_las_ultimas_semanas_de_la_ventana(self):
        """Solo cuentan las últimas `ventana` semanas."""
        self.assertEqual(prevision_promedio_movil([100, 0, 2, 4, 6], ventana=2, horizonte=3),
                         [5.0, 5.0, 5.0])

    def test_ventana_mayor_que_la_serie(self):
        """Si hay menos semanas que la ventana, se promedian las disponibles."""
        self.assertEqual(prevision_promedio_movil([4, 6], ventana=4, horizonte=2), [5.0, 5.0])

    def test_serie_vacia(self):
        """Sin datos, la previsión es 0."""
        self.assertEqual(prevision_promedio_movil([], horizonte=2), [0.0, 0.0])


class AgregacionesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.pista = Resource.objects.create(name='Pista 1')
        self.otra = Resource.objects.create(name='Pista 2')
        hoy = timezone.localdate()
        self.lunes_actual = hoy - timedelta(days=hoy.weekday())

    def reservar(self, dia, hora, horas=1, resource=None, **kwargs):
        return Booking.objects.create(user=self.user, resource=resource or self.pista,
                                      start_time=momento(dia, hora),
                                      end_time=momento(dia, hora + horas), **kwargs)

    def test_reservas_por_semana_con_datos_controlados(self):
        """Agrupa por semana (lunes) las últimas semanas completas, con ceros y sin canceladas."""
        semana_1 = self.lunes_actual - timedelta(weeks=1)
        semana_3 = self.lunes_actual - timedelta(weeks=3)
        self.reservar(semana_1, 10)
        self.reservar(semana_1 + timedelta(days=6), 20)          # domingo de esa semana
        self.reservar(semana_1, 12, status=Booking.Status.CANCELADA)
        self.reservar(semana_3 + timedelta(days=2), 9)
        self.reservar(self.lunes_actual, 9)                      # semana actual: no cuenta
        self.reservar(semana_1, 11, resource=self.otra)          # otra pista

        self.assertEqual(reservas_por_semana(self.pista, semanas=3), [
            {'semana': semana_3.isoformat(), 'total': 1},
            {'semana': (self.lunes_actual - timedelta(weeks=2)).isoformat(), 'total': 0},
            {'semana': semana_1.isoformat(), 'total': 2},
        ])
        # Sin filtro de pista se suman todas
        self.assertEqual(reservas_por_semana(None, semanas=1)[0]['total'], 3)

    def test_ocupacion_por_dia_hora(self):
        """Cuenta cada franja ocupada en la matriz día de la semana × hora (9–20)."""
        martes = self.lunes_actual - timedelta(weeks=1) + timedelta(days=1)
        self.reservar(martes, 10, horas=2)                       # ocupa 10:00 y 11:00
        self.reservar(martes, 15, status=Booking.Status.CANCELADA)

        ocupacion = ocupacion_por_dia_hora(self.pista)
        self.assertEqual(ocupacion['horas'], list(range(9, 21)))
        self.assertEqual(len(ocupacion['matriz']), 7)
        self.assertEqual(ocupacion['matriz'][1][1], 1)            # martes 10:00
        self.assertEqual(ocupacion['matriz'][1][2], 1)            # martes 11:00
        self.assertEqual(sum(sum(fila) for fila in ocupacion['matriz']), 2)


class PanelDemandaTests(TestCase):
    def setUp(self):
        self.pista = Resource.objects.create(name='Pista 1')
        self.url = reverse('panel_demanda')

    def test_usuario_no_staff_es_redirigido(self):
        """Un usuario sin permisos de staff no puede ver el panel (redirige al login del admin)."""
        user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_staff_accede(self):
        """Un usuario staff ve el panel con los datos de los gráficos y la explicación del método."""
        staff = User.objects.create_user(username='admin', password='clave-segura-123', is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['prevision']), 4)
        self.assertContains(response, 'promedio móvil')
        self.assertContains(response, 'chart.umd.min.js')

    def test_filtro_por_pista(self):
        """El panel se puede filtrar por pista; una pista inexistente da 404."""
        staff = User.objects.create_user(username='admin', password='clave-segura-123', is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(self.url, {'pista': self.pista.id})
        self.assertEqual(response.context['pista'], self.pista)
        self.assertEqual(self.client.get(self.url, {'pista': 99999}).status_code, 404)

    def test_enlace_al_panel_solo_para_staff(self):
        """La barra muestra el enlace al panel solo a usuarios staff."""
        user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse('home')), f'href="{self.url}"')
        user.is_staff = True
        user.save()
        self.assertContains(self.client.get(reverse('home')), f'href="{self.url}"')


class ComandosDatosTests(TestCase):
    def setUp(self):
        self.pista = Resource.objects.create(name='Pista 1')
        self.ana = User.objects.create_user(username='ana', password='clave-segura-123')
        manana = timezone.localdate() + timedelta(days=1)
        self.reserva_real = Booking.objects.create(user=self.ana, resource=self.pista,
                                                   start_time=momento(manana, 10),
                                                   end_time=momento(manana, 11))

    def generar(self, *args):
        call_command('generar_historico', *args, stdout=StringIO())
        return Booking.objects.filter(user__username='demo_historico')

    def test_generar_historico_crea_reservas_pasadas_reproducibles(self):
        """generar_historico crea reservas pasadas de demo_historico y con la misma semilla da lo mismo."""
        historico = self.generar('--semanas', '2', '--seed', '42')
        self.assertGreater(historico.count(), 0)
        self.assertFalse(historico.filter(start_time__gte=timezone.now()).exists())
        primeras = sorted(historico.values_list('resource_id', 'start_time'))

        historico = self.generar('--semanas', '2', '--seed', '42', '--reset')
        self.assertEqual(sorted(historico.values_list('resource_id', 'start_time')), primeras)

    def test_generar_historico_no_solapa_reservas(self):
        """El histórico no crea dos reservas en la misma franja de una pista."""
        historico = self.generar('--semanas', '3', '--seed', '7')
        franjas = list(historico.values_list('resource_id', 'start_time'))
        self.assertEqual(len(franjas), len(set(franjas)))

    def test_reset_solo_borra_el_historico(self):
        """--reset borra solo las reservas de demo_historico, nunca las de otros usuarios."""
        self.generar('--semanas', '1', '--seed', '1')
        call_command('generar_historico', '--semanas', '0', '--reset', stdout=StringIO())
        self.assertFalse(Booking.objects.filter(user__username='demo_historico').exists())
        self.assertTrue(Booking.objects.filter(pk=self.reserva_real.pk).exists())

    def test_crear_reservas_demo_no_borra_reservas_ajenas(self):
        """crear_reservas_demo ya no borra las reservas de los demás usuarios."""
        call_command('crear_reservas_demo', stdout=StringIO())
        self.assertTrue(Booking.objects.filter(pk=self.reserva_real.pk).exists())
        self.assertTrue(Booking.objects.filter(user__username='demo_user').exists())
