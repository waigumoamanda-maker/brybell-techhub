# order_service/main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import uuid

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/brybell_orders")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    total_amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    payment_status = Column(String(50), default="pending")
    shipping_address = Column(Text)
    phone_number = Column(String(20))
    tracking_number = Column(String(100), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255))
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    order = relationship("Order", back_populates="items")

Base.metadata.create_all(bind=engine)

# Pydantic Schemas
class OrderItemCreate(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    price: float

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    price: float
    
    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    user_id: int
    items: List[OrderItemCreate]
    shipping_address: str
    phone_number: str

class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    payment_status: str
    shipping_address: str
    phone_number: str
    tracking_number: str
    items: List[OrderItemResponse]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: str

# FastAPI App
app = FastAPI(title="Order Service", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper Functions
def generate_tracking_number():
    return f"BRY{uuid.uuid4().hex[:12].upper()}"

def calculate_total(items: List[OrderItemCreate]) -> float:
    return sum(item.price * item.quantity for item in items)

# API Endpoints
@app.get("/")
def root():
    return {"service": "Order Service", "status": "running"}

@app.post("/api/orders", response_model=OrderResponse, status_code=201)
def create_order(order_data: OrderCreate, db: Session = Depends(get_db)):
    # Calculate total
    total_amount = calculate_total(order_data.items)
    
    # Create order
    db_order = Order(
        user_id=order_data.user_id,
        total_amount=total_amount,
        shipping_address=order_data.shipping_address,
        phone_number=order_data.phone_number,
        tracking_number=generate_tracking_number(),
        status="pending",
        payment_status="pending"
    )
    
    db.add(db_order)
    db.flush()
    
    # Create order items
    for item in order_data.items:
        db_item = OrderItem(
            order_id=db_order.id,
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            price=item.price
        )
        db.add(db_item)
    
    db.commit()
    db.refresh(db_order)
    
    return db_order

@app.get("/api/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/orders/user/{user_id}", response_model=List[OrderResponse])
def get_user_orders(
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    orders = db.query(Order).filter(
        Order.user_id == user_id
    ).order_by(Order.created_at.desc()).offset(skip).limit(limit).all()
    return orders

@app.get("/api/orders", response_model=List[OrderResponse])
def get_all_orders(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Order)
    
    if status:
        query = query.filter(Order.status == status)
    
    orders = query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()
    return orders

@app.put("/api/orders/{order_id}/status", response_model=OrderResponse)
def update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.status = status_update.status
    order.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(order)
    return order

@app.put("/api/orders/{order_id}/payment-status")
def update_payment_status(
    order_id: int,
    payment_status: str,
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.payment_status = payment_status
    
    # Auto-update order status if payment is successful
    if payment_status == "paid" and order.status == "pending":
        order.status = "processing"
    
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    
    return {"message": "Payment status updated", "order": order.id}

@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status not in ["pending", "processing"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel order in current status"
        )
    
    order.status = "cancelled"
    order.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Order cancelled successfully"}

@app.get("/api/orders/tracking/{tracking_number}", response_model=OrderResponse)
def track_order(tracking_number: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.tracking_number == tracking_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/orders/stats/summary")
def get_order_stats(db: Session = Depends(get_db)):
    total_orders = db.query(Order).count()
    pending_orders = db.query(Order).filter(Order.status == "pending").count()
    processing_orders = db.query(Order).filter(Order.status == "processing").count()
    completed_orders = db.query(Order).filter(Order.status == "completed").count()
    
    total_revenue = db.query(Order).filter(
        Order.payment_status == "paid"
    ).with_entities(Order.total_amount).all()
    
    revenue_sum = sum(amount[0] for amount in total_revenue) if total_revenue else 0
    
    return {
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "processing_orders": processing_orders,
        "completed_orders": completed_orders,
        "total_revenue": revenue_sum
    }
