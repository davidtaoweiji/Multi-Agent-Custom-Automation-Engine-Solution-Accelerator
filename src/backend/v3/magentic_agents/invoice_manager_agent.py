"""
Invoice Manager Agent - Handles invoice approval/rejection workflow.
Manager can query pending invoices and approve/reject them.
"""

import logging
from typing import List, Optional, Dict, Any, Annotated
from datetime import datetime

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import kernel_function

from common.config.app_config import config
from common.database.database_factory import DatabaseFactory
from v3.magentic_agents.models.data_models import Invoice, InvoiceStatus
import json

class InvoiceManagerPlugin:
    """Plugin with invoice management functions for managers."""
    
    def __init__(self, manager_id: str):
        self.manager_id = manager_id
        self.logger = logging.getLogger(__name__)
    
    @kernel_function(
        name="query_pending_invoices",
        description="Query all pending invoices that require this manager's approval. Returns list of invoices with details including invoice_id, user_id, vendor, amount, date, and items. Supports pagination with page (default 1) and page_size (default 10) parameters."
    )
    async def query_pending_invoices(
        self,
        page: Annotated[int, "Page number to retrieve (starts from 1)"] = 1,
        page_size: Annotated[int, "Number of invoices per page"] = 10
    ) -> Annotated[str, "List of pending invoices requiring approval"]:
        """
        Query all unapproved invoices where current user is the manager.
        
        Args:
            page: Page number (default: 1, starts from 1)
            page_size: Number of invoices per page (default: 10)
        
        Returns:
            JSON string with list of pending invoices and pagination info
        """
        try:
            self.logger.info(f"🔍 Manager {self.manager_id} querying pending invoices (page {page}, size {page_size})")
            # Validate pagination parameters
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 10
            if page_size > 100:  # Maximum page size limit
                page_size = 100
            
            # Get database instance
            db = await DatabaseFactory.get_database()
            
            # Query invoices by manager_id
            invoices = await db.get_invoices_by_manager(self.manager_id)
            
            # Filter for pending status only
            pending_invoices = [
                inv for inv in invoices 
                if inv.status == InvoiceStatus.pending
            ]

            print(f"Found {len(pending_invoices)} pending invoices for manager '{self.manager_id}': {pending_invoices}")
            # Calculate pagination
            total_invoices = len(pending_invoices)
            total_pages = (total_invoices + page_size - 1) // page_size  # Ceiling division
            
            # Get invoices for current page
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_invoices = pending_invoices[start_idx:end_idx]
            
            if not page_invoices and total_invoices > 0:
                return f"Page {page} is out of range. Total pages: {total_pages}"
            
            if not pending_invoices:
                return "No pending invoices found requiring your approval."
            
            # Format response
            result = {
                "total_pending": total_invoices,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "showing": len(page_invoices),
                "invoices": []
            }
            
            for inv in page_invoices:
                result["invoices"].append({
                    "invoice_id": inv.invoice_id,
                    "user_id": inv.user_id,
                    "vendor_name": inv.vendor_name,
                    "company_name": inv.company_name,
                    "total_amount": inv.total_amount,
                    "currency": inv.currency,
                    "invoice_date": str(inv.invoice_date) if inv.invoice_date else None,
                    "submitted_date": str(inv.submitted_date) if inv.submitted_date else None,
                    "items": inv.items,
                    "tax_id": inv.tax_id,
                    "invoice_number": inv.invoice_number,
                    "status": inv.status
                })
            

            self.logger.info(f"✅ Found {total_invoices} pending invoice(s), showing page {page} ({len(page_invoices)} invoices)")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            self.logger.error(f"❌ Error querying pending invoices: {e}")
            return f"Error querying invoices: {str(e)}"
    
    @kernel_function(
        name="update_invoice_status",
        description="Approve or reject an invoice by updating its status. Requires invoice_id and new_status ('approved' or 'rejected'). Optionally provide rejection_reason if rejecting."
    )
    async def update_invoice_status(
        self,
        invoice_id: Annotated[str, "The ID of the invoice to update"],
        new_status: Annotated[str, "New status: 'approved' or 'rejected'"],
        rejection_reason: Annotated[Optional[str], "Reason for rejection (required if rejecting)"] = None
    ) -> Annotated[str, "Result of the status update operation"]:
        """
        Update the status of an invoice to approved or rejected.
        
        Args:
            invoice_id: The invoice ID to update
            new_status: Either 'approved' or 'rejected'
            rejection_reason: Required if status is rejected
            
        Returns:
            Confirmation message
        """
        try:
            self.logger.info(f"📝 Manager {self.manager_id} updating invoice {invoice_id} to {new_status}")
            
            # Validate status
            if new_status.lower() not in ['approved', 'rejected']:
                return f"Error: Invalid status '{new_status}'. Must be 'approved' or 'rejected'."
            
            # Get database instance
            db = await DatabaseFactory.get_database()
            
            # Get the invoice
            invoice = await db.get_invoice_by_id(invoice_id)
            
            if not invoice:
                return f"Error: Invoice {invoice_id} not found."
            
            # Verify this manager has permission (invoice.manager_id matches)
            if invoice.manager_id != self.manager_id:
                return f"Error: You are not authorized to approve/reject this invoice. Assigned manager: {invoice.manager_id}"
            
            # Check if already processed
            if invoice.status != InvoiceStatus.pending:
                return f"Error: Invoice {invoice_id} has already been {invoice.status}. Cannot update."
            
            # Update status
            if new_status.lower() == 'approved':
                invoice.status = InvoiceStatus.approved
                invoice.approved_date = datetime.now()
                invoice.rejection_reason = None
            else:  # rejected
                if not rejection_reason:
                    return "Error: rejection_reason is required when rejecting an invoice."
                invoice.status = InvoiceStatus.rejected
                invoice.rejection_reason = rejection_reason
                invoice.approved_date = None
            
            # Save to database
            updated_invoice = await db.update_invoice(invoice)
            
            result_msg = f"✅ Invoice {invoice_id} has been {new_status}.\n"
            result_msg += f"   Submitted by: {invoice.user_id}\n"
            result_msg += f"   Vendor: {invoice.vendor_name}\n"
            result_msg += f"   Amount: {invoice.currency} {invoice.total_amount}\n"
            
            if new_status.lower() == 'rejected':
                result_msg += f"   Rejection reason: {rejection_reason}\n"
            
            self.logger.info(f"✅ Successfully {new_status} invoice {invoice_id}")
            return result_msg
            
        except Exception as e:
            self.logger.error(f"❌ Error updating invoice status: {e}")
            return f"Error updating invoice: {str(e)}"


