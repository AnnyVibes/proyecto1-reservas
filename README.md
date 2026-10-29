# 🏟️ Gestor de Reservas de Pistas y Salas

Un sistema web desarrollado con **Django** para gestionar reservas de recursos como pistas de pádel, tenis, fútbol o salas multiusos.  
Incluye un **calendario interactivo con FullCalendar**, gestión de usuarios, validación de solapamientos, reservas recurrentes, bloqueos administrativos y un panel de administración completo.

---

## **Características principales**

### **Modelos implementados**
- **Resource** – Cada pista, con su precio por hora (`price_per_hour`).
- **Booking** – Reserva de un usuario, con estado `confirmada` / `cancelada`.
- **Availability (Bloqueos)** – Franjas en las que una pista no se puede reservar.
- **PaymentMethod** – Tarjeta guardada (solo titular, marca, últimos 4 dígitos, vencimiento y token).
- **Payment** – Pago simulado de cada reserva.

### **Funcionalidades clave**
- 📅 **Calendario mensual coloreado** por disponibilidad (libre, parcial, completo, pasado), con vistas de semana y día, en español.
- 💳 **Pago simulado** en un modal, con tarjeta nueva o guardada ("Guardar mis datos"). Nunca se guarda el número completo ni el CVV.
- 🗂️ **Mis reservas**: próximas y pasadas, con cancelación hasta 2 horas antes. La franja cancelada queda libre.
- ✉️ **Correos** de confirmación y cancelación (en desarrollo se muestran en la consola).
- 📈 **Panel de demanda** para staff: histórico semanal, previsión por promedio móvil de 4 semanas y mapa de calor por día y hora.
- ⛔ **Validación en el servidor**: solapes, bloqueos, horario 09:00–21:00, fechas pasadas y reservas recurrentes atómicas (máx. 12 semanas).
- 👨‍💼 **Django Admin** para pistas, reservas, bloqueos, tarjetas y pagos.

### **Tarjetas de prueba (pago simulado)**
| Número | Resultado |
|---|---|
| `4242 4242 4242 4242` | Aprobada |
| `4000 0000 0000 0002` | Siempre rechazada |

Cualquier vencimiento futuro y un CVV de 3 dígitos.

---

## **Tecnologías utilizadas**

- **Backend:** Django 5 (Python 3.12)
- **Frontend:** plantillas de Django con una plantilla base común, Tailwind (CDN), FullCalendar 6.1.11 y Chart.js 4.4.1 (CDN)
- **Base de datos:** SQLite (por defecto, fácil de cambiar a MySQL o PostgreSQL)
- **Autenticación:** Sistema de usuarios de Django
- **UI:** Diseño minimalista con **navbar**, cards y calendario interactivo

---

## Enfoque del Proyecto

Este proyecto está centrado principalmente en el aprendizaje y la práctica de **Django**.  
Mi objetivo ha sido entender la arquitectura del framework, el manejo de vistas, URLs, modelos, templates y la interacción con la base de datos.  

Por este motivo, el **diseño visual** no ha sido la prioridad en esta fase del desarrollo, ya que mi atención ha estado enfocada en construir una aplicación funcional y bien estructurada en cuanto a lógica y backend.



## **Instalación**

Requisitos: Python 3.12 o superior.

### **1. Clonar el repositorio**

```bash
git clone https://github.com/AnnyVibes/proyecto1-reservas.git
cd proyecto1-reservas
```

### **2. Crear y activar el entorno virtual**

```bash
python -m venv venv
source venv/Scripts/activate   # Windows (Git Bash)
source venv/bin/activate       # Linux/Mac
```

### **3. Instalar dependencias**

```bash
pip install -r requirements.txt
```

### **4. Crear la base de datos**

La base de datos (`db.sqlite3`) no se versiona: cada persona crea la suya.

```bash
python manage.py migrate
```

### **5. Cargar las pistas**

```bash
python manage.py loaddata pistas
```

### **6. Crear un superusuario (para acceder al panel admin)**

```bash
python manage.py createsuperuser
```

### **7. Ejecutar el servidor**

```bash
python manage.py runserver
```

Accede en tu navegador a http://127.0.0.1:8000/

### **8. Ejecutar las pruebas**

```bash
python manage.py test
```

### **9. (Opcional) Datos de ejemplo**

```bash
python manage.py generar_historico --semanas 26 --seed 42   # histórico para el panel de demanda
python manage.py generar_historico --semanas 0 --reset      # borra solo ese histórico
python manage.py crear_reservas_demo                        # usuario demo_user con reservas futuras
```

### **Correo**

Por defecto los correos se imprimen en la consola de `runserver`. Para usar un servidor SMTP real,
define la variable de entorno `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` y las
variables `EMAIL_HOST`, `EMAIL_PORT`, etc.

Uso de la aplicación
Panel de administración:
Accede a http://127.0.0.1:8000/admin/ para crear recursos (pistas) y gestionar reservas manualmente.

Home Page (Listado de recursos):
Verás todas las pistas (pádel, fútbol, tenis, etc.) con cards interactivas y un botón para ver el calendario de cada una.

Calendario interactivo:

Selecciona un bloque de tiempo disponible para hacer una reserva.

El sistema valida solapamientos y bloqueos.

Se pueden crear reservas recurrentes (pregunta cuántas semanas repetir).
