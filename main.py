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

    try:
        db.execute(text("ALTER TABLE challans ADD COLUMN apply_tds BOOLEAN DEFAULT TRUE"))
        db.commit()
    except:
        db.rollback()

    try:
        db.execute(text("ALTER TABLE bilties ADD COLUMN declared_value FLOAT"))
        db.commit()
    except:
        db.rollback()
        
    users = [
        ("SuperAdmin", "Admin@123", "SuperAdmin"),
        ("Dhananjay Dwivedi", "Dhananjay@123", "User"),
        ("Nagendra Shukla", "Nagendra@123", "User")
    ]
    for u, p, r in users:
        user = db.query(models.User).filter(models.User.username == u).first()
        if not user:
            db.add(models.User(username=u, hashed_password=get_password_hash(p), role=r))
        else:
            # Enforce the correct password hash in case it was modified or corrupted
            try:
                if not verify_password(p, user.hashed_password):
                    user.hashed_password = get_password_hash(p)
            except:
                user.hashed_password = get_password_hash(p)
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

class PartyUpdate(BaseModel):
    name: Optional[str] = None
    gst_no: Optional[str] = None
    pan_no: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    party_type: Optional[str] = None

class BiltyCreate(BaseModel):
    lr_no: str
    date: date
    gst_paid_by: str
    delivery_address: str
    lorry_no: Optional[str] = "-"
    origin: Optional[str] = "Ahmedabad"
    destination: Optional[str] = ""
    risk_type: str = "OWNER RISK"
    eway_bill_no: Optional[str] = None
    consignor_id: int
    consignee_id: int
    packages: str = ""
    description: str
    actual_weight: float
    charged_weight: float
    rate: float
    is_fixed_rate: bool = False
    is_direct_lr: Optional[bool] = False
    mazdoor_charges: float = 0.0
    sur_charges: float = 0.0
    st_charges: float = 0.0
    declared_value: Optional[float] = None

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

class InvoiceChargeItem(BaseModel):
    charge_name: str
    amount: float

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
    other_charges: List[InvoiceChargeItem] = []

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

# --- NON-CASH PAYMENT MODE MAPPING ---
NON_CASH_VCH_TYPES = {
    "TDS Deducted by Customer": "TDS Adjustment",
    "Bad Debt Write-Off": "Bad Debt W/O",
    "Discount/Rebate Given": "Discount",
    "Round-Off": "Round-Off",
    "Other Adjustment": "Adjustment",
    "TDS Deduction": "TDS Deduction",
    "Discount/Rebate Received": "Discount Recd",
    "Setoff / Discount (Settled in Full)": "Setoff Gain",
    "Extra Charges / Halting Paid": "Extra Halting",
    "Cash Refund": "Receipt",
    "Bank / NEFT Refund": "Receipt",
    "Vendor Advance Recovery": "Advance Recv",
    "Settlement / Setoff": "Setoff",
}

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