class InvoiceManagerAgent:
    """
    Invoice Manager Agent - allows managers to query and approve/reject pending invoices.
    Uses function calling to interact with the invoice database.
    """
    
    def __init__(self, manager_id: str, model_deployment_name: str = "gpt-4o"):
        self.manager_id = manager_id
        self.model_deployment_name = model_deployment_name
        self.logger = logging.getLogger(__name__)
        
        # Internal state
        self._kernel: Optional[Kernel] = None
        self._agent: Optional[ChatCompletionAgent] = None
        self._plugin: Optional[InvoiceManagerPlugin] = None
        self._is_initialized = False
    
    async def initialize(self):
        """Initialize the agent with Azure OpenAI and function tools."""
        if self._is_initialized:
            return
        
        try:
            # Create kernel
            self._kernel = Kernel()
            
            # Add Azure OpenAI service
            chat_service = AzureChatCompletion(
                deployment_name=self.model_deployment_name,
                endpoint=config.AZURE_OPENAI_ENDPOINT,
                api_key=config.AZURE_OPENAI_API_KEY,
            )
            self._kernel.add_service(chat_service)
            
            # Create and add plugin
            self._plugin = InvoiceManagerPlugin(manager_id=self.manager_id)
            self._kernel.add_plugin(
                plugin=self._plugin,
                plugin_name="InvoiceManager"
            )
            
            # Create agent with system instructions
            system_message = f"""You are an intelligent Invoice Management Assistant for managers.

Your role is to help Manager ID: {self.manager_id} review and process invoice reimbursement requests.

**Your capabilities:**
1. Query pending invoices that require this manager's approval
2. Approve invoices that meet company policies
3. Reject invoices with appropriate reasons

**Guidelines:**
- Always verify invoice details before approving
- Provide clear explanations for rejections
- Be professional and helpful
- When user asks to see pending invoices, use the query_pending_invoices function
- When user wants to approve/reject an invoice, use the update_invoice_status function
- Always confirm the action after updating an invoice status

**IMPORTANT: Response format:**
- You MUST always return a valid JSON object
- Never return plain text responses
- Use this JSON structure:
  {{
    "status": "success" or "error",
    "message": "Brief description of the result",
    "data": {{ ... relevant data ... }}
  }}
- For queries, include the invoice list in the "data" field
- For updates, include confirmation details in the "data" field
- Be clear, concise, and professional in the "message" field
"""
            
            self._agent = ChatCompletionAgent(
                kernel=self._kernel,
                name="InvoiceManagerAgent",
                instructions=system_message,
                description="Invoice management agent for approving/rejecting reimbursement requests"
            )
            
            self._is_initialized = True
            self.logger.info(f"✅ InvoiceManagerAgent initialized for manager {self.manager_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize InvoiceManagerAgent: {e}")
            raise
    
    async def process_request(self, user_message: str) -> str:
        """
        Process a manager's request (query or approve/reject invoices).
        
        Args:
            user_message: The manager's message/command
            
        Returns:
            Agent's response
        """
        if not self._is_initialized:
            await self.initialize()
        
        try:
            self.logger.info(f"📨 Processing manager request: {user_message[:100]}...")
            
            # Invoke agent with function calling enabled
            response_parts = []
            async for response in self._agent.invoke(user_message):
                if response.content:
                    response_parts.append(str(response.content))
            
            full_response = "".join(response_parts)
            self.logger.info("✅ Manager request processed successfully")
            
            return full_response
            
        except Exception as e:
            self.logger.error(f"❌ Error processing manager request: {e}")
            return f"Error processing request: {str(e)}"
    
    async def close(self):
        """Clean up resources."""
        self._kernel = None
        self._agent = None
        self._plugin = None
        self._is_initialized = False
        self.logger.info(f"🧹 InvoiceManagerAgent closed for manager {self.manager_id}")
    
    @property
    def is_initialized(self) -> bool:
        """Check if agent is initialized."""
        return self._is_initialized
