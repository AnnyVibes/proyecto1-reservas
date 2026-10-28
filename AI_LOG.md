# AI Development Log

Registro de los usos de IA que afectaron significativamente el desarrollo del proyecto.

**Equipo:** Anllelina Varcasia · Eliel Garcia · Angelica Rodriguez
**Herramientas:** Claude (chat) para guía del proceso y Claude Code (escritorio/CLI) para análisis y código.

## Leyenda de decisión humana
- ✅ **Aceptada**: se usó tal cual, después de verificarla.
- 🟡 **Modificada**: se usó con cambios hechos por el equipo.
- ❌ **Rechazada**: no se usó.
- 🔴 **Incorrecta**: la IA se equivocó y el equipo lo detectó.

## Registro

| # | Fecha | Rol | Actividad | Herramienta IA | Qué se solicitó | Resultado | Decisión humana |
|---|-------|-----|-----------|----------------|-----------------|-----------|-----------------|
| 1 | 2026-10-28 | Dev | Configuración | Claude (chat) | Pasos para clonar, subir y ejecutar el repositorio | Indicó instalar Django con `pip install django` sin fijar versión, lo que instaló Django 6.1 aunque el proyecto es Django 5 | 🔴🟡 Se detectó el desajuste de versión y se cambió a Django 5.2.18, compatible con Python 3.14 |
| 2 | 2026-10-28 | Reviewer | Configuración | Claude (chat) | Explicar el aviso de migraciones pendientes | Sugirió revisarlo con `makemigrations --dry-run` antes de aplicarlo | ✅ Se verificó que solo cambiaba `verbose_name` de `Availability` (sin cambios en la BD) y se aplicó la migración 0002 |
| 3 | 2026-10-28 | Reviewer | Configuración | — | — | El repositorio original no traía `requirements.txt` ni `.gitignore` | ✅ Detectado manualmente; se agregaron en el PR #1 |
| 4 | 2026-10-28 | Reviewer | Configuración | — | — | `db.sqlite3` aparecía modificado tras la migración | ❌ Decisión humana: no subir la base de datos local (contiene usuarios y sesiones) |
| 5 | 2026-10-28 | Dev | Organización | Claude (chat) | Script de PowerShell para crear las historias de usuario como issues | La primera versión invitaba colaboradores y asignaba issues automáticamente | 🟡 El equipo decidió asignar manualmente; se pidió una versión que solo crea etiquetas e issues (#2 a #6) |
| 6 | 2026-10-28 | Dev | Análisis | Claude Code | Analizar arquitectura, modelos, vistas, FullCalendar, pruebas y riesgos sin modificar archivos | Informe completo (ver `docs/ANALISIS_INICIAL.md`): 0 pruebas, 3 modelos, API sin validación de bloqueos, `@csrf_exempt`, etc. | ✅ Aceptado tras verificar los puntos clave contra el código (ver sección de verificación) |
| 7 | 2026-10-28 | Reviewer | Análisis | Claude Code | (Dentro del análisis) zona horaria a usar | Propuso `TIME_ZONE = "America/Caracas"` | 🔴❌ Incorrecto para el equipo, que está en Panamá; se usará `America/Panama` |
| 8 | 2026-10-28 | Reviewer | Análisis | Claude Code | (Dentro del análisis) diseño del pago con datos guardados | Propuso integrar un proveedor real (Stripe), SDK de pago y webhook | ❌ Rechazado: el alcance es un **pago simulado**; solo se guardará token simulado, marca, últimos 4 dígitos y vencimiento |
| 9 | 2026-10-28 | Reviewer | Análisis | Claude Code | (Dentro del análisis) método de previsión de demanda | Sugirió opcionalmente pandas o statsmodels | ❌ Rechazado: promedio móvil en Python puro, sin dependencias nuevas |
| 10 | 2026-10-28 | Reviewer | Análisis | Claude Code | (Dentro del análisis) orden de trabajo | Recomendó escribir pruebas de `api_crear_reserva` y `Booking.clean()` antes de implementar historias | ✅ Aceptado: se crea una tarea previa de pruebas base y correcciones |
| 11 | 2026-10-28 | Dev | Pruebas (T-00, #8) | Claude Code | Plan de pruebas de `api_crear_reserva` y `Booking.clean()` antes de corregir el código | Propuso 9 pruebas de AGENTS.md más una opcional de CSRF. La persona aprobó la de CSRF, pidió agregar una prueba de pista inexistente (404) y un docstring en español en cada prueba | ⏳ Pendiente de decisión humana |
| 12 | 2026-10-28 | Dev | Pruebas (T-00, #8) | Claude Code | Escribir las 11 pruebas y ejecutarlas sin tocar el código de la app | `reservas/tests/` con 11 pruebas: 10 fallaban y 1 daba error (`IntegrityError` por pista inexistente); solo pasaba `Booking.clean()`. Commit `516bd44` | ⏳ Pendiente de decisión humana |
| 13 | 2026-10-28 | Dev | Corrección (T-00, #8) | Claude Code | Plan de correcciones | Propuso servicio `reservas/services/reservas.py`, códigos HTTP correctos, quitar `@csrf_exempt` y `@ensure_csrf_cookie` en `calendario_full`. La persona aprobó validar el horario 09:00–21:00 (prueba 12) y eligió `{% csrf_token %}` en la plantilla en lugar de `@ensure_csrf_cookie` | ⏳ Pendiente de decisión humana |
| 14 | 2026-10-28 | Dev | Corrección (T-00, #8) | Claude Code | Implementar servicio, vista, settings, dejar de versionar BD y `.pyc`, fixture y README | 12/12 pruebas en verde. Commits `9edaa38`, `f3e1a28`, `b965f8b`, `470f2b4`, `e07ca14`, `cea7617` | ⏳ Pendiente de decisión humana |
| 15 | 2026-10-28 | Dev | Corrección (T-00, #8) | Claude Code | Generar `reservas/fixtures/pistas.json` con `dumpdata` | En el plan afirmó que `dumpdata -o` evitaba el problema de codificación de Windows, pero el archivo salió en cp1252 ("fútbol" ilegible). Lo detectó la propia IA al revisar el archivo y lo regeneró con `python -X utf8`; se verificó con `loaddata pistas` | ⏳ Pendiente de decisión humana |

## Verificación del análisis (Fase 1)

Puntos del informe de Claude Code comprobados manualmente contra el código (rol QA: Anllelina Varcasia, 2026-10-28):

| Afirmación de la IA | Archivo | Evidencia | ¿Correcta? |
|---------------------|---------|-----------|------------|
| `tests.py` está vacío y `manage.py test` encuentra 0 pruebas | `reservas/tests.py` | Solo contiene la plantilla por defecto; `manage.py test` → "Found 0 test(s)" | ✅ |
| `api_crear_reserva` tiene `@csrf_exempt` | `reservas/views.py` | Línea 119: `@csrf_exempt` sobre la función (línea 120) | ✅ |
| `api_crear_reserva` no consulta `Availability` (bloqueos) | `reservas/views.py` | La única consulta está en la línea 88, fuera de la función (que inicia en la línea 120) | ✅ |
| `calendario.html` siempre muestra "Libre" por el uso de la clave literal `fecha` | `reservas/templates/reservas/calendario.html` | Líneas 110-111: `reservas_por_dia.fecha` | ✅ |
| `INSTALLED_APPS` está definido dos veces | `gestor_reservas/settings.py` | Líneas 33 y 125 | ✅ |
| `crear_reservas_demo` borra todas las reservas | `reservas/management/commands/crear_reservas_demo.py` | Línea 24: `Booking.objects.all().delete()` | ✅ |
| `Booking` tiene `unique_together` (resource, start_time, end_time) | `reservas/models.py` | Línea 54 | ✅ |

**Resultado:** 7 de 7 afirmaciones verificadas como correctas. El análisis se acepta como base para planificar el trabajo.