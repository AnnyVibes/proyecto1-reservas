from datetime import datetime, time, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservas.models import Availability, Booking, Resource
from reservas.services.disponibilidad import estado_dias


def momento(dia, hora):
    """Datetime con zona para la fecha `dia` a la `hora` indicada (hora local)."""
    return timezone.make_aware(datetime.combine(dia, time(hora, 0)))


class EstadoDiasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.resource = Resource.objects.create(name='Pista 1')
        self.manana = timezone.localdate() + timedelta(days=1)

    def reservar(self, dia, desde, hasta, **kwargs):
        return Booking.objects.create(user=self.user, resource=self.resource,
                                      start_time=momento(dia, desde), end_time=momento(dia, hasta),
                                      **kwargs)

    def estado(self, dia):
        return estado_dias(self.resource, dia, dia + timedelta(days=1))[0]

    def test_dia_libre(self):
        """Un día futuro sin reservas está libre con las 12 franjas disponibles."""
        self.assertEqual(self.estado(self.manana), {
            'fecha': self.manana.isoformat(), 'estado': 'libre', 'libres': 12, 'total': 12,
        })

    def test_dia_parcial(self):
        """Un día con alguna franja ocupada está parcial."""
        self.reservar(self.manana, 10, 11)
        estado = self.estado(self.manana)
        self.assertEqual(estado['estado'], 'parcial')
        self.assertEqual(estado['libres'], 11)

    def test_dia_completo(self):
        """Un día con las 12 franjas ocupadas está completo."""
        self.reservar(self.manana, 9, 21)
        estado = self.estado(self.manana)
        self.assertEqual(estado['estado'], 'completo')
        self.assertEqual(estado['libres'], 0)

    def test_dia_pasado(self):
        """Un día anterior a hoy está en estado pasado."""
        ayer = timezone.localdate() - timedelta(days=1)
        self.assertEqual(self.estado(ayer)['estado'], 'pasado')

    def test_bloqueo_ocupa_franjas(self):
        """Un bloqueo (Availability) ocupa las franjas que solapa."""
        Availability.objects.create(resource=self.resource,
                                    start_time=momento(self.manana, 9), end_time=momento(self.manana, 12))
        estado = self.estado(self.manana)
        self.assertEqual(estado['estado'], 'parcial')
        self.assertEqual(estado['libres'], 9)

    def test_bloqueo_de_todo_el_dia_lo_completa(self):
        """Un bloqueo que cubre todo el horario deja el día completo."""
        Availability.objects.create(resource=self.resource,
                                    start_time=momento(self.manana, 0),
                                    end_time=momento(self.manana + timedelta(days=1), 0))
        self.assertEqual(self.estado(self.manana)['estado'], 'completo')

    def test_reserva_cancelada_no_ocupa(self):
        """Una reserva cancelada no ocupa la franja."""
        self.reservar(self.manana, 10, 11, status=Booking.Status.CANCELADA)
        self.assertEqual(self.estado(self.manana)['estado'], 'libre')

    def test_reserva_de_otra_pista_no_ocupa(self):
        """Las reservas de otra pista no afectan a esta."""
        otra = Resource.objects.create(name='Pista 2')
        Booking.objects.create(user=self.user, resource=otra,
                               start_time=momento(self.manana, 10), end_time=momento(self.manana, 11))
        self.assertEqual(self.estado(self.manana)['estado'], 'libre')

    def test_hoy_las_franjas_pasadas_no_cuentan_como_libres(self):
        """Hoy, las franjas que ya empezaron no cuentan como libres."""
        hoy = timezone.localdate()
        with mock.patch('django.utils.timezone.now', return_value=momento(hoy, 15)):
            estado = estado_dias(self.resource, hoy, hoy + timedelta(days=1))[0]
        self.assertEqual(estado['libres'], 6)  # de 15:00 a 21:00
        self.assertEqual(estado['estado'], 'parcial')

    def test_un_resultado_por_dia_del_rango(self):
        """Devuelve un elemento por cada día del rango [desde, hasta)."""
        dias = estado_dias(self.resource, self.manana, self.manana + timedelta(days=7))
        self.assertEqual(len(dias), 7)
        self.assertEqual(dias[-1]['fecha'], (self.manana + timedelta(days=6)).isoformat())


class ApiDisponibilidadTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(name='Pista 1')
        self.manana = timezone.localdate() + timedelta(days=1)

    def get(self, resource_id=None, **params):
        url = reverse('api_disponibilidad', args=[resource_id or self.resource.id])
        return self.client.get(url, params)

    def test_rango_valido(self):
        """Con un rango válido devuelve un estado por día (200)."""
        response = self.get(start=self.manana.isoformat(),
                            end=(self.manana + timedelta(days=3)).isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual([d['fecha'] for d in response.json()],
                         [(self.manana + timedelta(days=i)).isoformat() for i in range(3)])

    def test_acepta_fechas_con_hora_de_fullcalendar(self):
        """Acepta el formato con hora y zona que envía FullCalendar."""
        response = self.get(start=f'{self.manana.isoformat()}T00:00:00-05:00',
                            end=f'{(self.manana + timedelta(days=1)).isoformat()}T00:00:00-05:00')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_rango_invalido_devuelve_400(self):
        """Fechas ausentes, mal formadas, invertidas o de más de 62 días → 400."""
        casos = {
            'sin parametros': {},
            'mal formada': {'start': 'ayer', 'end': '2026-13-01'},
            'invertido': {'start': self.manana.isoformat(), 'end': self.manana.isoformat()},
            'mas de 62 dias': {'start': self.manana.isoformat(),
                               'end': (self.manana + timedelta(days=63)).isoformat()},
        }
        for nombre, params in casos.items():
            with self.subTest(nombre):
                self.assertEqual(self.get(**params).status_code, 400)

    def test_pista_inexistente_devuelve_404(self):
        """Una pista que no existe devuelve 404."""
        response = self.get(resource_id=99999, start=self.manana.isoformat(),
                            end=(self.manana + timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 404)


class ApiReservasYBloqueosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.otro = User.objects.create_user(username='luis', password='clave-segura-123')
        self.resource = Resource.objects.create(name='Pista 1')
        self.dia = timezone.localdate() + timedelta(days=2)
        self.mia = Booking.objects.create(user=self.user, resource=self.resource,
                                          start_time=momento(self.dia, 10), end_time=momento(self.dia, 11))
        self.ajena = Booking.objects.create(user=self.otro, resource=self.resource,
                                            start_time=momento(self.dia, 12), end_time=momento(self.dia, 13))
        self.lejana = Booking.objects.create(user=self.user, resource=self.resource,
                                             start_time=momento(self.dia + timedelta(days=30), 10),
                                             end_time=momento(self.dia + timedelta(days=30), 11))

    def test_api_reservas_filtra_por_rango(self):
        """api_reservas solo devuelve las reservas dentro del rango start/end."""
        response = self.client.get(reverse('api_reservas', args=[self.resource.id]), {
            'start': self.dia.isoformat(), 'end': (self.dia + timedelta(days=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_api_reservas_rango_invalido_devuelve_400(self):
        """api_reservas con un rango mal formado devuelve 400."""
        response = self.client.get(reverse('api_reservas', args=[self.resource.id]),
                                   {'start': 'x', 'end': 'y'})
        self.assertEqual(response.status_code, 400)

    def test_api_reservas_no_expone_nombres_de_otros_usuarios(self):
        """El calendario no muestra quién hizo cada reserva ajena; las propias se marcan."""
        self.client.force_login(self.user)
        eventos = self.client.get(reverse('api_reservas', args=[self.resource.id]), {
            'start': self.dia.isoformat(), 'end': (self.dia + timedelta(days=1)).isoformat(),
        }).json()
        titulos = sorted(e['title'] for e in eventos)
        self.assertEqual(titulos, ['Reservado', 'Tu reserva'])
        self.assertNotIn('luis', str(eventos))

    def test_api_bloqueos_filtra_por_rango(self):
        """api_bloqueos devuelve los bloqueos del rango para pintarlos en el calendario."""
        Availability.objects.create(resource=self.resource,
                                    start_time=momento(self.dia, 15), end_time=momento(self.dia, 17))
        Availability.objects.create(resource=self.resource,
                                    start_time=momento(self.dia + timedelta(days=40), 15),
                                    end_time=momento(self.dia + timedelta(days=40), 17))
        response = self.client.get(reverse('api_bloqueos', args=[self.resource.id]), {
            'start': self.dia.isoformat(), 'end': (self.dia + timedelta(days=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['title'], 'Bloqueado')

    def test_calendario_carga_vista_mensual_en_espanol(self):
        """El calendario empieza en vista mensual, carga el idioma español y la leyenda."""
        html = self.client.get(reverse('calendario_full', args=[self.resource.id])).content.decode()
        self.assertIn("initialView: 'dayGridMonth'", html)
        self.assertIn('locales-all.global.min.js', html)
        self.assertIn('id="leyenda"', html)
