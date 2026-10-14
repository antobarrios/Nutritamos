# Nutritamos — MVP full-stack

Aplicación web en español para planificación nutricional y agenda de turnos. Incluye React + Vite, FastAPI y persistencia con SQLite en local o PostgreSQL en despliegue.

## Incluye
- Panel profesional con agenda y creación/cancelación/estado de turnos.
- Enlace de reserva pública: añadir `?reservar=1` a la URL del frontend.
- Disponibilidad básica de lunes a viernes de 09:00 a 17:00; bloquea turnos superpuestos.
- Biblioteca de comidas, creación de comidas, favoritos y plan semanal por día/horario.
- Resumen y estadísticas basados en comidas planificadas.
- Registro de hidratación y lista de compras derivada de ingredientes planificados.
- Botón de WhatsApp en cada turno: abre WhatsApp con un recordatorio personalizado listo para revisar y enviar manualmente. No requiere API ni pago adicional.
- Integración opcional con WhatsApp Cloud API para envíos automáticos; requiere plantilla aprobada `appointment_reminder` y configurar variables. El endpoint de recordatorios se ejecuta mediante cron externo.

## Ejecutar localmente (Windows)

### 1. Backend
Abrí una terminal en `backend` y ejecutá:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API: http://127.0.0.1:8000 · Documentación: http://127.0.0.1:8000/docs

### 2. Frontend
En otra terminal, entrá a `frontend` y ejecutá:

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

Frontend: http://localhost:5173

Para uso local, la clave de ejemplo del frontend y del backend coincide. Cambiala si configurás otra clave en ambos `.env`. No pongas una clave privada real en un frontend público: el mecanismo de clave compartida es solo para MVP/pruebas.

## Despliegue sugerido

### Backend en Render
- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Variables: `DATABASE_URL` (PostgreSQL administrado), `FRONTEND_URL` (URL del frontend), `ADMIN_API_KEY` (secreto largo), `ENVIRONMENT=production`.
- Opcionales WhatsApp: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION=v22.0`, `REMINDER_CRON_SECRET`.

### Frontend en Vercel
- Root Directory: `frontend`
- Framework: Vite
- Build Command: `npm run build`
- Output Directory: `dist`
- Variable `VITE_API_URL=https://TU-API.onrender.com`
- `VITE_ADMIN_API_KEY` se admite solo para pruebas. Para pacientes reales, reemplazar la clave compartida por autenticación de usuario profesional (por ejemplo, Supabase Auth) antes de producción.

### Recordatorios de WhatsApp
**Opción sencilla (incluida):** desde la agenda profesional, tocá el botón verde **WhatsApp** del turno. Se abre WhatsApp con el nombre del paciente, la fecha y la hora precargados. Revisá el texto y presioná Enviar. No se envía automáticamente.

**Opción automática (opcional):** configurar una plantilla de WhatsApp Business aprobada llamada `appointment_reminder`, idioma `es_AR`, con dos variables en el cuerpo: nombre del paciente y fecha/hora. Configurar un cron externo que llame cada 15–30 minutos a `POST https://TU-API/api/reminders/run` enviando `X-Cron-Secret: <REMINDER_CRON_SECRET>`. El envío se saltea si faltan las credenciales o la plantilla no está aprobada.

## Importante antes de usar con pacientes reales
Este paquete es un MVP funcional, no una plataforma sanitaria lista para producción. Antes de guardar datos reales, agregá autenticación real y permisos por profesional, consentimiento y política de privacidad, auditoría, backups y validación de horarios/zona horaria. No guardes historias clínicas ni información sensible hasta asegurar esos controles. La información de calorías es orientativa y no sustituye la evaluación profesional.
