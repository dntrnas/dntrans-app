import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey, create_engine, Text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="User") # "SuperAdmin" or "User"

class Party(Base):
    __tablename__ = 'parties'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    gst_no = Column(String, nullable=True)
    pan_no = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    party_type = Column(String) 

class Bilty(Base):
    __tablename__ = 'bilties'
    id = Column(Integer, primary_key=True, index=True)
    lr_no = Column(String, unique=True, index=True)
    date = Column(Date, default=datetime.date.today)
    gst_paid_by = Column(String) 
    delivery_address = Column(Text)
    lorry_no = Column(String)
    origin = Column(String, default="Ahmedabad")
    destination = Column(String, default="")
    risk_type = Column(String) 
    eway_bill_no = Column(String, nullable=True)
    
    consignor_id = Column(Integer, ForeignKey('parties.id'))
    consignee_id = Column(Integer, ForeignKey('parties.id'))
    
    packages = Column(String)
    description = Column(Text)
    actual_weight = Column(Float)
    charged_weight = Column(Float)
    
    rate = Column(Float)
    is_fixed_rate = Column(Boolean, default=False)
    mazdoor_charges = Column(Float, default=0.0)
    sur_charges = Column(Float, default=0.0)
    st_charges = Column(Float, default=100.0)
    total_freight_charges = Column(Float)
    
    insurance_company = Column(String, nullable=True)
    insurance_policy_no = Column(String, nullable=True)
    insurance_date = Column(Date, nullable=True)
    insurance_amount = Column(Float, nullable=True)
    insurance_risk = Column(String, nullable=True)
    
    road_permit_no = Column(String, nullable=True)
    demurrage_days = Column(Integer, nullable=True)
    demurrage_rate = Column(Float, nullable=True)
    
    challan_id = Column(Integer, ForeignKey('challans.id'), nullable=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=True)
    
    consignor = relationship("Party", foreign_keys=[consignor_id])
    consignee = relationship("Party", foreign_keys=[consignee_id])

class Challan(Base):
    __tablename__ = 'challans'
    id = Column(Integer, primary_key=True, index=True)
    challan_no = Column(String, unique=True, index=True)
    date = Column(Date, default=datetime.date.today)
    origin = Column(String)
    destination = Column(String)
    lorry_no = Column(String)
    vendor_id = Column(Integer, ForeignKey('parties.id'))
    
    driver_name = Column(String)
    license_no = Column(String)
    driver_phone = Column(String)
    chassis_engine_no = Column(String)
    
    reporting_date = Column(Date, nullable=True)
    loading_date = Column(Date, nullable=True)
    delivery_date = Column(Date, nullable=True)
    unloading_date = Column(Date, nullable=True)
    
    weight_charges = Column(Float)
    total_freight = Column(Float)
    advance_paid = Column(Float)
    balance_freight = Column(Float)
    payable_at = Column(String)
    
    vendor_pan = Column(String)
    apply_tds = Column(Boolean, default=True)
    tds_amount = Column(Float, default=0.0)
    tds_rate = Column(Float, default=0.0)
    net_payable = Column(Float)
    penalty_per_day = Column(Float, nullable=True)
    
    vendor = relationship("Party")
    bilties = relationship("Bilty", backref="challan")

class Invoice(Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True, index=True)
    bill_no = Column(String, unique=True, index=True)
    date = Column(Date, default=datetime.date.today)
    party_id = Column(Integer, ForeignKey('parties.id'))
    bill_type = Column(String, default='Freight')
    reverse_charge = Column(Boolean, default=True)
    
    total_amount = Column(Float)
    igst_amount = Column(Float, default=0.0)
    net_amount = Column(Float)
    amount_in_words = Column(String)
    
    bank_name = Column(String)
    account_no = Column(String)
    ifsc_code = Column(String)
    branch = Column(String)
    
    party = relationship("Party")
    bilties = relationship("Bilty", backref="invoice")

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, default=datetime.date.today)
    party_id = Column(Integer, ForeignKey('parties.id'))
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=True)
    amount_received = Column(Float)
    payment_mode = Column(String) 
    utr_no = Column(String, nullable=True)
    
    party = relationship("Party")

class VendorPayment(Base):
    __tablename__ = 'vendor_payments'
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, default=datetime.date.today)
    vendor_id = Column(Integer, ForeignKey('parties.id'))
    challan_id = Column(Integer, ForeignKey('challans.id'), nullable=True)
    amount_paid = Column(Float)
    payment_mode = Column(String)
    utr_no = Column(String, nullable=True)
    
    vendor = relationship("Party")

class Expense(Base):
    __tablename__ = 'expenses'
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, default=datetime.date.today)
    expense_type = Column(String) 
    description = Column(String)
    amount = Column(Float)
    challan_id = Column(Integer, ForeignKey('challans.id'), nullable=True)
