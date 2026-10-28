# Análisis inicial del proyecto

> **Herramienta:** Claude Code · **Fecha:** 2026-10-28 · **Responsable:** Anllelina Varcasia
>
> Respuesta de Claude Code al prompt de análisis (Fase 1), guardada sin cambios como evidencia de uso de IA. La verificación humana de cada punto está en `AI_LOG.md`.

## Prompt utilizado

```text
Analiza este proyecto Django SIN modificar ningún archivo. Explícame:
1. Estructura de carpetas y función de cada app.
2. Modelos con sus campos y relaciones.
3. URLs y vistas existentes.
4. Cómo está integrado FullCalendar y de dónde obtiene los eventos.
5. Cómo funciona el login y la creación de reservas.
6. Si existen pruebas automatizadas.
7. Deudas técnicas o riesgos que detectes.
```

## Respuesta de Claude Code

```text
 Ran 4 shell commands

No modifiqué ningún archivo del proyecto. Solo los leí y ejecuté manage.py check, makemigrations --check --dry-run y manage.py test, que no escriben en el repositorio.

1. Estructura de carpetas

Gestor-de-reservas/
├── manage.py
├── requirements.txt        Django 5.2.18, asgiref, sqlparse, tzdata
├── db.sqlite3              base de datos versionada en git (aparece como modificada)
├── crear_issues.ps1        sin versionar: crea las historias de usuario en GitHub con gh
├── gestor_reservas/        proyecto: settings, urls, wsgi/asgi
└── reservas/               la única app; contiene toda la lógica
    ├── models.py · views.py · urls.py · admin.py · tests.py (vacío)
    ├── management/commands/crear_reservas_demo.py
    ├── migrations/0001_initial.py, 0002_alter_availability_options.py
    └── templates/
        ├── base.html                       nadie la usa
        └── reservas/home.html, login.html, calendario.html, calendario_full.html

- gestor_reservas: configuración. Base SQLite, TIME_ZONE="UTC", LANGUAGE_CODE="en-us".
- reservas: modelos, vistas, la API JSON, el admin y un comando para cargar datos de demostración.
- No hay carpeta static/, ni app de pagos, ni app de estadísticas.

2. Modelos (reservas/models.py)

┌──────────────────┬───────────────┬─────────────────────────────────┐
│      Modelo      │    Campos     │           Relaciones            │
├──────────────────┼───────────────┼─────────────────────────────────┤
│ Resource         │ name (único), │ Lo referencian bookings y       │
│                  │  description  │ availabilities                  │
├──────────────────┼───────────────┼─────────────────────────────────┤
│ Availability (se │               │                                 │
│  muestra como    │ start_time,   │ FK a Resource (CASCADE)         │
│ "Bloqueo" en el  │ end_time      │                                 │
│ admin)           │               │                                 │
├──────────────────┼───────────────┼─────────────────────────────────┤
│                  │ start_time,   │ FK a User (CASCADE), FK a       │
│ Booking          │ end_time,     │ Resource (CASCADE);             │
│                  │ created_at    │ unique_together(resource,       │
│                  │               │ start, end)                     │
└──────────────────┴───────────────┴─────────────────────────────────┘

- Booking.clean() rechaza reservas que se solapan con otra del mismo recurso. Pero objects.create() nunca llama a clean(), así que esta validación solo actúa en el admin.
- El nombre Availability confunde: su docstring dice "horarios disponibles", pero en la práctica guarda bloqueos.

3. URLs y vistas

URL: /admin/
Vista: Django admin
Qué hace: Gestión de los 3 modelos
────────────────────────────────────────
URL: /
Vista: home
Qué hace: Tarjetas con los recursos (está registrada dos veces: en el
proyecto y en la app)
────────────────────────────────────────
URL: /calendario/<id>/
Vista: calendario
Qué hace: Tabla semanal hecha en el servidor, sin FullCalendar
────────────────────────────────────────
URL: /calendario_full/<id>/
Vista: calendario_full
Qué hace: Calendario de FullCalendar (la vista principal)
────────────────────────────────────────
URL: /api/reservas/<id>/
Vista: api_reservas
Qué hace: JSON con las reservas, para FullCalendar
────────────────────────────────────────
URL: /api/reservas/crear/
Vista: api_crear_reserva
Qué hace: POST en JSON que crea reservas (@csrf_exempt)
────────────────────────────────────────
URL: /login/, /logout/
Vista: login_view, logout_view
Qué hace: Autenticación propia

- calendario_navegable no tiene URL, así que es código muerto.

4. Integración de FullCalendar (calendario_full.html)

- Se carga FullCalendar 6.1.11 desde el CDN de jsdelivr. La vista inicial es timeGridWeek de 09:00 a 21:00, en franjas de 1 hora y con selectable: true.
- Tiene dos eventSources:
  a. Reservas: las pide por AJAX a /api/reservas/<id>/. Esa vista devuelve todas las reservas del recurso e ignora los parámetros start/end que envía FullCalendar.
  b. Bloqueos: son un array fijo que Django inserta en la plantilla (bloqueos_json), pintado en rojo. Por eso el botón "Actualizar" no los vuelve a cargar.
- Datos duplicados: la vista también inserta reservas_json en la página. Solo se usa en isReserved(), que comprueba los solapes en el navegador con datos que se quedan viejos desde que se carga la página.
- locale: 'es' no tiene efecto porque no se carga el paquete de idiomas (locales-all).

5. Login y creación de reservas

Login
- login_view usa authenticate y login, y redirige a /. No respeta ?next=.
- logout_view cierra la sesión con un simple GET.
- No hay registro de usuarios, ni recuperación de contraseña, ni @login_required en ninguna vista.

Crear una reserva
1. El usuario selecciona una franja en el calendario.
2. El navegador comprueba bloqueos, solapes y si hay sesión iniciada.
3. Se piden confirmación y el número de semanas a repetir con confirm() y prompt().
4. Se hace un POST en JSON a /api/reservas/crear/.
5. El servidor comprueba que el usuario esté autenticado. Luego, para cada semana, busca solapes y crea la reserva con Booking.objects.create(...).
6. Responde con {success, reservas} y el calendario recarga los eventos.

6. Pruebas automatizadas

No hay ninguna. tests.py solo tiene la plantilla por defecto y manage.py test termina con "Found 0 test(s)". check no detecta problemas y no hay migraciones pendientes.

7. Deuda técnica y riesgos

Errores y riesgos funcionales
- El servidor no comprueba los bloqueos. api_crear_reserva no consulta Availability, así que con un POST directo se puede reservar una franja bloqueada.
- Las reservas recurrentes quedan a medias. Si la semana 3 choca, las semanas 1 y 2 ya se han guardado, porque no hay transaction.atomic.
- Hay condición de carrera. Se comprueba el solape y después se crea la reserva sin bloqueo, así que dos peticiones a la vez pueden reservar la misma franja.
- Faltan validaciones:
  - que el fin sea posterior al inicio;
  - que la fecha no esté en el pasado;
  - que el resource_id exista;
  - un límite para repeat_weeks (con 10000 crea 10001 filas).
- La API de creación devuelve errores con estado 200. Además, except Exception devuelve str(e) al cliente.
- calendario.html siempre muestra "Libre". reservas_por_dia.fecha busca la clave literal "fecha" en lugar de usar la variable.
- Zona horaria: el servidor trabaja en UTC y FullCalendar en la hora local del navegador. El comando de demo crea fechas sin zona horaria, que con USE_TZ generan avisos y desfases.
- base.html está rota: usa {% static %} sin {% load static %} y apunta a un CSS que no existe. No falla porque ninguna plantilla la extiende.

Seguridad
- @csrf_exempt en un POST autenticado, aunque el JS ya envía el token.
- SECRET_KEY escrita en el código, DEBUG=True.
- /api/reservas/<id>/ es pública y expone los nombres de usuario de quien reservó.
- El logout funciona por GET.

Mantenibilidad
- INSTALLED_APPS está definido dos veces en settings.py, la ruta / está duplicada y Resource se importa dos veces.
- Código duplicado: calendario y calendario_navegable son casi iguales, y lo mismo pasa entre api_reservas y calendario_full.
- Consultas N+1: se accede a reserva.user.username sin select_related.
- El CSS y la barra de navegación se repiten en cada plantilla, y se mezclan Tailwind (CDN) y estilos en línea.
- db.sqlite3 y los __pycache__/*.pyc están versionados aunque .gitignore los excluya: se añadieron antes de crear el .gitignore.
- crear_reservas_demo borra TODAS las reservas (Booking.objects.all().delete()).
- Booking no tiene campo de estado (confirmada o cancelada) ni de precio.

8. Qué se ve afectado por cada funcionalidad nueva

(a) Reservar con datos de pago guardados

- Modelos:
  - Un modelo nuevo PaymentMethod (FK a User). Debe guardar solo un token del proveedor (Stripe o similar), la marca, los últimos 4 dígitos y la caducidad, nunca el número de tarjeta ni el CVV (por PCI-DSS).
  - Seguramente también un modelo Payment.
  - En Booking: campos nuevos status, price, payment_method/payment y una migración.
  - En Resource: un campo de precio, como price_per_hour.
- api_crear_reserva: es la parte más afectada.
  - Recibir el método de pago y comprobar que pertenece al usuario.
  - Calcular el importe y cobrarlo.
  - Hacerlo todo dentro de transaction.atomic.
  - Quitar @csrf_exempt.
  - Corregir la falta de comprobación de bloqueos y las reservas recurrentes a medias antes de añadir dinero al flujo.
- Vistas y URLs nuevas: gestionar los métodos de pago del usuario (página "mi perfil" o "mis tarjetas") con @login_required, y quizá un webhook del proveedor.
- calendario_full.html: cambiar confirm()/prompt() por un modal que deje elegir la tarjeta guardada.
- Otros: settings.py (claves del proveedor fuera del código, en .env), requirements.txt (SDK de pago), admin.py.

(b) Calendario con días disponibles y ocupados

- calendario_full.html:
  - Añadir la vista dayGridMonth y colorear cada día, con dayCellClassNames/dayCellDidMount o eventos de fondo (display: 'background').
  - Cargar el paquete de idioma español.
- Un endpoint nuevo (por ejemplo /api/disponibilidad/<id>/?start=&end=) que calcule para cada día si está libre, parcial, completo o bloqueado. Debe usar Booking, Availability y el horario de 09:00 a 21:00, hoy fijado en DEFAULT_START/DEFAULT_END y sin uso real.
- api_reservas: filtrar por el rango start/end que envía FullCalendar.
- Bloqueos: servirlos desde una API en lugar de insertarlos en la página.
- Lógica compartida: sacar a un services.py la comprobación de solapes y bloqueos, que hoy está duplicada en JS, en views.py y en models.py. Así la usarían a la vez el cálculo de disponibilidad y la creación de reservas.
- Zona horaria: fijar TIME_ZONE (por ejemplo America/Caracas o la que corresponda) y el timeZone de FullCalendar. Si no, los días se calcularán mal en los bordes.

(c) Gráficos de previsión de demanda para el administrador

- Una vista nueva solo para staff (@staff_member_required), o una página propia dentro del admin (admin.site con URL personalizada), más su plantilla y una librería de gráficos como Chart.js.
- Servicio de agregación: consultas sobre Booking agrupadas con TruncDate/TruncWeek, ExtractWeekDay, ExtractHour y por recurso. Hacen falta índices en start_time y resource.
- Modelo de previsión: con estos datos basta algo simple, como una media móvil o la media por día de la semana y hora. Si se usan pandas o statsmodels, hay que añadirlos a requirements.txt.
- Datos:
  - Hace falta histórico: ampliar crear_reservas_demo para que genere varias semanas, y quitarle el delete() global.
  - Si existe el status de (a), las reservas canceladas se deben excluir del cálculo.
- admin.py: puede ser el sitio donde enlazar el panel.

Recomendación previa: antes de cualquiera de las tres, escribir pruebas para api_crear_reserva (solapes, bloqueos, recurrencia, usuario sin sesión) y para Booking.clean(). Las tres funcionalidades tocan esa misma lógica y ahora mismo no tiene ninguna prueba que avise si algo se rompe.
```
