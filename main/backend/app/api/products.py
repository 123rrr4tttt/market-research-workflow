from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import Product


router = APIRouter(prefix="/products", tags=["products"])


class ProductPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    selector_hint: str | None = None
    currency: str | None = None
    enabled: bool = True


@router.get("")
def list_products(enabled: bool | None = None) -> dict:
    with SessionLocal() as session:
        stmt = select(Product).order_by(Product.id.asc())
        if enabled is not None:
            stmt = stmt.where(Product.enabled == enabled)
        rows = session.execute(stmt).scalars().all()
        return {
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "category": row.category,
                    "source_name": row.source_name,
                    "source_uri": row.source_uri,
                    "selector_hint": row.selector_hint,
                    "currency": row.currency,
                    "enabled": row.enabled,
                }
                for row in rows
            ]
        }


@router.post("")
def create_product(payload: ProductPayload) -> dict:
    with SessionLocal() as session:
        row = Product(
            name=payload.name.strip(),
            category=payload.category,
            source_name=payload.source_name,
            source_uri=payload.source_uri,
            selector_hint=payload.selector_hint,
            currency=payload.currency,
            enabled=payload.enabled,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"id": row.id}


@router.put("/{product_id}")
def update_product(product_id: int, payload: ProductPayload) -> dict:
    with SessionLocal() as session:
        row = session.get(Product, product_id)
        if row is None:
            raise HTTPException(status_code=404, detail="product not found")
        row.name = payload.name.strip()
        row.category = payload.category
        row.source_name = payload.source_name
        row.source_uri = payload.source_uri
        row.selector_hint = payload.selector_hint
        row.currency = payload.currency
        row.enabled = payload.enabled
        session.commit()
        return {"updated": product_id}


@router.delete("/{product_id}")
def delete_product(product_id: int) -> dict:
    with SessionLocal() as session:
        row = session.get(Product, product_id)
        if row is None:
            raise HTTPException(status_code=404, detail="product not found")
        session.delete(row)
        session.commit()
        return {"deleted": product_id}
