import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from reservas.models import Booking, Payment, PaymentMethod, Resource
from reservas.services.pagos import PagoInvalido, detectar_marca, luhn_valido, validar_tarjeta
from reservas.tests.test_api_crear_reserva import TARJETA_DE_PRUEBA, franja

NUMERO = '4242424242424242'
RECHAZADA = '4000 0000 0000 0002'


class ValidacionTarjetaTests(TestCase):
    def test_luhn(self):
        """El algoritmo de Luhn acepta números válidos y rechaza los alterados."""
        self.assertTrue(luhn_valido('4242424242424242'))
        self.assertTrue(luhn_valido('4000000000000002'))
        self.assertFalse(luhn_valido('4242424242424241'))

    def test_detectar_marca(self):
        """Detecta visa, mastercard (51–55 y 2221–2720), amex (34/37) u otra."""
        casos = {
            '4242424242424242': 'visa', '5555555555554444': 'mastercard',
            '2221000000000009': 'mastercard', '2720990000000007': 'mastercard',
            '378282246310005': 'amex', '341111111111111': 'amex', '6011111111111117': 'otra',
        }
        for numero, marca in casos.items():
            with self.subTest(numero=numero):
                self.assertEqual(detectar_marca(numero), marca)

    def test_validar_tarjeta(self):
        """Rechaza tarjetas vencidas, mes inválido, CVV incorrecto y números que no pasan Luhn."""
        hoy = timezone.localdate()
        validar_tarjeta(NUMERO, hoy.month, hoy.year, '123')   # vence este mes: aún vale
        invalidas = {
            'vencida': (NUMERO, 1, hoy.year - 1, '123'),
            'mes 13': (NUMERO, 13, hoy.year + 1, '123'),
            'cvv corto': (NUMERO, 12, hoy.year + 1, '12'),
            'cvv con letras': (NUMERO, 12, hoy.year + 1, '12a'),
            'luhn': ('4242424242424241', 12, hoy.year + 1, '123'),
            'demasiado corto': ('4242', 12, hoy.year + 1, '123'),
        }
        for nombre, datos in invalidas.items():
            with self.subTest(nombre):
                with self.assertRaises(PagoInvalido):
                    validar_tarjeta(*datos)


class ReservaConPagoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.otro = User.objects.create_user(username='luis', password='clave-segura-123')
        self.resource = Resource.objects.create(name='Pista 1')
        self.client.force_login(self.user)
        self.inicio = franja(1, 10)
        self.fin = self.inicio + timedelta(hours=1)

    def reservar(self, **extra):
        datos = {
            'resource_id': self.resource.id,
            'start_time': self.inicio.isoformat(),
            'end_time': self.fin.isoformat(),
            'repeat_weeks': 0,
        }
        datos.update(extra)
        return self.client.post(reverse('api_crear_reserva'), json.dumps(datos),
                                content_type='application/json')

    def metodo(self, user=None):
        return PaymentMethod.objects.create(user=user or self.user, holder_name='Ana Prueba',
                                            brand='visa', last4='4242', exp_month=12,
                                            exp_year=timezone.localdate().year + 2)

    def test_tarjeta_nueva_sin_guardar(self):
        """Con una tarjeta nueva se crea la reserva y un pago aprobado; no se guarda la tarjeta."""
        response = self.reservar(tarjeta=TARJETA_DE_PRUEBA, guardar=False)
        self.assertEqual(response.status_code, 201)
        pago = Payment.objects.get()
        self.assertEqual(pago.status, Payment.Status.APROBADO)
        self.assertEqual(pago.amount, Decimal('10.00'))
        self.assertEqual(pago.booking.user, self.user)
        self.assertFalse(PaymentMethod.objects.exists())
        self.assertEqual(response.json()['pago']['importe'], '10.00')

    def test_guardar_tarjeta_solo_guarda_datos_no_sensibles(self):
        """Al guardar la tarjeta solo se guardan titular, marca, últimos 4, vencimiento y token."""
        response = self.reservar(tarjeta=TARJETA_DE_PRUEBA, guardar=True)
        self.assertEqual(response.status_code, 201)
        metodo = PaymentMethod.objects.get()
        self.assertEqual((metodo.user, metodo.brand, metodo.last4), (self.user, 'visa', '4242'))
        self.assertIsNotNone(metodo.token)
        self.assertEqual(Payment.objects.get().payment_method, metodo)

    def test_guardar_la_misma_tarjeta_no_la_duplica(self):
        """Guardar otra vez la misma tarjeta reutiliza la ya guardada (sin duplicados)."""
        self.reservar(tarjeta=TARJETA_DE_PRUEBA, guardar=True)
        self.inicio, self.fin = franja(1, 12), franja(1, 13)
        self.assertEqual(self.reservar(tarjeta=TARJETA_DE_PRUEBA, guardar=True).status_code, 201)
        self.assertEqual(PaymentMethod.objects.count(), 1)
        self.assertEqual(Payment.objects.filter(payment_method__isnull=False).count(), 2)

    def test_numero_completo_y_cvv_no_se_guardan_en_la_bd(self):
        """Ni el número completo ni el CVV aparecen en ningún dato de la BD."""
        self.reservar(tarjeta=TARJETA_DE_PRUEBA, guardar=True)
        salida = StringIO()
        call_command('dumpdata', stdout=salida)
        volcado = salida.getvalue()
        self.assertNotIn(NUMERO, volcado)
        self.assertNotIn('4242 4242 4242 4242', volcado)
        for modelo in (PaymentMethod, Payment):
            for fila in modelo.objects.values():
                with self.subTest(modelo=modelo.__name__):
                    self.assertNotIn(TARJETA_DE_PRUEBA['cvv'], [str(v) for v in fila.values()])

    def test_reserva_con_tarjeta_guardada(self):
        """Se puede pagar con una tarjeta guardada propia."""
        metodo = self.metodo()
        response = self.reservar(payment_method_id=metodo.id)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.get().payment_method, metodo)

    def test_tarjeta_guardada_de_otro_usuario_devuelve_404(self):
        """Usar la tarjeta guardada de otro usuario devuelve 404 y no crea la reserva."""
        ajena = self.metodo(user=self.otro)
        response = self.reservar(payment_method_id=ajena.id)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Booking.objects.exists())

    def test_tarjeta_rechazada_no_crea_reserva(self):
        """La tarjeta de prueba 4000 0000 0000 0002 se rechaza: no se crea reserva, pago ni tarjeta."""
        rechazada = dict(TARJETA_DE_PRUEBA, numero=RECHAZADA)
        response = self.reservar(tarjeta=rechazada, guardar=True)
        self.assertEqual(response.status_code, 402)
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(PaymentMethod.objects.exists())

    def test_tarjeta_invalida_devuelve_400(self):
        """Una tarjeta que no pasa la validación devuelve 400 sin crear nada."""
        response = self.reservar(tarjeta=dict(TARJETA_DE_PRUEBA, numero='4242424242424241'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Booking.objects.exists())
        self.assertNotIn('4242424242424241', response.content.decode())

    def test_sin_metodo_de_pago_devuelve_400(self):
        """Reservar sin indicar un método de pago devuelve 400."""
        self.assertEqual(self.reservar().status_code, 400)
        self.assertFalse(Booking.objects.exists())

    def test_importe_segun_precio_horas_y_semanas(self):
        """El importe es precio por hora × horas, con un pago por cada semana reservada."""
        self.resource.price_per_hour = Decimal('15.50')
        self.resource.save()
        self.fin = self.inicio + timedelta(hours=2)
        response = self.reservar(tarjeta=TARJETA_DE_PRUEBA, repeat_weeks=2)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(sorted(Payment.objects.values_list('amount', flat=True)), [Decimal('31.00')] * 3)
        self.assertEqual(response.json()['pago']['importe'], '93.00')

    def test_conflicto_no_cobra(self):
        """Si la franja está ocupada (409) no se crea ningún pago."""
        Booking.objects.create(user=self.otro, resource=self.resource, start_time=self.inicio, end_time=self.fin)
        response = self.reservar(tarjeta=TARJETA_DE_PRUEBA)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Payment.objects.exists())


class MisTarjetasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ana', password='clave-segura-123')
        self.otro = User.objects.create_user(username='luis', password='clave-segura-123')
        self.client.force_login(self.user)
        anio = timezone.localdate().year + 2
        self.mia = PaymentMethod.objects.create(user=self.user, holder_name='Ana', brand='visa',
                                                last4='4242', exp_month=12, exp_year=anio)
        self.ajena = PaymentMethod.objects.create(user=self.otro, holder_name='Luis', brand='amex',
                                                  last4='0005', exp_month=12, exp_year=anio)

    def test_lista_solo_las_tarjetas_propias(self):
        """Mis tarjetas muestra solo las tarjetas del usuario."""
        response = self.client.get(reverse('mis_tarjetas'))
        self.assertEqual(list(response.context['tarjetas']), [self.mia])
        self.assertContains(response, '4242')
        self.assertNotContains(response, '0005')

    def test_eliminar_tarjeta_propia(self):
        """El usuario puede eliminar su tarjeta guardada."""
        response = self.client.post(reverse('eliminar_tarjeta', args=[self.mia.id]), follow=True)
        self.assertRedirects(response, reverse('mis_tarjetas'))
        self.assertFalse(PaymentMethod.objects.filter(pk=self.mia.pk).exists())

    def test_eliminar_tarjeta_ajena_devuelve_404(self):
        """No se puede eliminar la tarjeta de otro usuario (404)."""
        response = self.client.post(reverse('eliminar_tarjeta', args=[self.ajena.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PaymentMethod.objects.filter(pk=self.ajena.pk).exists())

    def test_eliminar_solo_por_post(self):
        """Eliminar una tarjeta solo acepta POST (405 con GET)."""
        response = self.client.get(reverse('eliminar_tarjeta', args=[self.mia.id]))
        self.assertEqual(response.status_code, 405)

    def test_mis_tarjetas_exige_sesion(self):
        """Mis tarjetas exige sesión."""
        self.client.logout()
        response = self.client.get(reverse('mis_tarjetas'))
        self.assertEqual(response.status_code, 302)

    def test_calendario_ofrece_tarjetas_guardadas_en_el_modal(self):
        """El calendario usa un modal (sin prompt) que ofrece las tarjetas guardadas del usuario."""
        resource = Resource.objects.create(name='Pista 1')
        response = self.client.get(reverse('calendario_full', args=[resource.id]))
        self.assertContains(response, 'id="modal-reserva"')
        self.assertContains(response, 'Guardar mis datos')
        self.assertNotContains(response, 'prompt(')
        self.assertEqual([t['last4'] for t in response.context['tarjetas']], ['4242'])
