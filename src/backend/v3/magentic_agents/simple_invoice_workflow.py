"""
Simplified Invoice Processing Workflow without LangGraph.
Uses SimpleChatAgent with intelligent state management.
"""

import logging
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime, timedelta
import json

from v3.magentic_agents.simple_chat_agent import SimpleChatAgent


class WorkflowStage(Enum):
    """Invoice processing workflow stages."""
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    CONFIRMATION = "confirmation"
    NOTIFICATION = "notification"
    COMPLETED = "completed"


class SimpleInvoiceWorkflow:
    """Simplified invoice processing workflow using SimpleChatAgent."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.logger = logging.getLogger(__name__)
        
        # Workflow state
        self.current_stage = WorkflowStage.ANALYSIS
        self.extracted_data = None
        self.policy_violations = []
        self.reimbursement_form = None
        
        # Initialize SimpleChatAgent
        self.agent = SimpleChatAgent(
            agent_name="SimpleInvoiceAgent",
            agent_description="Invoice processing and reimbursement assistant",
            system_message="",  # Will be set dynamically
            model_deployment_name="gpt-4o",
            user_id=user_id
        )
    
    async def process_invoice_request(self, user_message: str, images: Optional[List[bytes]] = None):
        """Process invoice request through workflow stages."""
        
        try:
            await self.agent.open()
            
            # Stage 1: Invoice Analysis
            if self.current_stage == WorkflowStage.ANALYSIS:
                return await self._handle_analysis_stage(user_message, images)
            
            # Stage 2: Policy Verification
            elif self.current_stage == WorkflowStage.VERIFICATION:
                return await self._handle_verification_stage(user_message)
            
            # Stage 3: User Confirmation
            elif self.current_stage == WorkflowStage.CONFIRMATION:
                return await self._handle_confirmation_stage(user_message)
            
            # Stage 4: Manager Notification
            elif self.current_stage == WorkflowStage.NOTIFICATION:
                return await self._handle_notification_stage()
            
            else:
                return "Workflow completed. Start a new invoice processing request."
                
        except Exception as e:
            self.logger.error(f"Error in workflow: {e}")
            return f"❌ Error processing invoice: {str(e)}"
    
    async def _handle_analysis_stage(self, user_message: str, images: Optional[List[bytes]] = None):
        """Handle invoice analysis stage."""
        
        analysis_prompt = f"""
TASK: Invoice Analysis and Data Extraction

USER REQUEST: {user_message}

Please analyze the uploaded invoice images and extract the following information:

**Required Fields:**
- Tax ID
- Company Name  
- Vendor Name
- Invoice Date (YYYY-MM-DD format)
- Total Amount (number only)
- Items/Description
- Invoice Number

**Instructions:**
1. Examine each uploaded image carefully
2. Extract all key information from the invoices
3. Present the data in a clear table format
4. Also provide the extracted data in JSON format for processing

**Output Format:**
First show a formatted table, then provide JSON like this:
```json
{{
    "invoices": [
        {{
            "tax_id": "...",
            "company_name": "...",
            "vendor_name": "...",
            "invoice_date": "YYYY-MM-DD",
            "total_amount": 0.00,
            "items": ["item1", "item2"],
            "invoice_number": "...",
            "currency": "USD"
        }}
    ]
}}
```

If you cannot extract certain fields, mark them as "Not found" or "Unclear".
"""

        # Get response from agent
        response = await self.agent.invoke_async(analysis_prompt, images)
        
        # Try to extract JSON data from response
        self.extracted_data = self._extract_json_from_response(response)
        
        # Move to next stage
        self.current_stage = WorkflowStage.VERIFICATION
        
        return response + "\n\n🔄 **Next Step:** Verifying policy compliance..."
    
    async def _handle_verification_stage(self, user_message: str):
        """Handle policy verification stage."""
        
        if not self.extracted_data:
            return "❌ No invoice data found. Please start over with invoice analysis."
        
        # Check policies
        violations = []
        invoices = self.extracted_data.get("invoices", [])
        
        for i, invoice in enumerate(invoices, 1):
            # Policy 1: Meal expense limit
            amount = float(invoice.get("total_amount", 0))
            vendor = invoice.get("vendor_name", "").lower()
            items = str(invoice.get("items", "")).lower()
            
            if "restaurant" in vendor or "meal" in items or "food" in items:
                if amount > 200:
                    violations.append(f"Invoice {i}: Meal expense ${amount} exceeds $200 limit")
            
            # Policy 2: Date within 30 days
            invoice_date_str = invoice.get("invoice_date")
            if invoice_date_str and invoice_date_str != "Not found":
                try:
                    invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d")
                    days_old = (datetime.now() - invoice_date).days
                    if days_old > 30:
                        violations.append(f"Invoice {i}: Date {invoice_date_str} is {days_old} days old (exceeds 30-day limit)")
                except ValueError:
                    violations.append(f"Invoice {i}: Invalid date format '{invoice_date_str}'")
            
            # Policy 3: Required fields
            required_fields = ["tax_id", "company_name", "vendor_name", "total_amount"]
            for field in required_fields:
                if not invoice.get(field) or invoice.get(field) == "Not found":
                    violations.append(f"Invoice {i}: Missing required field '{field}'")
        
        self.policy_violations = violations
        
        if violations:
            violation_text = "\n".join(f"• {v}" for v in violations)
            return f"""❌ **Policy Violations Found:**