@app.put("/api/parties/{party_id}")
def update_party(party_id: int, party_update: PartyUpdate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    party = db.query(models.Party).filter(models.Party.id == party_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    update_data = party_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(party, key, value)
            
    db.commit()
    db.refresh(party)
    return party


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
    # Unbilled: Belongs to party, NOT attached to invoice (can bill before or after challan)
    return db.query(models.Bilty).filter(
        ((models.Bilty.consignor_id == party_id) & (models.Bilty.gst_paid_by == 'CONSIGNOR')) |
        ((models.Bilty.consignee_id == party_id) & (models.Bilty.gst_paid_by == 'CONSIGNEE'))
    ).filter(models.Bilty.invoice_id == None).all()

@app.post("/api/bilties")
def create_bilty(bilty: BiltyCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if bilty.is_fixed_rate:
        bilty.st_charges = 0.0 # No extra stationery charges on lumpsum
        total_freight = bilty.rate + bilty.mazdoor_charges + bilty.sur_charges
    else:
        total_freight = (bilty.charged_weight * bilty.rate) + bilty.mazdoor_charges + bilty.sur_charges + bilty.st_charges
        
    bilty_data = bilty.dict(exclude={'is_direct_lr'})
    if not bilty_data.get('origin'): bilty_data['origin'] = 'Ahmedabad'
    if not bilty_data.get('destination'): bilty_data['destination'] = '-'
    if not bilty_data.get('lorry_no'): bilty_data['lorry_no'] = '-'
    bilty_data['total_freight_charges'] = total_freight
    db_bilty = models.Bilty(**bilty_data)
    db.add(db_bilty)
    try:
        db.commit()
        db.refresh(db_bilty)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="LR Number already exists or database error.")
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
    if not apply_tds or freight <= 0:
        return 0.0, 0.0
    pan_type = pan_no[3].upper() if pan_no and len(pan_no) >= 4 else 'P'
    rate = 0.01 if pan_type in ['P', 'H'] else 0.02
    return round(freight * rate, 2), rate

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

@app.get("/api/challans")
def get_challans(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    challans = db.query(models.Challan).order_by(models.Challan.id.desc()).limit(100).all()
    res = []
    for ch in challans:
        # Calculate Customer Revenue for this Challan
        customer_revenue = 0.0
        billing_status = "Unbilled"
        inv_nos = []
        for b in ch.bilties:
            if b.invoice_id:
                inv = db.query(models.Invoice).filter(models.Invoice.id == b.invoice_id).first()
                if inv:
                    if inv.bill_no not in inv_nos: inv_nos.append(inv.bill_no)
                    # Allocate invoice other charges proportionally based on freight
                    inv_bilties = db.query(models.Bilty).filter(models.Bilty.invoice_id == inv.id).all()
                    inv_lr_freight_sum = sum(ib.total_freight_charges for ib in inv_bilties) or 1.0
                    other_charges = db.query(func.sum(models.InvoiceCharge.amount)).filter(models.InvoiceCharge.invoice_id == inv.id).scalar() or 0.0
                    lr_share = (b.total_freight_charges or 0.0) / inv_lr_freight_sum
                    customer_revenue += (b.total_freight_charges or 0.0) + (other_charges * lr_share)
            else:
                customer_revenue += (b.total_freight_charges or 0.0)
        
        if inv_nos:
            billing_status = f"Billed ({', '.join(inv_nos)})"
            
        # Vendor Cost
        vendor_cost = ch.total_freight or 0.0
        trip_expenses = db.query(func.sum(models.Expense.amount)).filter(models.Expense.challan_id == ch.id).scalar() or 0.0
        extra_charges = db.query(func.sum(models.VendorPayment.amount_paid)).filter(
            models.VendorPayment.challan_id == ch.id,
            models.VendorPayment.payment_mode.in_(['Extra Charges / Halting Paid', 'Extra Trip Charge / Halting Paid'])
        ).scalar() or 0.0
        setoff_gain = db.query(func.sum(models.VendorPayment.amount_paid)).filter(
            models.VendorPayment.challan_id == ch.id,
            models.VendorPayment.payment_mode.in_(['Setoff / Discount (Settled in Full)', 'Setoff / Discount'])
        ).scalar() or 0.0
        
        total_trip_cost = (vendor_cost + trip_expenses + extra_charges) - setoff_gain
        margin = customer_revenue - total_trip_cost
        margin_pct = (margin / customer_revenue * 100.0) if customer_revenue > 0 else 0.0
        
        res.append({
            "id": ch.id,
            "challan_no": ch.challan_no,
            "date": ch.date.isoformat() if ch.date else "",
            "origin": ch.origin,
            "destination": ch.destination,
            "lorry_no": ch.lorry_no,
            "vendor_id": ch.vendor_id,
            "vendor_name": ch.vendor.name if ch.vendor else "Unknown Vendor",
            "driver_name": ch.driver_name,
            "total_freight": ch.total_freight,
            "advance_paid": ch.advance_paid,
            "balance_freight": ch.balance_freight,
            "tds_amount": ch.tds_amount,
            "net_payable": ch.net_payable,
            "lr_count": len(ch.bilties),
            "lr_nos": [b.lr_no for b in ch.bilties],
            "customer_revenue": round(customer_revenue, 2),
            "billing_status": billing_status,
            "total_trip_cost": round(total_trip_cost, 2),
            "margin": round(margin, 2),
            "margin_pct": round(margin_pct, 1)
        })
    return res

@app.delete("/api/challans/{challan_id}")
def delete_challan(challan_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can delete challans")
    
    challan = db.query(models.Challan).filter(models.Challan.id == challan_id).first()
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
        
    v_payments = db.query(models.VendorPayment).filter(models.VendorPayment.challan_id == challan_id).first()
    if v_payments:
        raise HTTPException(status_code=400, detail="Cannot delete Challan because vendor payout payments have already been recorded against it. Delete the payout records first.")
        
    bilties = db.query(models.Bilty).filter(models.Bilty.challan_id == challan_id).all()
            
    expenses = db.query(models.Expense).filter(models.Expense.challan_id == challan_id).all()
    for exp in expenses:
        exp.challan_id = None
        
    # Unlink all attached Bilties so they revert to undelivered / undispatched status
    for b in bilties:
        b.challan_id = None
        
    db.delete(challan)
    db.commit()
    return {"message": "Challan deleted successfully. Associated Bilties are now available for dispatch again."}

@app.post("/api/invoices")
def create_invoice(invoice: InvoiceCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    bilties = db.query(models.Bilty).filter(models.Bilty.id.in_(invoice.bilty_ids)).all()
    if not bilties: raise HTTPException(status_code=400, detail="No bilties provided")
    total_freight = sum(b.total_freight_charges for b in bilties)
    other_charges_total = sum(c.amount for c in invoice.other_charges)
    total_amount = total_freight + other_charges_total
    igst_amount = 0.0 if invoice.reverse_charge else total_amount * 0.05
    net_amount = total_amount + igst_amount
    
    # Use actual num2words for Indian format
    amount_words = num2words(int(net_amount), lang='en_IN').title() + " Rupees Only"
    
    invoice_data = invoice.dict(exclude={'bilty_ids', 'other_charges'})
    invoice_data.update({'total_amount': total_amount, 'igst_amount': igst_amount, 'net_amount': net_amount, 'amount_in_words': amount_words})
    db_invoice = models.Invoice(**invoice_data)
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    for b in bilties: b.invoice_id = db_invoice.id
    # Save other charges
    for charge in invoice.other_charges:
        db.add(models.InvoiceCharge(invoice_id=db_invoice.id, charge_name=charge.charge_name, amount=charge.amount))
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
    
    # Delete associated other charges
    db.query(models.InvoiceCharge).filter(models.InvoiceCharge.invoice_id == invoice_id).delete()
    
    db.delete(invoice)
    db.commit()
    return {"message": "Invoice deleted successfully"}

@app.get("/api/invoices/{invoice_id}/bilties")
def get_invoice_bilties(invoice_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Bilty).filter(models.Bilty.invoice_id == invoice_id).all()

@app.get("/api/invoices/{invoice_id}/charges")
def get_invoice_charges(invoice_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.InvoiceCharge).filter(models.InvoiceCharge.invoice_id == invoice_id).all()

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
    return db_payment

@app.delete("/api/payments/{payment_id}")
def delete_payment(payment_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can delete payments")
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    db.delete(payment)
    db.commit()
    return {"message": "Payment deleted successfully"}

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

@app.delete("/api/vendor_payments/{payment_id}")
def delete_vendor_payment(payment_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can delete vendor payments")
    payment = db.query(models.VendorPayment).filter(models.VendorPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Vendor payment not found")
    db.delete(payment)
    db.commit()
    return {"message": "Vendor payment deleted successfully"}

@app.post("/api/expenses")
def create_expense(expense: ExpenseCreate, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    db_expense = models.Expense(**expense.dict())
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can delete expenses")
    expense = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
    return {"message": "Expense deleted successfully"}

@app.get("/api/reports/dashboard")
def get_dashboard_analytics(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # 1. Outstanding logic
    parties = db.query(models.Party).all()
    outstanding_results = []
    cleared_accounts = []
    for party in parties:
        if party.party_type == 'Customer':
            unbilled = db.query(func.sum(models.Bilty.total_freight_charges)).filter(
                ((models.Bilty.consignor_id == party.id) & (models.Bilty.gst_paid_by == 'CONSIGNOR')) |
                ((models.Bilty.consignee_id == party.id) & (models.Bilty.gst_paid_by == 'CONSIGNEE'))
            ).filter(models.Bilty.invoice_id == None).scalar() or 0.0
            billed = db.query(func.sum(models.Invoice.net_amount)).filter(models.Invoice.party_id == party.id).scalar() or 0.0
            payments = db.query(func.sum(models.Payment.amount_received)).filter(models.Payment.party_id == party.id).scalar() or 0.0
            net_exposure = unbilled + (billed - payments)
            
            has_transactions = unbilled > 0 or billed > 0 or payments > 0
            if net_exposure > 0.50:
                outstanding_results.append({
                    "party_id": party.id,
                    "party_name": party.name,
                    "unbilled": unbilled,
                    "billed": billed - payments,
                    "net": round(net_exposure, 2),
                    "balance_type": "Receivable",
                    "is_advance": False
                })
            elif net_exposure < -0.50:
                outstanding_results.append({
                    "party_id": party.id,
                    "party_name": party.name,
                    "unbilled": unbilled,
                    "billed": billed - payments,
                    "net": round(net_exposure, 2),
                    "balance_type": "Advance (Cr)",
                    "is_advance": True
                })
            elif has_transactions and abs(net_exposure) <= 0.50:
                cleared_accounts.append({
                    "party_id": party.id,
                    "party_name": party.name,
                    "party_type": "Customer",
                    "net_balance": round(net_exposure, 2)
                })
            
    vendor_outstanding_results = []
    for party in parties:
        if party.party_type == 'Vendor':
            vendor_challans = db.query(func.sum(models.Challan.net_payable)).filter(models.Challan.vendor_id == party.id).scalar() or 0.0
            vendor_payments = db.query(func.sum(models.VendorPayment.amount_paid)).filter(models.VendorPayment.vendor_id == party.id).scalar() or 0.0
            vendor_refunds = db.query(func.sum(models.Payment.amount_received)).filter(models.Payment.party_id == party.id).scalar() or 0.0
            # Net vendor exposure: Payable to vendor = (Challan net payable + Refunds received) - Vendor payments made
            net_vendor_exposure = (vendor_challans + vendor_refunds) - vendor_payments
            
            gross_freight = db.query(func.sum(models.Challan.total_freight)).filter(models.Challan.vendor_id == party.id).scalar() or 0.0
            adv_paid = db.query(func.sum(models.Challan.advance_paid)).filter(models.Challan.vendor_id == party.id).scalar() or 0.0
            has_transactions = gross_freight > 0 or adv_paid > 0 or vendor_payments > 0 or vendor_refunds > 0
            
            if net_vendor_exposure > 0.50:
                vendor_outstanding_results.append({
                    "party_id": party.id,
                    "party_name": party.name,
                    "net": round(net_vendor_exposure, 2),
                    "balance_type": "Payable",
                    "is_advance": False
                })
            elif net_vendor_exposure < -0.50:
                vendor_outstanding_results.append({
                    "party_id": party.id,
                    "party_name": party.name,
                    "net": round(net_vendor_exposure, 2),
                    "balance_type": "Advance (Dr)",
                    "is_advance": True
                })
            elif has_transactions and abs(net_vendor_exposure) <= 0.50:
                cleared_accounts.append({
                    "party_id": party.id,
                    "party_name": party.name,
                    "party_type": "Vendor",
                    "net_balance": round(net_vendor_exposure, 2)
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
        "cleared_accounts": cleared_accounts,
        "revenue_labels": list(revenue_dict.keys()),
        "revenue_data": list(revenue_dict.values()),
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "total_cost": total_cost,
        "net_revenue": net_revenue
    }

@app.get("/api/parties/{party_id}/payments")
def get_party_payments(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Payment).filter(models.Payment.party_id == party_id).order_by(models.Payment.date.desc()).all()

@app.get("/api/parties/{party_id}/vendor_payments")
def get_vendor_payments(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.VendorPayment).filter(models.VendorPayment.vendor_id == party_id).order_by(models.VendorPayment.date.desc()).all()

@app.get("/api/expenses")
def get_expenses(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Expense).order_by(models.Expense.date.desc()).all()

@app.get("/api/parties/{party_id}/tally_ledger")
def get_party_tally_ledger(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    party = db.query(models.Party).filter(models.Party.id == party_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
        
    rows = []
    
    if party.party_type == 'Customer':
        invoices = db.query(models.Invoice).filter(models.Invoice.party_id == party_id).all()
        for inv in invoices:
            rows.append({
                "date": inv.date.isoformat(),
                "vch_type": "Sales",
                "vch_no": inv.bill_no,
                "particulars": f"To Sales Invoice #{inv.bill_no}",
                "debit": inv.net_amount,
                "credit": 0.0
            })
            
        unbilled = db.query(models.Bilty).filter(
            ((models.Bilty.consignor_id == party_id) & (models.Bilty.gst_paid_by == 'CONSIGNOR')) |
            ((models.Bilty.consignee_id == party_id) & (models.Bilty.gst_paid_by == 'CONSIGNEE'))
        ).filter(models.Bilty.invoice_id == None).all()
        for lr in unbilled:
            rows.append({
                "date": lr.date.isoformat(),
                "vch_type": "Unbilled",
                "vch_no": lr.lr_no,
                "particulars": f"To Unbilled Freight (LR #{lr.lr_no} to {lr.destination})",
                "debit": lr.total_freight_charges,
                "credit": 0.0
            })
            
        payments = db.query(models.Payment).filter(models.Payment.party_id == party_id).all()
        for pay in payments:
            inv_ref = ""
            if pay.invoice_id:
                inv = db.query(models.Invoice).filter(models.Invoice.id == pay.invoice_id).first()
                if inv:
                    inv_ref = f" (Agst Inv #{inv.bill_no})"
            # Determine voucher type based on payment mode
            vch_type = NON_CASH_VCH_TYPES.get(pay.payment_mode, "Receipt")
            if pay.payment_mode in NON_CASH_VCH_TYPES:
                particulars = f"By {pay.payment_mode}{inv_ref}"
            else:
                particulars = f"By Bank/Cash Receipt{inv_ref}"
            rows.append({
                "id": pay.id,
                "entry_type": "payment",
                "date": pay.date.isoformat(),
                "vch_type": vch_type,
                "vch_no": pay.utr_no or "-",
                "particulars": particulars,
                "debit": 0.0,
                "credit": pay.amount_received
            })
            
    elif party.party_type == 'Vendor':
        challans = db.query(models.Challan).filter(models.Challan.vendor_id == party_id).all()
        for ch in challans:
            # Gross Lorry Hire booked as Purchase (Credit)
            rows.append({
                "date": ch.date.isoformat(),
                "vch_type": "Purchase",
                "vch_no": ch.challan_no,
                "particulars": f"By Gross Lorry Hire (Challan #{ch.challan_no})",
                "debit": 0.0,
                "credit": ch.total_freight
            })
            # Explicit TDS Deduction line (Debit)
            if ch.tds_amount and ch.tds_amount > 0:
                tds_pct = int(round(ch.tds_rate * 100)) if ch.tds_rate else 1
                rows.append({
                    "date": ch.date.isoformat(),
                    "vch_type": "TDS Deduction",
                    "vch_no": ch.challan_no,
                    "particulars": f"To TDS Deducted u/s 194C @ {tds_pct}% (Challan #{ch.challan_no})",
                    "debit": ch.tds_amount,
                    "credit": 0.0
                })
            # Advance Paid line (Debit)
            if ch.advance_paid and ch.advance_paid > 0:
                rows.append({
                    "date": ch.date.isoformat(),
                    "vch_type": "Payment (Adv)",
                    "vch_no": ch.challan_no,
                    "particulars": f"To Advance Paid (Challan #{ch.challan_no})",
                    "debit": ch.advance_paid,
                    "credit": 0.0
                })
                
        payments = db.query(models.VendorPayment).filter(models.VendorPayment.vendor_id == party_id).all()
        for pay in payments:
            ch_ref = ""
            if pay.challan_id:
                ch = db.query(models.Challan).filter(models.Challan.id == pay.challan_id).first()
                if ch:
                    ch_ref = f" (Agst Ch #{ch.challan_no})"
            vch_type = NON_CASH_VCH_TYPES.get(pay.payment_mode, "Payment")
            if pay.payment_mode in NON_CASH_VCH_TYPES:
                particulars = f"To {pay.payment_mode}{ch_ref}"
            else:
                particulars = f"To Bank/Cash Payment{ch_ref}"
            rows.append({
                "id": pay.id,
                "entry_type": "vendor_payment",
                "date": pay.date.isoformat(),
                "vch_type": vch_type,
                "vch_no": pay.utr_no or "-",
                "particulars": particulars,
                "debit": pay.amount_paid,
                "credit": 0.0
            })

        # Receipts / refunds / recoveries received from vendor (models.Payment)
        receipts = db.query(models.Payment).filter(models.Payment.party_id == party_id).all()
        for rec in receipts:
            vch_type = NON_CASH_VCH_TYPES.get(rec.payment_mode, "Receipt")
            particulars = f"By {rec.payment_mode} (Advance Refund / Recovery)"
            rows.append({
                "id": rec.id,
                "entry_type": "payment",
                "date": rec.date.isoformat(),
                "vch_type": vch_type,
                "vch_no": rec.utr_no or "-",
                "particulars": particulars,
                "debit": 0.0,
                "credit": rec.amount_received
            })
            
    # Sort chronologically
    rows.sort(key=lambda x: x['date'])
    balance = 0.0
    for r in rows:
        if party.party_type == 'Customer':
            balance += r['debit'] - r['credit']
            r['balance_str'] = f"{abs(balance):.2f} {'Dr' if balance >= 0 else 'Cr'}"
            r['balance'] = balance
        else: # Vendor
            balance += r['credit'] - r['debit']
            r['balance_str'] = f"{abs(balance):.2f} {'Cr' if balance >= 0 else 'Dr'}"
            r['balance'] = balance
            
    return rows

@app.delete("/api/reset_database")
def reset_database(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can reset database")
    
    # Delete in order of foreign keys
    db.query(models.InvoiceCharge).delete()
    db.query(models.Expense).delete()
    db.query(models.VendorPayment).delete()
    db.query(models.Payment).delete()
    db.query(models.Bilty).delete()
    db.query(models.Invoice).delete()
    db.query(models.Challan).delete()
    db.query(models.Party).delete()
    db.commit()
    return {"message": "Database wiped successfully!"}

from fastapi.encoders import jsonable_encoder
import json
from fastapi import File, UploadFile
from fastapi.responses import Response
from sqlalchemy import text

@app.get("/api/backup")
def backup_database(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can backup database")
    
    backup_data = {}
    for table in models.Base.metadata.sorted_tables:
        results = db.execute(table.select()).fetchall()
        backup_data[table.name] = [dict(r._mapping) for r in results]
    
    filename = f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
    content = json.dumps(jsonable_encoder(backup_data))
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/restore")
async def restore_database(file: UploadFile = File(...), db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Only SuperAdmin can restore database")
    
    content = await file.read()
    try:
        backup_data = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    try:
        # 1. Clear current tables
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        
        # 2. Insert backup data
        for table in models.Base.metadata.sorted_tables:
            if table.name in backup_data and backup_data[table.name]:
                db.execute(table.insert(), backup_data[table.name])
        
        # 3. Update PostgreSQL sequences safely
        if engine.dialect.name == "postgresql":
            for table in models.Base.metadata.sorted_tables:
                seq_name = f"{table.name}_id_seq"
                db.execute(text(f"SELECT setval('{seq_name}', coalesce(max(id), 1), max(id) IS NOT null) FROM {table.name}"))
                
        db.commit()
        return {"message": "Database restored successfully!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

# --- EXCEL REPORT ENDPOINTS ---
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from io import BytesIO

def _excel_response(wb, filename):
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return Response(content=output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})

def _setup_sheet(ws, title, headers):
    hdr_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    hdr_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    col_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    col_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(row=1, column=1, value="D TRANS EXPRESS LOGISTICS").font = hdr_font
    ws.cell(row=1, column=1).fill = hdr_fill
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 30
    
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws.cell(row=2, column=1, value=title).font = Font(name="Calibri", size=12, bold=True)
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="center")
    
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=ci, value=h)
        cell.font = col_font
        cell.fill = col_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[4].height = 24
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}4"
    return border

def _auto_width(ws):
    for col in ws.columns:
        mx = 0
        cl = get_column_letter(col[0].column)
        for cell in col:
            v = str(cell.value) if cell.value else ""
            if len(v) > mx: mx = len(v)
        ws.column_dimensions[cl].width = max(mx + 3, 12)

def _add_total_row(ws, row, col_sums, num_cols, border):
    bold = Font(name="Calibri", size=11, bold=True)
    dbl = Border(top=Side(style="double", color="000000"), bottom=Side(style="double", color="000000"))
    ws.cell(row=row, column=1, value="TOTAL").font = bold
    for ci in range(1, num_cols + 1):
        ws.cell(row=row, column=ci).border = dbl
        ws.cell(row=row, column=ci).font = bold
    for ci, val in col_sums.items():
        ws.cell(row=row, column=ci, value=round(val, 2)).number_format = '#,##0.00'

def _fmt_date(d):
    if not d: return ""
    if isinstance(d, str): 
        try:
            d = date.fromisoformat(d)
        except: return d
    return d.strftime("%d-%m-%Y")

@app.get("/api/reports/excel/customer_ledger/{party_id}")
def excel_customer_ledger(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    party = db.query(models.Party).filter(models.Party.id == party_id).first()
    if not party: raise HTTPException(404, "Party not found")
    ledger_rows = get_party_tally_ledger(party_id, db, user)
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Ledger"
    headers = ["Date", "Vch Type", "Vch No.", "Particulars", "Debit (₹)", "Credit (₹)", "Balance"]
    bdr = _setup_sheet(ws, f"Statement of Account: {party.name}", headers)
    ws.cell(row=3, column=1, value=f"GSTIN: {party.gst_no or 'N/A'}  |  PAN: {party.pan_no or 'N/A'}").font = Font(size=10, italic=True)
    
    for ri, r in enumerate(ledger_rows, 5):
        ws.cell(row=ri, column=1, value=_fmt_date(r['date'])).border = bdr
        ws.cell(row=ri, column=2, value=r['vch_type']).border = bdr
        ws.cell(row=ri, column=3, value=r['vch_no']).border = bdr
        ws.cell(row=ri, column=4, value=r['particulars']).border = bdr
        c5 = ws.cell(row=ri, column=5, value=r['debit'] if r['debit'] > 0 else None)
        c5.border = bdr; c5.number_format = '#,##0.00'
        c6 = ws.cell(row=ri, column=6, value=r['credit'] if r['credit'] > 0 else None)
        c6.border = bdr; c6.number_format = '#,##0.00'
        ws.cell(row=ri, column=7, value=r['balance_str']).border = bdr
    
    tr = len(ledger_rows) + 5
    _add_total_row(ws, tr, {5: sum(r['debit'] for r in ledger_rows), 6: sum(r['credit'] for r in ledger_rows)}, 7, bdr)
    if ledger_rows:
        ws.cell(row=tr, column=7, value=ledger_rows[-1]['balance_str'])
    _auto_width(ws)
    return _excel_response(wb, f"Ledger_{party.name.replace(' ','_')}.xlsx")

@app.get("/api/reports/excel/vendor_ledger/{party_id}")
def excel_vendor_ledger(party_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return excel_customer_ledger(party_id, db, user)

@app.get("/api/reports/excel/invoice_register")
def excel_invoice_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "Invoice Register"
    headers = ["Sr.", "Invoice No.", "Date", "Customer", "GSTIN", "LR Count", "Freight (₹)", "Other Charges (₹)", "Taxable (₹)", "IGST (₹)", "Net Amount (₹)", "Received (₹)", "Balance (₹)"]
    bdr = _setup_sheet(ws, "Invoice Register", headers)
    invs = db.query(models.Invoice).order_by(models.Invoice.date).all()
    sums = {7:0, 8:0, 9:0, 10:0, 11:0, 12:0, 13:0}
    for i, inv in enumerate(invs, 1):
        ri = i + 4
        lr_count = db.query(models.Bilty).filter(models.Bilty.invoice_id == inv.id).count()
        freight = sum(b.total_freight_charges for b in db.query(models.Bilty).filter(models.Bilty.invoice_id == inv.id).all())
        other = db.query(func.sum(models.InvoiceCharge.amount)).filter(models.InvoiceCharge.invoice_id == inv.id).scalar() or 0.0
        paid = db.query(func.sum(models.Payment.amount_received)).filter(models.Payment.invoice_id == inv.id).scalar() or 0.0
        bal = inv.net_amount - paid
        party = db.query(models.Party).filter(models.Party.id == inv.party_id).first()
        vals = [i, inv.bill_no, _fmt_date(inv.date), party.name if party else "", party.gst_no if party else "", lr_count, freight, other, inv.total_amount, inv.igst_amount, inv.net_amount, paid, bal]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci >= 7: c.number_format = '#,##0.00'
        for ci in [7,8,9,10,11,12,13]: sums[ci] += vals[ci-1]
    _add_total_row(ws, len(invs)+5, sums, 13, bdr)
    _auto_width(ws)
    return _excel_response(wb, "Invoice_Register.xlsx")

@app.get("/api/reports/excel/challan_register")
def excel_challan_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "Challan Register"
    headers = ["Challan No.", "Date", "Vendor", "PAN", "Lorry No.", "From → To", "LR Count", "LR Nos", "Freight (₹)", "Advance (₹)", "TDS %", "TDS (₹)", "Net Payable (₹)", "Paid (₹)", "Balance (₹)"]
    bdr = _setup_sheet(ws, "Challan Register", headers)
    challans = db.query(models.Challan).order_by(models.Challan.date).all()
    sums = {9:0, 10:0, 12:0, 13:0, 14:0, 15:0}
    for i, ch in enumerate(challans):
        ri = i + 5
        paid = db.query(func.sum(models.VendorPayment.amount_paid)).filter(models.VendorPayment.challan_id == ch.id).scalar() or 0.0
        bal = ch.net_payable - paid
        lr_nos = ", ".join([b.lr_no for b in ch.bilties])
        vals = [ch.challan_no, _fmt_date(ch.date), ch.vendor.name if ch.vendor else "", ch.vendor_pan, ch.lorry_no, f"{ch.origin} → {ch.destination}", len(ch.bilties), lr_nos, ch.total_freight, ch.advance_paid, f"{ch.tds_rate*100:.0f}%", ch.tds_amount, ch.net_payable, paid, bal]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci in [9,10,12,13,14,15]: c.number_format = '#,##0.00'
        for ci in [9,10,12,13]: sums[ci] += vals[ci-1]
        sums[14] += paid; sums[15] += bal
    _add_total_row(ws, len(challans)+5, sums, 15, bdr)
    _auto_width(ws)
    return _excel_response(wb, "Challan_Register.xlsx")

@app.get("/api/reports/excel/payment_register")
def excel_payment_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "Payment Register"
    headers = ["Date", "Customer", "Against Invoice", "Amount (₹)", "Mode", "Reference/UTR"]
    bdr = _setup_sheet(ws, "Payment Register (Customer Receipts)", headers)
    pays = db.query(models.Payment).order_by(models.Payment.date).all()
    total = 0
    for i, p in enumerate(pays):
        ri = i + 5
        party = db.query(models.Party).filter(models.Party.id == p.party_id).first()
        inv_ref = "Unallocated"
        if p.invoice_id:
            inv = db.query(models.Invoice).filter(models.Invoice.id == p.invoice_id).first()
            if inv: inv_ref = inv.bill_no
        vals = [_fmt_date(p.date), party.name if party else "", inv_ref, p.amount_received, p.payment_mode, p.utr_no or ""]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci == 4: c.number_format = '#,##0.00'
        total += p.amount_received
    _add_total_row(ws, len(pays)+5, {4: total}, 6, bdr)
    _auto_width(ws)
    return _excel_response(wb, "Payment_Register.xlsx")

@app.get("/api/reports/excel/vendor_payment_register")
def excel_vendor_payment_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "Vendor Payments"
    headers = ["Date", "Vendor", "Against Challan", "Amount (₹)", "Mode", "Reference/UTR"]
    bdr = _setup_sheet(ws, "Vendor Payment Register (Payouts)", headers)
    pays = db.query(models.VendorPayment).order_by(models.VendorPayment.date).all()
    total = 0
    for i, p in enumerate(pays):
        ri = i + 5
        vendor = db.query(models.Party).filter(models.Party.id == p.vendor_id).first()
        ch_ref = "Unallocated"
        if p.challan_id:
            ch = db.query(models.Challan).filter(models.Challan.id == p.challan_id).first()
            if ch: ch_ref = ch.challan_no
        vals = [_fmt_date(p.date), vendor.name if vendor else "", ch_ref, p.amount_paid, p.payment_mode, p.utr_no or ""]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci == 4: c.number_format = '#,##0.00'
        total += p.amount_paid
    _add_total_row(ws, len(pays)+5, {4: total}, 6, bdr)
    _auto_width(ws)
    return _excel_response(wb, "Vendor_Payment_Register.xlsx")

@app.get("/api/reports/excel/lr_register")
def excel_lr_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "LR Register"
    headers = ["LR No.", "Date", "Consignor", "Consignee", "From", "To", "Lorry No.", "Description", "Pkgs", "Wt (MT)", "Rate", "Freight (₹)", "Declared Value (₹)", "Challan", "Invoice", "Status"]
    bdr = _setup_sheet(ws, "Consignment (LR) Register", headers)
    bilties = db.query(models.Bilty).order_by(models.Bilty.date).all()
    total_freight = 0
    for i, b in enumerate(bilties):
        ri = i + 5
        consignor = db.query(models.Party).filter(models.Party.id == b.consignor_id).first()
        consignee = db.query(models.Party).filter(models.Party.id == b.consignee_id).first()
        ch_no = ""
        if b.challan_id:
            ch = db.query(models.Challan).filter(models.Challan.id == b.challan_id).first()
            if ch: ch_no = ch.challan_no
        inv_no = ""
        if b.invoice_id:
            inv = db.query(models.Invoice).filter(models.Invoice.id == b.invoice_id).first()
            if inv: inv_no = inv.bill_no
        status = "Billed" if b.invoice_id else ("Dispatched" if b.challan_id else "Pending")
        vals = [b.lr_no, _fmt_date(b.date), consignor.name if consignor else "", consignee.name if consignee else "", b.origin or "", b.destination or "", b.lorry_no or "", b.description or "", b.packages or "", b.charged_weight, "Fixed" if b.is_fixed_rate else b.rate, b.total_freight_charges, b.declared_value, ch_no, inv_no, status]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci in [12, 13]: c.number_format = '#,##0.00'
        total_freight += b.total_freight_charges or 0
    _add_total_row(ws, len(bilties)+5, {12: total_freight}, 16, bdr)
    _auto_width(ws)
    return _excel_response(wb, "LR_Register.xlsx")

@app.get("/api/reports/excel/outstanding_summary")
def excel_outstanding_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "Outstanding"
    headers = ["Party Name", "Type", "GSTIN", "PAN", "Unbilled (₹)", "Billed Unpaid (₹)", "Net Outstanding (₹)", "Status"]
    bdr = _setup_sheet(ws, "Party-Wise Outstanding Summary", headers)
    dash = get_dashboard_analytics(db, user)
    ri = 5
    for o in dash['outstanding']:
        party = db.query(models.Party).filter(models.Party.id == o['party_id']).first()
        vals = [o['party_name'], "Customer", party.gst_no if party else "", party.pan_no if party else "", o['unbilled'], o['billed'], o['net'], "Outstanding"]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci in [5,6,7]: c.number_format = '#,##0.00'
        ri += 1
    for o in dash['vendor_outstanding']:
        party = db.query(models.Party).filter(models.Party.id == o['party_id']).first()
        status_label = "Advance / Dr (Excess Paid)" if o.get('is_advance') else "Payable Outstanding"
        vals = [o['party_name'], "Vendor", party.gst_no if party else "", party.pan_no if party else "", 0, o['net'], o['net'], status_label]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci in [5,6,7]: c.number_format = '#,##0.00'
        ri += 1
    for o in dash['cleared_accounts']:
        vals = [o['party_name'], o['party_type'], "", "", 0, 0, 0, "Cleared ✅"]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
        ri += 1
    _auto_width(ws)
    return _excel_response(wb, "Outstanding_Summary.xlsx")

@app.get("/api/reports/excel/expense_register")
def excel_expense_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "Expenses"
    headers = ["Date", "Expense Type", "Description", "Amount (₹)"]
    bdr = _setup_sheet(ws, "Expense Register", headers)
    exps = db.query(models.Expense).order_by(models.Expense.date).all()
    total = 0
    for i, e in enumerate(exps):
        ri = i + 5
        vals = [_fmt_date(e.date), e.expense_type, e.description, e.amount]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci == 4: c.number_format = '#,##0.00'
        total += e.amount
    _add_total_row(ws, len(exps)+5, {4: total}, 4, bdr)
    _auto_width(ws)
    return _excel_response(wb, "Expense_Register.xlsx")

@app.get("/api/reports/excel/tds_summary")
def excel_tds_summary(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    wb = Workbook(); ws = wb.active; ws.title = "TDS Summary"
    headers = ["Vendor Name", "PAN", "Total Freight (₹)", "TDS Rate", "TDS Amount (₹)"]
    bdr = _setup_sheet(ws, "TDS Summary Report (Section 194C)", headers)
    vendors = db.query(models.Party).filter(models.Party.party_type == 'Vendor').all()
    ri = 5; total_freight = 0; total_tds = 0
    for v in vendors:
        challans = db.query(models.Challan).filter(models.Challan.vendor_id == v.id).all()
        if not challans: continue
        freight = sum(c.total_freight for c in challans)
        tds = sum(c.tds_amount for c in challans)
        rate = challans[0].tds_rate if challans else 0
        vals = [v.name, v.pan_no or "", freight, f"{rate*100:.0f}%", tds]
        for ci, val in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=val); c.border = bdr
            if ci in [3,5]: c.number_format = '#,##0.00'
        total_freight += freight; total_tds += tds; ri += 1
    _add_total_row(ws, ri, {3: total_freight, 5: total_tds}, 5, bdr)
    _auto_width(ws)
    return _excel_response(wb, "TDS_Summary.xlsx")

@app.get("/api/reports/excel/journal_register")
def excel_journal_register(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Non-cash adjustments register — payments with modes like Bad Debt, TDS, Discount, etc."""
    wb = Workbook(); ws = wb.active; ws.title = "Non-Cash Adjustments"
    headers = ["Date", "Type (Mode)", "Party", "Against", "Amount (₹)", "Reference"]
    bdr = _setup_sheet(ws, "Non-Cash Adjustments Register", headers)
    cash_modes = {"NEFT", "Cheque", "Cash"}
    
    ri = 5; total = 0
    # Customer non-cash
    pays = db.query(models.Payment).filter(~models.Payment.payment_mode.in_(cash_modes)).order_by(models.Payment.date).all()
    for p in pays:
        party = db.query(models.Party).filter(models.Party.id == p.party_id).first()
        inv_ref = ""
        if p.invoice_id:
            inv = db.query(models.Invoice).filter(models.Invoice.id == p.invoice_id).first()
            if inv: inv_ref = inv.bill_no
        vals = [_fmt_date(p.date), p.payment_mode, party.name if party else "", inv_ref or "Unallocated", p.amount_received, p.utr_no or ""]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci == 5: c.number_format = '#,##0.00'
        total += p.amount_received; ri += 1
    # Vendor non-cash
    vpays = db.query(models.VendorPayment).filter(~models.VendorPayment.payment_mode.in_(cash_modes)).order_by(models.VendorPayment.date).all()
    for p in vpays:
        vendor = db.query(models.Party).filter(models.Party.id == p.vendor_id).first()
        ch_ref = ""
        if p.challan_id:
            ch = db.query(models.Challan).filter(models.Challan.id == p.challan_id).first()
            if ch: ch_ref = ch.challan_no
        vals = [_fmt_date(p.date), p.payment_mode, vendor.name if vendor else "", ch_ref or "Unallocated", p.amount_paid, p.utr_no or ""]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v); c.border = bdr
            if ci == 5: c.number_format = '#,##0.00'
        total += p.amount_paid; ri += 1
    _add_total_row(ws, ri, {5: total}, 6, bdr)
    _auto_width(ws)
    return _excel_response(wb, "NonCash_Adjustments_Register.xlsx")

@app.get("/api/reports/excel/revenue_expense_detail")
def excel_revenue_expense_detail(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Detailed Revenue & Expense Bifurcation Report"""
    wb = Workbook(); ws = wb.active; ws.title = "Revenue & Expense Detail"
    
    hdr_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    hdr_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    section_font = Font(name="Calibri", size=12, bold=True, color="1F497D")
    sub_font = Font(name="Calibri", size=11, bold=True)
    normal = Font(name="Calibri", size=11)
    total_font = Font(name="Calibri", size=12, bold=True)
    grand_font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    grand_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    
    ws.column_dimensions['A'].width = 45
    ws.column_dimensions['B'].width = 20
    
    # Title
    ws.merge_cells("A1:B1")
    ws.cell(row=1, column=1, value="D TRANS EXPRESS LOGISTICS").font = hdr_font
    ws.cell(row=1, column=1).fill = hdr_fill
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 30
    ws.merge_cells("A2:B2")
    ws.cell(row=2, column=1, value="Revenue & Expense Bifurcation (Detailed)").font = Font(size=12, bold=True)
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="center")
    
    ri = 4
    # === REVENUE SECTION ===
    ws.cell(row=ri, column=1, value="REVENUE (INCOME)").font = section_font
    ri += 1
    
    # A. Freight Income - Customer wise
    ws.cell(row=ri, column=1, value="A. Freight Income (Customer-Wise)").font = sub_font; ri += 1
    customers = db.query(models.Party).filter(models.Party.party_type == 'Customer').all()
    freight_total = 0
    for cust in customers:
        inv_total = db.query(func.sum(models.Invoice.total_amount)).filter(models.Invoice.party_id == cust.id).scalar() or 0
        # Subtract other charges to get pure freight
        inv_ids = [inv.id for inv in db.query(models.Invoice).filter(models.Invoice.party_id == cust.id).all()]
        other_charges_for_cust = 0
        if inv_ids:
            other_charges_for_cust = db.query(func.sum(models.InvoiceCharge.amount)).filter(models.InvoiceCharge.invoice_id.in_(inv_ids)).scalar() or 0
        pure_freight = inv_total - other_charges_for_cust
        if pure_freight > 0:
            ws.cell(row=ri, column=1, value=f"   {cust.name}").font = normal
            c = ws.cell(row=ri, column=2, value=round(pure_freight, 2)); c.number_format = '#,##0.00'; c.font = normal
            freight_total += pure_freight; ri += 1
    ws.cell(row=ri, column=1, value="   Total Freight Income").font = total_font
    c = ws.cell(row=ri, column=2, value=round(freight_total, 2)); c.number_format = '#,##0.00'; c.font = total_font
    ri += 2
    
    # B. Other Charges Income - Charge wise
    ws.cell(row=ri, column=1, value="B. Other Charges Income (Charge-Wise)").font = sub_font; ri += 1
    charges = db.query(models.InvoiceCharge.charge_name, func.sum(models.InvoiceCharge.amount)).group_by(models.InvoiceCharge.charge_name).all()
    other_total = 0
    for name, amt in charges:
        ws.cell(row=ri, column=1, value=f"   {name}").font = normal
        c = ws.cell(row=ri, column=2, value=round(amt, 2)); c.number_format = '#,##0.00'; c.font = normal
        other_total += amt; ri += 1
    ws.cell(row=ri, column=1, value="   Total Other Charges").font = total_font
    c = ws.cell(row=ri, column=2, value=round(other_total, 2)); c.number_format = '#,##0.00'; c.font = total_font
    ri += 2
    
    # C. IGST collected
    igst_total = db.query(func.sum(models.Invoice.igst_amount)).scalar() or 0
    if igst_total > 0:
        ws.cell(row=ri, column=1, value="C. IGST Collected").font = sub_font
        c = ws.cell(row=ri, column=2, value=round(igst_total, 2)); c.number_format = '#,##0.00'; c.font = sub_font
        ri += 2
    
    total_revenue = freight_total + other_total + igst_total
    ws.merge_cells(f"A{ri}:A{ri}")
    ws.cell(row=ri, column=1, value="═══ TOTAL REVENUE ═══").font = grand_font; ws.cell(row=ri, column=1).fill = green_fill
    c = ws.cell(row=ri, column=2, value=round(total_revenue, 2)); c.number_format = '#,##0.00'; c.font = grand_font; c.fill = green_fill
    ri += 2
    
    # === EXPENSE SECTION ===
    ws.cell(row=ri, column=1, value="EXPENSES (COST)").font = section_font
    ri += 1
    
    # D. Lorry Hire - Vendor wise
    ws.cell(row=ri, column=1, value="D. Lorry Hire / Freight Paid (Vendor-Wise)").font = sub_font; ri += 1
    vendors = db.query(models.Party).filter(models.Party.party_type == 'Vendor').all()
    lorry_total = 0
    for v in vendors:
        vfreight = db.query(func.sum(models.Challan.total_freight)).filter(models.Challan.vendor_id == v.id).scalar() or 0
        if vfreight > 0:
            ws.cell(row=ri, column=1, value=f"   {v.name}").font = normal
            c = ws.cell(row=ri, column=2, value=round(vfreight, 2)); c.number_format = '#,##0.00'; c.font = normal
            lorry_total += vfreight; ri += 1
    ws.cell(row=ri, column=1, value="   Total Lorry Hire").font = total_font
    c = ws.cell(row=ri, column=2, value=round(lorry_total, 2)); c.number_format = '#,##0.00'; c.font = total_font
    ri += 2
    
    # E. General Expenses - Type wise
    ws.cell(row=ri, column=1, value="E. General Expenses (Type-Wise)").font = sub_font; ri += 1
    exp_groups = db.query(models.Expense.expense_type, func.sum(models.Expense.amount)).group_by(models.Expense.expense_type).all()
    exp_total = 0
    for etype, amt in exp_groups:
        ws.cell(row=ri, column=1, value=f"   {etype}").font = normal
        c = ws.cell(row=ri, column=2, value=round(amt, 2)); c.number_format = '#,##0.00'; c.font = normal
        exp_total += amt; ri += 1
    ws.cell(row=ri, column=1, value="   Total General Expenses").font = total_font
    c = ws.cell(row=ri, column=2, value=round(exp_total, 2)); c.number_format = '#,##0.00'; c.font = total_font
    ri += 2
    
    # F. Non-Cash Write-Offs
    cash_modes = {"NEFT", "Cheque", "Cash"}
    non_cash_pays = db.query(models.Payment).filter(~models.Payment.payment_mode.in_(cash_modes)).all()
    writeoff_dict = {}
    for p in non_cash_pays:
        writeoff_dict[p.payment_mode] = writeoff_dict.get(p.payment_mode, 0) + p.amount_received
    
    if writeoff_dict:
        ws.cell(row=ri, column=1, value="F. Non-Cash Adjustments (Customer Side)").font = sub_font; ri += 1
        wo_total = 0
        for mode, amt in writeoff_dict.items():
            ws.cell(row=ri, column=1, value=f"   {mode}").font = normal
            c = ws.cell(row=ri, column=2, value=round(amt, 2)); c.number_format = '#,##0.00'; c.font = normal
            wo_total += amt; ri += 1
        ws.cell(row=ri, column=1, value="   Total Non-Cash Adjustments").font = total_font
        c = ws.cell(row=ri, column=2, value=round(wo_total, 2)); c.number_format = '#,##0.00'; c.font = total_font
        ri += 2
    
    # G. TDS on Challans
    tds_total = db.query(func.sum(models.Challan.tds_amount)).scalar() or 0
    if tds_total > 0:
        ws.cell(row=ri, column=1, value="G. TDS Deducted on Vendor Challans").font = sub_font
        c = ws.cell(row=ri, column=2, value=round(tds_total, 2)); c.number_format = '#,##0.00'; c.font = sub_font
        ri += 2
    
    total_expense = lorry_total + exp_total
    ws.cell(row=ri, column=1, value="═══ TOTAL EXPENSES ═══").font = grand_font; ws.cell(row=ri, column=1).fill = red_fill
    c = ws.cell(row=ri, column=2, value=round(total_expense, 2)); c.number_format = '#,##0.00'; c.font = grand_font; c.fill = red_fill
    ri += 2
    
    # NET PROFIT
    net_profit = total_revenue - total_expense
    ws.cell(row=ri, column=1, value="═══ NET PROFIT / (LOSS) ═══").font = grand_font; ws.cell(row=ri, column=1).fill = grand_fill
    c = ws.cell(row=ri, column=2, value=round(net_profit, 2)); c.number_format = '#,##0.00'; c.font = grand_font; c.fill = grand_fill
    
    return _excel_response(wb, "Revenue_Expense_Bifurcation.xlsx")

@app.get("/api/reports/excel/challan_margin")
def excel_challan_margin(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Challan Profitability & Trip Margin Report"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Challan Margin"
    
    headers = [
        "Sr.", "Challan No.", "Date", "Route (From → To)", "Lorry No.", "Vendor", "LR Nos.",
        "Customer Name", "Billing Status", "Invoice No.", "Customer Freight (₹)", "Other Charges (₹)",
        "Total Revenue (₹)", "Vendor Freight (₹)", "Trip Exp / Halting (₹)", "Total Cost (₹)",
        "Gross Margin (₹)", "Margin %"
    ]
    bdr = _setup_sheet(ws, "Challan Profitability & Trip Margin Report", headers)
    
    green_font = Font(name="Calibri", size=10, bold=True, color="006100")
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red_font = Font(name="Calibri", size=10, bold=True, color="9C0006")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    
    challans = db.query(models.Challan).order_by(models.Challan.date.asc()).all()
    
    tot_cust_freight = 0.0
    tot_other_charges = 0.0
    tot_revenue = 0.0
    tot_vendor_freight = 0.0
    tot_trip_expenses = 0.0
    tot_cost = 0.0
    tot_margin = 0.0
    
    for i, ch in enumerate(challans, 1):
        ri = i + 4
        cust_freight = 0.0
        allocated_other_charges = 0.0
        inv_nos = []
        cust_names = []
        
        for b in ch.bilties:
            cust_name = b.consignor.name if b.consignor else ""
            if cust_name and cust_name not in cust_names:
                cust_names.append(cust_name)
            
            b_freight = b.total_freight_charges or 0.0
            cust_freight += b_freight
            
            if b.invoice_id:
                inv = db.query(models.Invoice).filter(models.Invoice.id == b.invoice_id).first()
                if inv:
                    if inv.bill_no not in inv_nos: inv_nos.append(inv.bill_no)
                    inv_bilties = db.query(models.Bilty).filter(models.Bilty.invoice_id == inv.id).all()
                    inv_freight_sum = sum(ib.total_freight_charges for ib in inv_bilties) or 1.0
                    inv_charges = db.query(func.sum(models.InvoiceCharge.amount)).filter(models.InvoiceCharge.invoice_id == inv.id).scalar() or 0.0
                    lr_share = b_freight / inv_freight_sum
                    allocated_other_charges += (inv_charges * lr_share)
                    
        total_rev = cust_freight + allocated_other_charges
        vendor_freight = ch.total_freight or 0.0
        trip_exp = db.query(func.sum(models.Expense.amount)).filter(models.Expense.challan_id == ch.id).scalar() or 0.0
        extra_halting = db.query(func.sum(models.VendorPayment.amount_paid)).filter(
            models.VendorPayment.challan_id == ch.id,
            models.VendorPayment.payment_mode.in_(['Extra Charges / Halting Paid', 'Extra Trip Charge / Halting Paid'])
        ).scalar() or 0.0
        setoff = db.query(func.sum(models.VendorPayment.amount_paid)).filter(
            models.VendorPayment.challan_id == ch.id,
            models.VendorPayment.payment_mode.in_(['Setoff / Discount (Settled in Full)', 'Setoff / Discount'])
        ).scalar() or 0.0
        
        trip_expenses = trip_exp + extra_halting - setoff
        trip_cost = vendor_freight + trip_expenses
        margin = total_rev - trip_cost
        margin_pct = (margin / total_rev * 100.0) if total_rev > 0 else 0.0
        
        vals = [
            i,
            ch.challan_no,
            _fmt_date(ch.date),
            f"{ch.origin} → {ch.destination}",
            ch.lorry_no,
            ch.vendor.name if ch.vendor else "Unknown",
            ", ".join([b.lr_no for b in ch.bilties]),
            ", ".join(cust_names) if cust_names else "-",
            "Billed" if inv_nos else "Unbilled",
            ", ".join(inv_nos) if inv_nos else "-",
            round(cust_freight, 2),
            round(allocated_other_charges, 2),
            round(total_rev, 2),
            round(vendor_freight, 2),
            round(trip_expenses, 2),
            round(trip_cost, 2),
            round(margin, 2),
            f"{margin_pct:.1f}%"
        ]
        
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.border = bdr
            if ci in [11, 12, 13, 14, 15, 16, 17]:
                cell.number_format = '#,##0.00'
            if ci in [17, 18]: # Margin and Margin %
                if margin >= 0:
                    cell.font = green_font
                    cell.fill = green_fill
                else:
                    cell.font = red_font
                    cell.fill = red_fill
                    
        tot_cust_freight += cust_freight
        tot_other_charges += allocated_other_charges
        tot_revenue += total_rev
        tot_vendor_freight += vendor_freight
        tot_trip_expenses += trip_expenses
        tot_cost += trip_cost
        tot_margin += margin
        
    # Total row
    tot_row = len(challans) + 5
    sums = {
        11: tot_cust_freight,
        12: tot_other_charges,
        13: tot_revenue,
        14: tot_vendor_freight,
        15: tot_trip_expenses,
        16: tot_cost,
        17: tot_margin
    }
    _add_total_row(ws, tot_row, sums, 18, bdr)
    overall_pct = (tot_margin / tot_revenue * 100.0) if tot_revenue > 0 else 0.0
    avg_cell = ws.cell(row=tot_row, column=18, value=f"{overall_pct:.1f}%")
    if tot_margin >= 0:
        avg_cell.font = green_font
        avg_cell.fill = green_fill
    else:
        avg_cell.font = red_font
        avg_cell.fill = red_fill
        
    _auto_width(ws)
    return _excel_response(wb, "Challan_Profitability_Margin_Report.xlsx")

@app.get("/api/reports/excel/profit_loss")
def excel_profit_loss(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return excel_revenue_expense_detail(db, user)

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
