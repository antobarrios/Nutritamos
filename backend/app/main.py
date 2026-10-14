from __future__ import annotations

import os
import uuid
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

APP_NAME = "Nutritamos API"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or "sqlite:///./nutritamos.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "change-this-to-a-long-random-secret")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

class Base(DeclarativeBase):
    pass

class MealDB(Base):
    __tablename__ = "meals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="almuerzo")
    kcal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time: Mapped[str] = mapped_column(String(20), nullable=False, default="12:30")
    emoji: Mapped[str] = mapped_column(String(12), nullable=False, default="🥗")
    color: Mapped[str] = mapped_column(String(30), nullable=False, default="sage")
    ingredients: Mapped[str] = mapped_column(Text, nullable=False, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

class PlanDB(Base):
    __tablename__ = "plan_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    meal: Mapped[str] = mapped_column(String(20), nullable=False)
    food_id: Mapped[int] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), nullable=False)

class WaterDB(Base):
    __tablename__ = "water_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    ml: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AppointmentDB(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_name: Mapped[str] = mapped_column(String(120), nullable=False)
    patient_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    patient_email: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="Consulta nutricional")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reservado")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="paciente")
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MealCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    category: str = Field(default="almuerzo", pattern="^(desayuno|almuerzo|merienda|cena|snack)$")
    kcal: int = Field(default=0, ge=0, le=5000)
    time: str = Field(default="12:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    emoji: str = Field(default="🥗", max_length=12)
    color: str = Field(default="sage", max_length=30)
    ingredients: list[str] = Field(default_factory=list)

class PlanCreate(BaseModel):
    day: str = Field(pattern="^(Lun|Mar|Mié|Jue|Vie|Sáb|Dom)$")
    meal: str = Field(pattern="^(desayuno|almuerzo|merienda|cena)$")
    food_id: int

class AppointmentCreate(BaseModel):
    patient_name: str = Field(min_length=2, max_length=120)
    patient_phone: str = Field(min_length=6, max_length=40)
    patient_email: str = Field(default="", max_length=180)
    start_at: datetime
    duration_minutes: int = Field(default=30, ge=15, le=180)
    reason: str = Field(default="Consulta nutricional", max_length=300)

class AppointmentStatus(BaseModel):
    status: str = Field(pattern="^(reservado|confirmado|asistio|ausente|cancelado)$")

class WaterCreate(BaseModel):
    ml: int = Field(ge=50, le=2000)

DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MEAL_CATEGORIES = ["desayuno", "almuerzo", "merienda", "cena"]
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

def local_now() -> datetime:
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    if not ADMIN_API_KEY or ADMIN_API_KEY == "change-this-to-a-long-random-secret":
        # Allow local demo but fail closed in production unless a secret is configured.
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            raise HTTPException(503, "Configurá ADMIN_API_KEY en las variables de entorno.")
        return True
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(401, "Clave profesional inválida.")
    return True


def meal_dict(m: MealDB):
    return {"id": m.id, "name": m.name, "category": m.category, "kcal": m.kcal, "time": m.time,
            "emoji": m.emoji, "color": m.color, "ingredients": [x.strip() for x in m.ingredients.split(",") if x.strip()], "favorite": m.favorite}


def appointment_dict(a: AppointmentDB):
    return {"id": a.id, "patient_name": a.patient_name, "patient_phone": a.patient_phone,
            "patient_email": a.patient_email, "start_at": a.start_at.isoformat(),
            "duration_minutes": a.duration_minutes, "reason": a.reason, "status": a.status,
            "source": a.source, "reminder_sent": a.reminder_sent}

app = FastAPI(title=APP_NAME, version="1.0.0", description="API para planificación nutricional y agenda de turnos Nutritamos")
app.add_middleware(CORSMiddleware, allow_origins=list({FRONTEND_URL, "http://localhost:5173", "http://127.0.0.1:5173"}), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(MealDB)) == 0:
            demo = [
                ("Yogur con frutos rojos", "desayuno", 280, "08:00", "🥣", "sage", "yogur,frutos rojos,avena"),
                ("Tostadas con palta", "desayuno", 320, "08:30", "🥑", "peach", "pan integral,palta,huevo"),
                ("Bowl de quinoa y vegetales", "almuerzo", 420, "12:30", "🥗", "sage", "quinoa,pepino,tomate,garbanzos"),
                ("Pollo con verduras", "almuerzo", 510, "13:00", "🍲", "peach", "pollo,zapallo,zanahoria,arroz integral"),
                ("Fruta y frutos secos", "merienda", 220, "17:00", "🍎", "lavender", "manzana,nueces"),
                ("Licuado de banana", "merienda", 190, "17:30", "🥤", "sage", "banana,leche o bebida vegetal"),
                ("Tortilla de verduras", "cena", 360, "20:30", "🍳", "peach", "huevo,espinaca,cebolla"),
                ("Ensalada tibia de lentejas", "cena", 390, "21:00", "🥙", "lavender", "lentejas,calabaza,rúcula"),
            ]
            db.add_all([MealDB(name=n, category=c, kcal=k, time=t, emoji=e, color=col, ingredients=i) for n,c,k,t,e,col,i in demo])
            db.commit()

@app.get("/")
def root():
    return {"name": APP_NAME, "version": "1.0.0", "docs": "/docs", "status": "ok"}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Nutritamos API"}

@app.get("/api/meals")
def list_meals(db: Session = Depends(get_db)):
    return [meal_dict(m) for m in db.scalars(select(MealDB).order_by(MealDB.category, MealDB.name)).all()]

@app.post("/api/meals", dependencies=[Depends(require_admin)], status_code=201)
def create_meal(data: MealCreate, db: Session = Depends(get_db)):
    m = MealDB(name=data.name, category=data.category, kcal=data.kcal, time=data.time, emoji=data.emoji, color=data.color, ingredients=",".join(data.ingredients))
    db.add(m); db.commit(); db.refresh(m)
    return meal_dict(m)

@app.patch("/api/meals/{meal_id}/favorite", dependencies=[Depends(require_admin)])
def toggle_favorite(meal_id: int, db: Session = Depends(get_db)):
    m = db.get(MealDB, meal_id)
    if not m: raise HTTPException(404, "Comida no encontrada")
    m.favorite = not m.favorite; db.commit(); db.refresh(m)
    return meal_dict(m)

@app.get("/api/plan")
def get_plan(day: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    stmt = select(PlanDB, MealDB).join(MealDB, PlanDB.food_id == MealDB.id)
    if day:
        if day not in DAYS: raise HTTPException(422, "Día inválido")
        stmt = stmt.where(PlanDB.day == day)
    rows = db.execute(stmt.order_by(PlanDB.id)).all()
    return [{"id": p.id, "day": p.day, "meal": p.meal, "food_id": p.food_id, "food": meal_dict(m)} for p,m in rows]

@app.post("/api/plan", dependencies=[Depends(require_admin)], status_code=201)
def save_plan(data: PlanCreate, db: Session = Depends(get_db)):
    if not db.get(MealDB, data.food_id): raise HTTPException(404, "La comida seleccionada no existe")
    existing = db.scalar(select(PlanDB).where(PlanDB.day == data.day, PlanDB.meal == data.meal))
    if existing:
        existing.food_id = data.food_id
    else:
        db.add(PlanDB(day=data.day, meal=data.meal, food_id=data.food_id))
    db.commit()
    return {"ok": True, "day": data.day, "meal": data.meal, "food_id": data.food_id}

@app.delete("/api/plan/{entry_id}", dependencies=[Depends(require_admin)])
def delete_plan(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(PlanDB, entry_id)
    if not entry: raise HTTPException(404, "Comida planificada no encontrada")
    db.delete(entry); db.commit(); return {"ok": True}

@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    rows = db.execute(select(PlanDB, MealDB).join(MealDB, PlanDB.food_id == MealDB.id)).all()
    by_day = {day: {"meals": 0, "kcal": 0} for day in DAYS}
    for p,m in rows:
        by_day[p.day]["meals"] += 1; by_day[p.day]["kcal"] += m.kcal
    return {"total_planned_meals": len(rows), "total_planned_kcal": sum(m.kcal for _,m in rows), "by_day": by_day,
            "favorites": db.scalar(select(func.count()).select_from(MealDB).where(MealDB.favorite.is_(True))) or 0}

@app.get("/api/water")
def water_summary(day: date = Query(default_factory=date.today), db: Session = Depends(get_db)):
    entries = db.scalars(select(WaterDB).where(WaterDB.day == day.isoformat()).order_by(WaterDB.id)).all()
    return {"day": day.isoformat(), "total_ml": sum(x.ml for x in entries), "goal_ml": 2000,
            "entries": [{"id": x.id, "ml": x.ml} for x in entries]}

@app.post("/api/water", dependencies=[Depends(require_admin)], status_code=201)
def add_water(data: WaterCreate, day: date = Query(default_factory=date.today), db: Session = Depends(get_db)):
    entry = WaterDB(day=day.isoformat(), ml=data.ml); db.add(entry); db.commit(); db.refresh(entry)
    return {"id": entry.id, "day": entry.day, "ml": entry.ml}

@app.get("/api/appointments/availability")
def availability(day: date = Query(...), duration_minutes: int = Query(default=30, ge=15, le=180), db: Session = Depends(get_db)):
    # Business hours are configurable in a future version; MVP defaults to weekdays 09:00–17:00.
    if day.weekday() >= 5: return {"day": day.isoformat(), "slots": []}
    now = local_now()
    booked = db.scalars(select(AppointmentDB).where(func.date(AppointmentDB.start_at) == day.isoformat(), AppointmentDB.status != "cancelado")).all()
    slots = []
    current = datetime.combine(day, time(9, 0))
    end_day = datetime.combine(day, time(17, 0))
    while current + timedelta(minutes=duration_minutes) <= end_day:
        slot_end = current + timedelta(minutes=duration_minutes)
        conflict = any(current < a.start_at + timedelta(minutes=a.duration_minutes) and slot_end > a.start_at for a in booked)
        if not conflict and current > now:
            slots.append(current.isoformat())
        current += timedelta(minutes=30)
    return {"day": day.isoformat(), "slots": slots}

async def send_whatsapp_reminder(appointment: AppointmentDB):
    token = os.getenv("WHATSAPP_TOKEN", "").strip()
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    version = os.getenv("WHATSAPP_API_VERSION", "v22.0").strip()
    if not token or not phone_id or not appointment.patient_phone:
        return False
    # Requires an approved WhatsApp template named "appointment_reminder" with {{1}} patient name and {{2}} appointment date/time.
    payload = {"messaging_product": "whatsapp", "to": appointment.patient_phone,
               "type": "template", "template": {"name": "appointment_reminder", "language": {"code": "es_AR"},
               "components": [{"type": "body", "parameters": [{"type": "text", "text": appointment.patient_name},
               {"type": "text", "text": appointment.start_at.strftime("%d/%m/%Y %H:%M")}]}]}}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"https://graph.facebook.com/{version}/{phone_id}/messages", headers={"Authorization": f"Bearer {token}"}, json=payload)
        response.raise_for_status()
    return True

@app.post("/api/appointments", status_code=201)
def book_appointment(data: AppointmentCreate, background_tasks: BackgroundTasks, source: str = Query(default="paciente", pattern="^(paciente|profesional)$"), x_admin_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    if source == "profesional":
        require_admin(x_admin_key)
    if data.start_at <= local_now(): raise HTTPException(400, "Elegí una fecha y hora futuras.")
    end_at = data.start_at + timedelta(minutes=data.duration_minutes)
    if source == "paciente":
        opening = datetime.combine(data.start_at.date(), time(9, 0))
        closing = datetime.combine(data.start_at.date(), time(17, 0))
        if data.start_at.weekday() >= 5 or data.start_at < opening or end_at > closing or data.start_at.minute not in (0, 30):
            raise HTTPException(400, "Elegí un horario disponible de lunes a viernes, entre las 09:00 y las 17:00.")
    day_bookings = db.scalars(select(AppointmentDB).where(func.date(AppointmentDB.start_at) == data.start_at.date().isoformat(), AppointmentDB.status != "cancelado")).all()
    if any(data.start_at < a.start_at + timedelta(minutes=a.duration_minutes) and end_at > a.start_at for a in day_bookings):
        raise HTTPException(409, "Ese horario acaba de ocuparse. Elegí otro horario disponible.")
    a = AppointmentDB(patient_name=data.patient_name, patient_phone=data.patient_phone, patient_email=data.patient_email,
                      start_at=data.start_at, duration_minutes=data.duration_minutes, reason=data.reason, source=source)
    db.add(a); db.commit(); db.refresh(a)
    return appointment_dict(a)

@app.get("/api/appointments", dependencies=[Depends(require_admin)])
def list_appointments(from_date: Optional[date] = None, to_date: Optional[date] = None, db: Session = Depends(get_db)):
    stmt = select(AppointmentDB).order_by(AppointmentDB.start_at)
    if from_date: stmt = stmt.where(AppointmentDB.start_at >= datetime.combine(from_date, time.min))
    if to_date: stmt = stmt.where(AppointmentDB.start_at < datetime.combine(to_date + timedelta(days=1), time.min))
    return [appointment_dict(a) for a in db.scalars(stmt).all()]

@app.patch("/api/appointments/{appointment_id}", dependencies=[Depends(require_admin)])
def update_appointment(appointment_id: str, data: AppointmentStatus, db: Session = Depends(get_db)):
    a = db.get(AppointmentDB, appointment_id)
    if not a: raise HTTPException(404, "Turno no encontrado")
    a.status = data.status; db.commit(); db.refresh(a)
    return appointment_dict(a)

@app.delete("/api/appointments/{appointment_id}", dependencies=[Depends(require_admin)])
def delete_appointment(appointment_id: str, db: Session = Depends(get_db)):
    a = db.get(AppointmentDB, appointment_id)
    if not a: raise HTTPException(404, "Turno no encontrado")
    a.status = "cancelado"; db.commit(); return {"ok": True}

@app.post("/api/reminders/run")
async def run_reminders(x_cron_secret: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    secret = os.getenv("REMINDER_CRON_SECRET", "change-this-too")
    if not secret or x_cron_secret != secret: raise HTTPException(401, "Clave de recordatorios inválida")
    now = local_now(); window_end = now + timedelta(hours=24)
    candidates = db.scalars(select(AppointmentDB).where(AppointmentDB.status.in_(["reservado", "confirmado"]), AppointmentDB.reminder_sent.is_(False), AppointmentDB.start_at >= now, AppointmentDB.start_at <= window_end)).all()
    sent = 0; skipped = 0
    for a in candidates:
        try:
            ok = await send_whatsapp_reminder(a)
            if ok:
                a.reminder_sent = True; sent += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    db.commit()
    return {"checked": len(candidates), "sent": sent, "skipped": skipped, "note": "Configura token, número y plantilla aprobada de WhatsApp Cloud API para enviar mensajes reales."}