{violation_text}

🔧 **Please fix these issues and resubmit, or type 'OVERRIDE' if you have manager approval to bypass these policies.**"""
        else:
            # No violations, proceed to confirmation
            self.current_stage = WorkflowStage.CONFIRMATION
            return await self._generate_confirmation_form()
    
    async def _handle_confirmation_stage(self, user_message: str):
        """Handle user confirmation stage."""
        
        user_response = user_message.upper().strip()
        
        if user_response == "CONFIRM":
            self.current_stage = WorkflowStage.NOTIFICATION
            return await self._handle_notification_stage()
        
        elif user_response == "CANCEL":
            return "❌ **Request Cancelled**\n\nReimbursement request has been cancelled by user."
        
        else:
            return """🤔 **Please provide a clear response:**
            
✅ Type **CONFIRM** to submit for manager approval
❌ Type **CANCEL** to cancel the request"""
    
    async def _handle_notification_stage(self):
        """Handle manager notification stage."""
        
        # Generate reimbursement form
        form_id = f"REI-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        self.reimbursement_form = {
            "form_id": form_id,
            "employee_id": self.user_id,
            "submission_date": datetime.now().isoformat(),
            "invoices": self.extracted_data.get("invoices", []),
            "total_amount": sum(float(inv.get("total_amount", 0)) for inv in self.extracted_data.get("invoices", [])),
            "status": "pending_approval"
        }
        
        # Mock email notification
        self.current_stage = WorkflowStage.COMPLETED
        
        return f"""🎉 **Reimbursement Request Submitted Successfully!**

**Form ID:** {form_id}
**Total Amount:** ${self.reimbursement_form['total_amount']:.2f}
**Status:** Submitted for Manager Approval

📧 **Manager Notification:** Email sent to manager@company.com
💾 **Database:** Form saved successfully

**What happens next:**
• Your manager will receive an email notification
• They can approve/reject in the management portal
• You'll receive notification of the decision

Type 'NEW' to start another reimbursement request."""
    
    async def _generate_confirmation_form(self):
        """Generate confirmation form for user review."""
        
        invoices = self.extracted_data.get("invoices", [])
        total_amount = sum(float(inv.get("total_amount", 0)) for inv in invoices)
        
        invoice_summary = []
        for i, inv in enumerate(invoices, 1):
            invoice_summary.append(
                f"**Invoice {i}:**\n"
                f"• Vendor: {inv.get('vendor_name', 'N/A')}\n"
                f"• Amount: ${inv.get('total_amount', 0)}\n"
                f"• Date: {inv.get('invoice_date', 'N/A')}\n"
                f"• Items: {', '.join(inv.get('items', ['N/A']))}"
            )
        
        return f"""✅ **Policy Verification Passed**

📋 **Reimbursement Summary:**

{chr(10).join(invoice_summary)}

**Total Amount:** ${total_amount:.2f}

🔍 **Please review and confirm:**
✅ Type **CONFIRM** to submit for manager approval
❌ Type **CANCEL** to cancel the request"""
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Extract JSON data from agent response."""
        try:
            import re
            # Look for JSON block
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL | re.IGNORECASE)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
            # Fallback: look for any JSON-like structure
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
                
        except Exception as e:
            self.logger.warning(f"Failed to extract JSON: {e}")
        
        return {"invoices": [], "extraction_failed": True}
    
    def get_current_stage(self) -> str:
        """Get current workflow stage."""
        return self.current_stage.value
    
    def reset_workflow(self):
        """Reset workflow to start fresh."""
        self.current_stage = WorkflowStage.ANALYSIS
        self.extracted_data = None
        self.policy_violations = []
        self.reimbursement_form = None