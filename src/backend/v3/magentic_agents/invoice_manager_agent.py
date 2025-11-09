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
from semantic_kernel.contents.chat_history import ChatHistory

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
        description="Query all pending invoices that require this manager's approval. Returns list of invoices with details including invoice_id, user_id, vendor, amount, date, and items."
    )
    async def query_pending_invoices(
        self,
    ) -> Annotated[str, "List of pending invoices requiring approval"]:
        """
        Query all unapproved invoices where current user is the manager.    
        Returns:
            JSON string with list of pending invoices and pagination info
        """
        try:
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

            # Format response
            result = {
                "total_pending": total_invoices,
                "invoices": []
            }
            
            for inv in pending_invoices:
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

            self.logger.info(f"✅ fetched: {total_invoices} invoices successfully")
            return json.dumps(result, indent=2)
            
        except Exception as e:
            self.logger.error(f"❌ Error querying pending invoices: {e}")
            return f"Error querying invoices: {str(e)}"
    
    @kernel_function(
        name="update_invoice_status",
        description="Approve or reject one or multiple invoices by updating their status. Accepts invoice_id as a single ID or comma-separated list of IDs. Requires new_status ('approved' or 'rejected'). rejection_reason is optional."
    )
    async def update_invoice_status(
        self,
        invoice_id: Annotated[str, "Single invoice ID or comma-separated list of invoice IDs to update (e.g., 'INV001' or 'INV001,INV002,INV003')"],
        new_status: Annotated[str, "New status: 'approved' or 'rejected'"],
        rejection_reason: Annotated[Optional[str], "Optional reason for rejection"] = None
    ) -> Annotated[str, "Result of the status update operation"]:
        """
        Update the status of one or multiple invoices to approved or rejected.
        
        Args:
            invoice_id: Single invoice ID or comma-separated list of IDs
            new_status: Either 'approved' or 'rejected'
            rejection_reason: Optional reason for rejection
            
        Returns:
            Confirmation message with results for each invoice
        """
        try:
            # Parse invoice IDs - handle both single ID and comma-separated list
            invoice_ids = [id.strip() for id in invoice_id.split(',') if id.strip()]
            
            if not invoice_ids:
                return "Error: No valid invoice IDs provided."
            
            self.logger.info(f"📝 Manager {self.manager_id} updating {len(invoice_ids)} invoice(s) to {new_status}")
            
            # Validate status
            if new_status.lower() not in ['approved', 'rejected']:
                return f"Error: Invalid status '{new_status}'. Must be 'approved' or 'rejected'."
            
            # Get database instance
            db = await DatabaseFactory.get_database()
            
            # Process each invoice
            results = []
            success_count = 0
            error_count = 0
            
            for inv_id in invoice_ids:
                try:
                    # Get the invoice
                    invoice = await db.get_invoice_by_id(inv_id)
                    
                    if not invoice:
                        results.append(f"❌ Invoice {inv_id}: Not found")
                        error_count += 1
                        continue
                    
                    # Verify this manager has permission
                    if invoice.manager_id != self.manager_id:
                        results.append(f"❌ Invoice {inv_id}: Not authorized (assigned to {invoice.manager_id})")
                        error_count += 1
                        continue
                    
                    # Check if already processed
                    if invoice.status != InvoiceStatus.pending:
                        results.append(f"⚠️ Invoice {inv_id}: Already {invoice.status}")
                        error_count += 1
                        continue
                    
                    # Update status
                    if new_status.lower() == 'approved':
                        invoice.status = InvoiceStatus.approved
                        invoice.approved_date = datetime.now()
                        invoice.rejection_reason = None
                    else:  # rejected
                        invoice.status = InvoiceStatus.rejected
                        invoice.rejection_reason = rejection_reason
                        invoice.approved_date = None
                    
                    # Save to database
                    updated_invoice = await db.update_invoice(invoice)
                    
                    result_line = f"✅ Invoice {inv_id}: {new_status.upper()} | {invoice.vendor_name} | {invoice.currency} {invoice.total_amount}"
                    results.append(result_line)
                    success_count += 1
                    
                except Exception as e:
                    results.append(f"❌ Invoice {inv_id}: Error - {str(e)}")
                    error_count += 1
            
            # Build summary message
            summary = f"\n{'='*60}\n"
            summary += f"📊 BATCH UPDATE SUMMARY\n"
            summary += f"{'='*60}\n"
            summary += f"Total processed: {len(invoice_ids)} | Success: {success_count} | Errors: {error_count}\n"
            summary += f"Status: {new_status.upper()}\n"
            if new_status.lower() == 'rejected' and rejection_reason:
                summary += f"Rejection reason: {rejection_reason}\n"
            summary += f"{'='*60}\n\n"
            
            # Add individual results
            summary += "\n".join(results)
            
            self.logger.info(f"✅ Batch update complete: {success_count}/{len(invoice_ids)} successful")
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ Error updating invoice status: {e}")
            return f"Error updating invoice(s): {str(e)}"


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
        self._chat_history: ChatHistory = ChatHistory()
        self.extracted_invoice: Optional[List[Dict[str, Any]]] = None
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
            2. Update invoice status to approved or rejected with optional rejection reason

            **Processing Steps:**
            1.analyze the user's request and pick one of the following intents:
                - QUERY Intent - Use query_pending_invoices function when user asks to see/show/list/query pending invoices or uses phrases like: "query","show me", "list", "what invoices", "pending invoices", "invoices to review"
                - UPDATE Intent - Use update_invoice_status function when user wants to approve/reject invoice(s) or uses phrases like: "approve invoice", "reject invoice", "update status", "accept", "deny"
            2. Select appropriate tool based on intent
            3. Execute the tool with proper parameters
            4. Format response according to JSON structure below
           
            **Context Management:**
            - For QUERY operations: Fresh invoice data is extracted and stored for reference
            - For UPDATE operations: Previously extracted invoices are used for reference, then cleared after successful update
            - Use previously extracted invoices when user mentions "first invoice", "invoice from vendor X", "the invoice with amount Y", etc.

            **Previously Extracted Invoices (for UPDATE reference only):**
            {json.dumps(self.extracted_invoice, indent=2) if self.extracted_invoice else "No invoice data extracted yet. Please query invoices first."}

            **IMPORTANT: Response format:**
            - You MUST always return a valid JSON object
            - Never return plain text responses
            - Be clear, concise, and professional in the response structure
            - Always include relevant invoice details in the data field
            - Use this JSON structure:
            {{
                "status": "success" or "error",
                "type": "query" or "update",
                "data":  [
                    {{
                        "invoice_id": "invoice_id_1",
                        "user_id": "user_id_value",
                        "vendor_name": "vendor_name_value",
                        "company_name": "company_name_value",
                        "total_amount": 100.0,
                        "currency": "USD",
                        "invoice_date": "YYYY-MM-DD",
                        "submitted_date": "YYYY-MM-DD HH:MM:SS",
                        "items": "items_description",
                        "tax_id": "tax_id_value",
                        "invoice_number": "invoice_number_value",
                        "status": most updated status
                    }}
                ]
            }}


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
        Maintains conversation history for context across multiple requests.
        
        Args:
            user_message: The manager's message/command
            
        Returns:
            Agent's response
        """
        if not self._is_initialized:
            await self.initialize()
        
        try:
            self.logger.info(f"📨 Processing manager request: {user_message[:100]}...")
            
            # Add user message to history
            self._chat_history.add_user_message(user_message)
            
            # Invoke agent with function calling enabled and conversation history
            response_parts = []
            async for response in self._agent.invoke(self._chat_history):
                if response.content:
                    response_parts.append(str(response.content))
            
            full_response = "".join(response_parts)
            
            # Add assistant response to history
            self._chat_history.add_assistant_message(full_response)
            
            # Parse JSON response and extract invoice data if it's a query
            try:
                response_json = json.loads(full_response)
                if (response_json.get("type") == "query" and 
                    response_json.get("status") == "success" and 
                    "data" in response_json):
                    
                    # Store the invoice data for future reference
                    self.extracted_invoice = response_json["data"]
                    self.logger.info(f"📋 Extracted {len(self.extracted_invoice)} invoice(s) from query response")
                    
                elif (response_json.get("type") == "update" and 
                      response_json.get("status") == "success"):
                    
                    # Clear extracted invoice data after successful update
                    self.extracted_invoice = None
                    self.logger.info(f"🧹 Cleared extracted invoice data after successful update")
                    
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self.logger.warning(f"⚠️ Could not parse response as JSON or extract invoice data: {e}")
            
            self.logger.info(f"✅ Manager request processed successfully. History length: {len(self._chat_history.messages)}")
            
            return full_response
            
        except Exception as e:
            self.logger.error(f"❌ Error processing manager request: {e}")
            return f"Error processing request: {str(e)}"
    
    def get_chat_history(self) -> ChatHistory:
        """Get the current chat history."""
        return self._chat_history
    
    def clear_chat_history(self):
        """Clear the conversation history."""
        self._chat_history.clear()
        self.logger.info(f"🧹 Chat history cleared for manager {self.manager_id}")
    
    async def close(self):
        """Clean up resources."""
        self._kernel = None
        self._agent = None
        self._plugin = None
        self._chat_history.clear()
        self._is_initialized = False
        self.logger.info(f"🧹 InvoiceManagerAgent closed for manager {self.manager_id}")
    
    @property
    def is_initialized(self) -> bool:
        """Check if agent is initialized."""
        return self._is_initialized
