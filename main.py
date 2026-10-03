import os
from datetime import datetime, timedelta, date
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, text
import bcrypt
from jose import JWTError, jwt
from dotenv import load_dotenv
from num2words import num2words

import models
from models import Base

load_dotenv()
db_url = os.getenv("DATABASE_URL", "sqlite:///./gta_software.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

SQLALCHEMY_DATABASE_URL = db_url
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="GTA Transport Management System (Enhanced)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AUTH SETUP ---
SECRET_KEY = os.getenv("SECRET_KEY", "b91a7e5f3c2e1d0f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@app.on_event("startup")
def startup_event():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    # Ensure new columns exist if SQLite (cheap hack, normally use alembic)
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'User'"))
        db.commit()
    except:
        db.rollback()

    try:
        db.execute(text("ALTER TABLE bilties ADD COLUMN origin VARCHAR DEFAULT 'Ahmedabad'"))
        db.commit()
    except:
        db.rollback()

    try:
        db.execute(text("ALTER TABLE bilties ADD COLUMN destination VARCHAR DEFAULT ''"))
        db.commit()
    except:
        db.rollback()
        
    users = [
        ("SuperAdmin", "Admin@123", "SuperAdmin"),
        ("Dhananjay Dwivedi", "Dhananjay@123", "User"),
        ("Nagendra Shukla", "Nagendra@123", "User")
    ]
    for u, p, r in users:
        if not db.query(models.User).filter(models.User.username == u).first():
            db.add(models.User(username=u, hashed_password=get_password_hash(p), role=r))
    db.commit()
    db.close()

@app.post("/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}

# --- SCHEMAS ---
class PartyCreate(BaseModel):
    name: str
    gst_no: Optional[str] = None
    pan_no: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    party_type: str

class BiltyCreate(BaseModel):
    lr_no: str
    date: date
    gst_paid_by: str
    delivery_address: str
    lorry_no: str
    risk_type: str
    eway_bill_no: Optional[str] = None
    consignor_id: int
    consignee_id: int
    packages: str = ""
    description: str
    actual_weight: float
    charged_weight: float
    rate: float
    is_fixed_rate: bool = False
    mazdoor_charges: float = 0.0
    sur_charges: float = 0.0
    st_charges: float = 100.0

class ChallanCreate(BaseModel):
    challan_no: str
    date: date
    origin: str
    destination: str
    lorry_no: str
    vendor_id: int
    driver_name: str
    license_no: str
    driver_phone: str
    chassis_engine_no: str
    vendor_freight: float
    advance_paid: float
    payable_at: str
    apply_tds: bool = True
    bilty_ids: List[int]

class InvoiceCreate(BaseModel):
    bill_no: str
    date: date
    party_id: int
    bill_type: str = 'Freight'
    reverse_charge: bool = True
    bank_name: str
    account_no: str
    ifsc_code: str
    branch: str
    bilty_ids: List[int]

class PaymentCreate(BaseModel):
    date: date
    party_id: int
    invoice_id: Optional[int] = None
    amount_received: float
    payment_mode: str
    utr_no: Optional[str] = None

class VendorPaymentCreate(BaseModel):
    date: date
    vendor_id: int
    challan_id: Optional[int] = None
    amount_paid: float
    payment_mode: str
    utr_no: Optional[str] = None

class ExpenseCreate(BaseModel):
    date: date
    expense_type: str
    description: str
    amount: float
    challan_id: Optional[int] = None

# --- ENDPOINTS ---
@app.get("/api/parties")
def list_parties(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Party).all()

@app.post("/api/parties")
def create_party(party: PartyCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db_party = models.Party(**party.dict())
    db.add(db_party)
    db.commit()
    db.refresh(db_party)
    return db_party

@app.delete("/api/parties/{party_id}")
def delete_party(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    party = db.query(models.Party).filter(models.Party.id == party_id).first()
    if not party: raise HTTPException(status_code=404, detail="Party not found")
    
    # Check if party is used in bilties
    bilty = db.query(models.Bilty).filter((models.Bilty.consignor_id == party_id) | (models.Bilty.consignee_id == party_id)).first()
    if bilty: raise HTTPException(status_code=400, detail="Cannot delete Party. It is used in existing Consignments (LRs).")
    
    db.delete(party)
    db.commit()
    return {"message": "Party deleted"}

@app.get("/api/bilties")
def list_bilties(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Bilty).all()

@app.get("/api/bilties/unbilled/{party_id}")
def get_unbilled_bilties(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # Unbilled: Belongs to party, attached to challan (dispatched), NOT attached to invoice
    return db.query(models.Bilty).filter(
        ((models.Bilty.consignor_id == party_id) & (models.Bilty.gst_paid_by == 'CONSIGNOR')) |
        ((models.Bilty.consignee_id == party_id) & (models.Bilty.gst_paid_by == 'CONSIGNEE'))
    ).filter(models.Bilty.challan_id != None, models.Bilty.invoice_id == None).all()

@app.post("/api/bilties")
def create_bilty(bilty: BiltyCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if bilty.is_fixed_rate:
        bilty.st_charges = 0.0 # No extra stationery charges on lumpsum
        total_freight = bilty.rate + bilty.mazdoor_charges + bilty.sur_charges
    else:
        total_freight = (bilty.charged_weight * bilty.rate) + bilty.mazdoor_charges + bilty.sur_charges + bilty.st_charges
        
    bilty_data = bilty.dict()
    bilty_data['total_freight_charges'] = total_freight
    db_bilty = models.Bilty(**bilty_data)
    db.add(db_bilty)
    db.commit()
    db.refresh(db_bilty)
    return db_bilty

@app.delete("/api/bilties/{bilty_id}")
def delete_bilty(bilty_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    bilty = db.query(models.Bilty).filter(models.Bilty.id == bilty_id).first()
    if not bilty: raise HTTPException(status_code=404, detail="Bilty not found")
    
    if bilty.invoice_id or bilty.challan_id:
        raise HTTPException(status_code=400, detail="Cannot delete LR. It is already attached to a Challan or Invoice.")
        
    db.delete(bilty)
    db.commit()
    return {"message": "Consignment (LR) deleted"}

def calculate_tds(pan_no: str, freight: float, apply_tds: bool):
    if not apply_tds or not pan_no or len(pan_no) < 4:
        return 0.0, 0.0
    pan_type = pan_no[3].upper()
    rate = 0.01 if pan_type in ['P', 'H'] else 0.02
    if freight > 30000:
        return freight * rate, rate
    return 0.0, 0.0

@app.post("/api/challans")
def create_challan(challan: ChallanCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    vendor = db.query(models.Party).filter(models.Party.id == challan.vendor_id).first()
    if not vendor: raise HTTPException(status_code=404, detail="Vendor not found")
    bilties = db.query(models.Bilty).filter(models.Bilty.id.in_(challan.bilty_ids)).all()
    
    # Freight paid to vendor is now explicit instead of derived from customer billing
    total_freight = challan.vendor_freight
    
    weight_charges = sum(b.charged_weight for b in bilties) # Just track total weight
    tds_amount, tds_rate = calculate_tds(vendor.pan_no, total_freight, challan.apply_tds)
    balance = total_freight - challan.advance_paid
    net_payable = balance - tds_amount
    challan_data = challan.dict(exclude={'bilty_ids', 'vendor_freight'})
    challan_data.update({'weight_charges': weight_charges, 'total_freight': total_freight, 'balance_freight': balance, 'vendor_pan': vendor.pan_no or '', 'tds_amount': tds_amount, 'tds_rate': tds_rate, 'net_payable': net_payable})
    db_challan = models.Challan(**challan_data)
    db.add(db_challan)
    db.commit()
    db.refresh(db_challan)
    for b in bilties: 
        b.challan_id = db_challan.id
        b.lorry_no = db_challan.lorry_no
        b.origin = db_challan.origin
        b.destination = db_challan.destination
    db.commit()
    db.refresh(db_challan)
    return db_challan

@app.post("/api/invoices")
def create_invoice(invoice: InvoiceCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    bilties = db.query(models.Bilty).filter(models.Bilty.id.in_(invoice.bilty_ids)).all()
    if not bilties: raise HTTPException(status_code=400, detail="No bilties provided")
    total_amount = sum(b.total_freight_charges for b in bilties)
    igst_amount = 0.0 if invoice.reverse_charge else total_amount * 0.05
    net_amount = total_amount + igst_amount
    
    # Use actual num2words for Indian format
    amount_words = num2words(int(net_amount), lang='en_IN').title() + " Rupees Only"
    
    invoice_data = invoice.dict(exclude={'bilty_ids'})
    invoice_data.update({'total_amount': total_amount, 'igst_amount': igst_amount, 'net_amount': net_amount, 'amount_in_words': amount_words})
    db_invoice = models.Invoice(**invoice_data)
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    for b in bilties: b.invoice_id = db_invoice.id
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

@app.get("/api/invoices")
def get_invoices(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Invoice).order_by(models.Invoice.id.desc()).limit(50).all()

@app.delete("/api/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can delete invoices")
    
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice: raise HTTPException(status_code=404, detail="Invoice not found")
    
    payments = db.query(models.Payment).filter(models.Payment.invoice_id == invoice_id).first()
    if payments:
        raise HTTPException(status_code=400, detail="Cannot delete invoice because payments have been received against it. Delete the payments first.")
        
    bilties = db.query(models.Bilty).filter(models.Bilty.invoice_id == invoice_id).all()
    for b in bilties: b.invoice_id = None
    
    db.delete(invoice)
    db.commit()
    return {"message": "Invoice deleted successfully"}

@app.get("/api/invoices/{invoice_id}/bilties")
def get_invoice_bilties(invoice_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Bilty).filter(models.Bilty.invoice_id == invoice_id).all()

@app.get("/api/parties/{party_id}/unpaid_invoices")
def get_unpaid_invoices(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    invoices = db.query(models.Invoice).filter(models.Invoice.party_id == party_id).all()
    unpaid = []
    for inv in invoices:
        paid = db.query(func.sum(models.Payment.amount_received)).filter(models.Payment.invoice_id == inv.id).scalar() or 0.0
        balance = inv.net_amount - paid
        if balance > 0.01:
            unpaid.append({
                "id": inv.id,
                "bill_no": inv.bill_no,
                "date": inv.date,
                "net_amount": inv.net_amount,
                "balance": balance
            })
    return unpaid

@app.post("/api/payments")
def create_payment(payment: PaymentCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db_payment = models.Payment(**payment.dict())
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    db.refresh(db_payment)
    return db_payment

@app.get("/api/parties/{vendor_id}/unpaid_challans")
def get_unpaid_challans(vendor_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    challans = db.query(models.Challan).filter(models.Challan.vendor_id == vendor_id).all()
    unpaid = []
    for ch in challans:
        paid = db.query(func.sum(models.VendorPayment.amount_paid)).filter(models.VendorPayment.challan_id == ch.id).scalar() or 0.0
        # Vendor was already paid advance, so balance is net_payable - paid
        balance = ch.net_payable - paid
        if balance > 0.01:
            unpaid.append({
                "id": ch.id,
                "challan_no": ch.challan_no,
                "date": ch.date,
                "net_payable": ch.net_payable,
                "balance": balance
            })
    return unpaid

@app.post("/api/vendor_payments")
def create_vendor_payment(payment: VendorPaymentCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db_payment = models.VendorPayment(**payment.dict())
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment

@app.post("/api/expenses")
def create_expense(expense: ExpenseCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db_expense = models.Expense(**expense.dict())
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@app.get("/api/reports/dashboard")
def get_dashboard_analytics(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # 1. Outstanding logic
    parties = db.query(models.Party).all()
    outstanding_results = []
    for party in parties:
        unbilled = db.query(func.sum(models.Bilty.total_freight_charges)).filter(
            ((models.Bilty.consignor_id == party.id) & (models.Bilty.gst_paid_by == 'CONSIGNOR')) |
            ((models.Bilty.consignee_id == party.id) & (models.Bilty.gst_paid_by == 'CONSIGNEE'))
        ).filter(models.Bilty.challan_id != None, models.Bilty.invoice_id == None).scalar() or 0.0
        billed = db.query(func.sum(models.Invoice.net_amount)).filter(models.Invoice.party_id == party.id).scalar() or 0.0
        payments = db.query(func.sum(models.Payment.amount_received)).filter(models.Payment.party_id == party.id).scalar() or 0.0
        net_exposure = unbilled + (billed - payments)
        if net_exposure > 0:
            outstanding_results.append({
                "party_name": party.name,
                "unbilled": unbilled,
                "billed": billed - payments,
                "net": net_exposure
            })
            
    vendor_outstanding_results = []
    for party in parties:
        if party.party_type == 'Vendor':
            vendor_challans = db.query(func.sum(models.Challan.net_payable)).filter(models.Challan.vendor_id == party.id).scalar() or 0.0
            vendor_payments = db.query(func.sum(models.VendorPayment.amount_paid)).filter(models.VendorPayment.vendor_id == party.id).scalar() or 0.0
            net_vendor_exposure = vendor_challans - vendor_payments
            if net_vendor_exposure > 0:
                vendor_outstanding_results.append({
                    "party_name": party.name,
                    "net": net_vendor_exposure
                })

    # 2. Revenue Chart Data
    invoices = db.query(models.Invoice).all()
    revenue_dict = {}
    for inv in invoices:
        m = inv.date.strftime("%b %Y")
        revenue_dict[m] = revenue_dict.get(m, 0) + inv.net_amount
        
    total_revenue = sum(revenue_dict.values())
    total_expenses = db.query(func.sum(models.Expense.amount)).scalar() or 0.0
    total_cost = (db.query(func.sum(models.Challan.total_freight)).scalar() or 0.0) + total_expenses
    net_revenue = total_revenue - total_cost

    return {
        "outstanding": outstanding_results,
        "vendor_outstanding": vendor_outstanding_results,
        "revenue_labels": list(revenue_dict.keys()),
        "revenue_data": list(revenue_dict.values()),
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "net_revenue": net_revenue
    }

@app.delete("/api/reset_database")
def reset_database(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can reset database")
    
    # Delete in order of foreign keys
    db.query(models.Expense).delete()
    db.query(models.VendorPayment).delete()
    db.query(models.Payment).delete()
    db.query(models.Bilty).delete()
    db.query(models.Invoice).delete()
    db.query(models.Challan).delete()
    db.query(models.Party).delete()
    db.commit()
    return {"message": "Database wiped successfully!"}

# --- STATIC FILES FOR SPA ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_index():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/manifest.json")
def read_manifest():
    return FileResponse("static/manifest.json")

@app.get("/sw.js")
def read_sw():
    return FileResponse("static/sw.js")
