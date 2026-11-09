"""Owner-bound V7 contact profile: address, phone and WhatsApp. NO bank secrets.
Store with the existing customer PostgreSQL, independently of broker accounts.
"""
from __future__ import annotations
import re
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import text,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Customer,Role
from app.db import get_db
from app.security import get_current_customer
from app.config import approved_release_origin
router=APIRouter(prefix="/api/v1",tags=["customer-profile"])
class ContactProfile(BaseModel):
    phone:str=Field(default="",max_length=50)
    physical_address:str=Field(default="",max_length=400)
    whatsapp_number:str=Field(default="",max_length=50)
    whatsapp_same_as_phone:bool=False
    @model_validator(mode="after")
    def normalize(self):
        self.phone=self.phone.strip()
        self.physical_address=self.physical_address.strip()
        self.whatsapp_number=self.whatsapp_number.strip()
        for name,value in (("phone",self.phone),("physical_address",self.physical_address),("whatsapp_number",self.whatsapp_number)):
            if any(ord(ch)<32 and ch not in "\n\r" for ch in value) or "\x00" in value:
                raise ValueError("Invalid "+name)
        if "\n" in self.phone or "\n" in self.whatsapp_number or "\r" in self.phone or "\r" in self.whatsapp_number:
            raise ValueError("Invalid telephone")
        if len(self.phone)>50 or len(self.whatsapp_number)>50 or len(self.physical_address)>400:
            raise ValueError("Field too long")
        if self.whatsapp_same_as_phone:
            self.whatsapp_number=self.phone
        return self
def require_customer(c:Customer):
    if c.role!=Role.CUSTOMER or not c.is_active:
        raise HTTPException(status_code=403,detail="CUSTOMER_PROFILE_UNAVAILABLE")
    return c
@router.get("/me/profile",response_model=ContactProfile)
async def read_customer_contact_profile(c:Customer=Depends(get_current_customer),db:AsyncSession=Depends(get_db)):
    require_customer(c)
    row=(await db.execute(text("SELECT physical_address,whatsapp_number,whatsapp_same_as_phone FROM public.customer_contact_profiles WHERE customer_id=:id"),{"id":c.id})).mappings().first()
    return ContactProfile(phone=c.phone or "",physical_address=row["physical_address"] if row else "",
       whatsapp_number=row["whatsapp_number"] if row else "",
       whatsapp_same_as_phone=row["whatsapp_same_as_phone"] if row else False)
@router.put("/me/profile",response_model=ContactProfile)
async def update_customer_contact_profile(request:Request,payload:ContactProfile,
      c:Customer=Depends(get_current_customer),db:AsyncSession=Depends(get_db)):
    require_customer(c)
    if not approved_release_origin(request.headers.get("origin","")):
        raise HTTPException(status_code=403,detail="CUSTOMER_PROFILE_ORIGIN_DENIED")
    # Lock the authenticated customer's own row to serialize concurrent updates.
    existing=await db.scalar(select(Customer).where(Customer.id==c.id).with_for_update())
    if existing is None or not existing.is_active:
        raise HTTPException(status_code=403,detail="CUSTOMER_PROFILE_UNAVAILABLE")
    existing.phone=payload.phone or None
    await db.execute(text("""
       INSERT INTO public.customer_contact_profiles(customer_id,physical_address,whatsapp_number,whatsapp_same_as_phone)
       VALUES(:id,:address,:whatsapp,:same)
       ON CONFLICT(customer_id) DO UPDATE SET
          physical_address=EXCLUDED.physical_address,
          whatsapp_number=EXCLUDED.whatsapp_number,
          whatsapp_same_as_phone=EXCLUDED.whatsapp_same_as_phone,
          updated_at=NOW()
    """),{"id":c.id,"address":payload.physical_address,"whatsapp":payload.whatsapp_number,
           "same":payload.whatsapp_same_as_phone})
    await db.commit()
    return payload
