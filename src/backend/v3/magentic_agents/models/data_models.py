
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from semantic_kernel.kernel_pydantic import Field, KernelBaseModel

class DataType(str, Enum):
    """Enumeration of possible data types for documents in the database."""
    invoice = "invoice"  # 🔄 Added for invoice reimbursement forms
    
class BaseDataModel(KernelBaseModel):
    """Base data model with common fields."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

class InvoiceStatus(str, Enum):
    """Enumeration of possible statuses for an invoice reimbursement."""
    
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"

class Invoice(BaseDataModel):
    """Invoice reimbursement form model for Cosmos DB storage."""
    
    data_type: Literal[DataType.invoice] = Field(DataType.invoice, Literal=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invoice_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    manager_id: Optional[str] = None
    
    # Invoice details
    tax_id: str
    company_name: str
    vendor_name: str
    invoice_date: str  # YYYY-MM-DD format
    total_amount: float
    items: str  # Description of items
    invoice_number: Optional[str] = None
    currency: str = "USD"
    
    # Workflow metadata
    status: InvoiceStatus = InvoiceStatus.pending
    submitted_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    # Additional metadata
    team_id: Optional[str] = None
    workflow_session_id: Optional[str] = None
    notes: Optional[str] = None