"""
Invoice Processing Workflow using LangGraph.
Multi-node workflow for invoice analysis, policy verification, and approval process.
"""

import logging
from typing import List, Optional, Dict, Any, TypedDict, Annotated
from datetime import datetime, timedelta
import json
import asyncio

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents import ChatMessageContent, TextContent, ImageContent
from semantic_kernel.contents.chat_history import ChatHistory

from common.config.app_config import config


class InvoiceWorkflowState(TypedDict):
    """State definition for the invoice processing workflow."""
    messages: Annotated[list, add_messages]
    user_id: str
    images: Optional[List[bytes]]
    extracted_data: Optional[Dict[str, Any]]
    policy_violations: Optional[List[str]]
    user_confirmation: Optional[bool]
    workflow_stage: str  # "analysis", "verification", "confirmation", "notification", "completed"
    reimbursement_form: Optional[Dict[str, Any]]
    manager_notification_sent: Optional[bool]


class InvoiceProcessingWorkflow:
    """LangGraph-based invoice processing workflow."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._kernel: Optional[Kernel] = None
        self._agent: Optional[ChatCompletionAgent] = None
        self._workflow_graph = None
        self._is_initialized = False
        
    async def initialize(self):
        """Initialize the workflow with Azure OpenAI connection."""
        if self._is_initialized:
            return
            
        try:
            # Create kernel
            self._kernel = Kernel()

            # Add Azure OpenAI Chat Completion service
            chat_service = AzureChatCompletion(
                deployment_name="gpt-4o",  # Use vision-capable model
                endpoint=config.AZURE_OPENAI_ENDPOINT,
                api_key=config.AZURE_OPENAI_API_KEY,
            )
            self._kernel.add_service(chat_service)

            # Create chat completion agent
            self._agent = ChatCompletionAgent(
                kernel=self._kernel,
                name="InvoiceProcessingAgent",
                instructions="""You are an expert invoice processing agent. You can:
1. Analyze invoice images and extract structured data
2. Verify compliance with company policies
3. Generate reimbursement forms
4. Process approvals and notifications

Always provide detailed, accurate responses in the requested format.""",
                description="Invoice processing and reimbursement workflow agent",
            )
            
            # Build the workflow graph
            self._build_workflow_graph()
            self._is_initialized = True
            
            self.logger.info("✅ Invoice processing workflow initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize invoice workflow: {e}")
            raise
    
    def _build_workflow_graph(self):
        """Build the LangGraph workflow."""
        workflow = StateGraph(InvoiceWorkflowState)
        
        # Add nodes
        workflow.add_node("invoice_analysis", self._invoice_analysis_node)
        workflow.add_node("policy_verification", self._policy_verification_node)
        workflow.add_node("user_confirmation", self._user_confirmation_node)
        workflow.add_node("manager_notification", self._manager_notification_node)
        
        # Define edges
        workflow.set_entry_point("invoice_analysis")
        
        workflow.add_edge("invoice_analysis", "policy_verification")
        workflow.add_conditional_edges(
            "policy_verification",
            self._should_ask_for_fixes,
            {
                "ask_for_fixes": "policy_verification",  # Loop back if violations found
                "proceed_to_confirmation": "user_confirmation"
            }
        )
        workflow.add_conditional_edges(
            "user_confirmation", 
            self._check_user_confirmation,
            {
                "confirmed": "manager_notification",
                "wait_for_confirmation": END
            }
        )
        workflow.add_edge("manager_notification", END)
        
        self._workflow_graph = workflow.compile()
    
    async def _invoice_analysis_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 1: Analyze invoice images and extract data."""
        self.logger.info("🔍 Processing invoice analysis node")
        
        try:
            # Create message content for invoice analysis
            analysis_prompt = """
Please analyze the uploaded invoice images and extract the following information:

Required fields:
- Tax ID
- Company Name  
- Vendor Name
- Invoice Date
- Total Amount
- Items/Description
- Invoice Number

Please return the extracted data in JSON format like this:
{
    "tax_id": "...",
    "company_name": "...",
    "vendor_name": "...",
    "invoice_date": "YYYY-MM-DD",
    "total_amount": 0.00,
    "items": ["item1", "item2"],
    "invoice_number": "...",
    "currency": "USD"
}

Also provide a formatted table for display in the chat.
"""
            
            # Create message with images
            message_content = ChatMessageContent(
                role="user",
                items=[TextContent(text=analysis_prompt)]
            )
            
            # Add images if provided
            if state.get("images"):
                for i, image_bytes in enumerate(state["images"]):
                    image_content = ImageContent(
                        data=image_bytes,
                        mime_type="image/jpeg"
                    )
                    message_content.items.append(image_content)
                
                self.logger.info(f"Processing {len(state['images'])} invoice image(s)")
            
            # Get response from agent
            chat_history = ChatHistory()
            chat_history.add_message(message_content)
            
            response_content = ""
            async for response in self._agent.invoke(chat_history):
                if response.content:
                    response_content += str(response.content)
            
            # Try to extract JSON data from response
            extracted_data = self._parse_extracted_data(response_content)
            
            # Update state
            state["extracted_data"] = extracted_data
            state["workflow_stage"] = "analysis_completed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": response_content}
            ]
            
            self.logger.info("✅ Invoice analysis completed successfully")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error in invoice analysis: {e}")
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"❌ Failed to analyze invoice: {str(e)}"}
            ]
            return state
    
    async def _policy_verification_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 2: Verify compliance with company policies."""
        self.logger.info("📋 Processing policy verification node")
        
        try:
            extracted_data = state.get("extracted_data", {})
            violations = []
            
            # Policy 1: Meal expenses must not exceed $200
            total_amount = float(extracted_data.get("total_amount", 0))
            if "meal" in str(extracted_data.get("items", "")).lower() or "restaurant" in str(extracted_data.get("vendor_name", "")).lower():
                if total_amount > 200:
                    violations.append(f"Meal expense ${total_amount} exceeds the $200 limit")
            
            # Policy 2: Invoices must be dated within 30 days
            invoice_date_str = extracted_data.get("invoice_date")
            if invoice_date_str:
                try:
                    invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d")
                    days_old = (datetime.now() - invoice_date).days
                    if days_old > 30:
                        violations.append(f"Invoice is {days_old} days old, exceeds 30-day policy")
                except ValueError:
                    violations.append("Invalid invoice date format")
            
            # Policy 3: Required fields validation
            required_fields = ["tax_id", "company_name", "vendor_name", "total_amount"]
            for field in required_fields:
                if not extracted_data.get(field):
                    violations.append(f"Missing required field: {field}")
            
            # Update state
            state["policy_violations"] = violations
            state["workflow_stage"] = "verification_completed"
            
            if violations:
                violation_message = "❌ **Policy Violations Found:**\n\n"
                for i, violation in enumerate(violations, 1):
                    violation_message += f"{i}. {violation}\n"
                violation_message += "\n🔧 Please fix these issues and resubmit the invoice."
                
                state["messages"] = state.get("messages", []) + [
                    {"role": "assistant", "content": violation_message}
                ]
            else:
                success_message = "✅ **Policy Verification Passed**\n\nAll company policies are satisfied. Ready to proceed with reimbursement form generation."
                state["messages"] = state.get("messages", []) + [
                    {"role": "assistant", "content": success_message}
                ]
            
            self.logger.info(f"Policy verification completed. Violations: {len(violations)}")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error in policy verification: {e}")
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"❌ Failed to verify policies: {str(e)}"}
            ]
            return state
    
    async def _user_confirmation_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 3: Generate reimbursement form and ask for confirmation."""
        self.logger.info("📝 Processing user confirmation node")
        
        try:
            extracted_data = state.get("extracted_data", {})
            
            # Generate reimbursement form
            reimbursement_form = {
                "form_id": f"REI-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "employee_id": state.get("user_id"),
                "submission_date": datetime.now().isoformat(),
                "vendor_name": extracted_data.get("vendor_name"),
                "invoice_date": extracted_data.get("invoice_date"),
                "total_amount": extracted_data.get("total_amount"),
                "description": ", ".join(extracted_data.get("items", [])),
                "status": "pending_confirmation"
            }
            
            # Create confirmation message
            confirmation_message = f"""
📋 **Reimbursement Form Generated**

**Form ID:** {reimbursement_form['form_id']}
**Vendor:** {reimbursement_form['vendor_name']}
**Amount:** ${reimbursement_form['total_amount']}
**Date:** {reimbursement_form['invoice_date']}
**Description:** {reimbursement_form['description']}

🔍 **Please review the information above and confirm:**
✅ Type 'CONFIRM' to submit for manager approval
❌ Type 'CANCEL' to cancel the request
"""
            
            state["reimbursement_form"] = reimbursement_form
            state["workflow_stage"] = "awaiting_confirmation"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": confirmation_message}
            ]
            
            self.logger.info("User confirmation form generated")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error generating confirmation: {e}")
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"❌ Failed to generate reimbursement form: {str(e)}"}
            ]
            return state
    
    async def _manager_notification_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 4: Send notification to manager (mock implementation)."""
        self.logger.info("📧 Processing manager notification node")
        
        try:
            reimbursement_form = state.get("reimbursement_form", {})
            
            # Mock email notification
            notification_details = {
                "to": "manager@company.com",
                "subject": f"New Reimbursement Request - {reimbursement_form.get('form_id')}",
                "body": f"""
New reimbursement request submitted:

Form ID: {reimbursement_form.get('form_id')}
Employee: {state.get('user_id')}
Vendor: {reimbursement_form.get('vendor_name')}
Amount: ${reimbursement_form.get('total_amount')}
Date: {reimbursement_form.get('invoice_date')}

Please review and approve/reject in the system.
""",
                "status": "sent_successfully"
            }
            
            # Simulate saving to database
            await self._save_reimbursement_form(reimbursement_form)
            
            success_message = f"""
🎉 **Reimbursement Request Submitted Successfully!**

**Form ID:** {reimbursement_form.get('form_id')}
**Status:** Submitted for Manager Approval

📧 **Manager Notification:** Sent successfully to manager@company.com
💾 **Database:** Form saved successfully

Your manager will receive an email notification and can approve/reject the request in the system.
"""
            
            state["manager_notification_sent"] = True
            state["workflow_stage"] = "completed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": success_message}
            ]
            
            self.logger.info("Manager notification sent successfully")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error sending manager notification: {e}")
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"❌ Failed to send manager notification: {str(e)}"}
            ]
            return state
    
    def _should_ask_for_fixes(self, state: InvoiceWorkflowState) -> str:
        """Conditional edge: Check if policy violations need to be fixed."""
        violations = state.get("policy_violations", [])
        if violations:
            return "ask_for_fixes"
        else:
            return "proceed_to_confirmation"
    
    def _check_user_confirmation(self, state: InvoiceWorkflowState) -> str:
        """Conditional edge: Check if user has confirmed."""
        confirmation = state.get("user_confirmation")
        if confirmation is True:
            return "confirmed"
        else:
            return "wait_for_confirmation"
    
    def _parse_extracted_data(self, response_content: str) -> Dict[str, Any]:
        """Parse extracted data from agent response."""
        try:
            # Look for JSON in the response
            import re
            json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            else:
                # Fallback: create basic structure
                return {
                    "extracted_from_text": True,
                    "raw_response": response_content
                }
        except Exception as e:
            self.logger.warning(f"Failed to parse JSON from response: {e}")
            return {"parsing_error": str(e), "raw_response": response_content}
    
    async def _save_reimbursement_form(self, form_data: Dict[str, Any]):
        """Mock function to save reimbursement form to database."""
        # This would integrate with your actual database
        self.logger.info(f"💾 Saving reimbursement form {form_data.get('form_id')} to database")
        await asyncio.sleep(0.1)  # Simulate database operation
    
    async def process_invoice_workflow(
        self, 
        user_id: str, 
        user_message: str, 
        images: Optional[List[bytes]] = None
    ) -> InvoiceWorkflowState:
        """Process an invoice through the complete workflow."""
        if not self._is_initialized:
            await self.initialize()
        
        # Initialize state
        initial_state = InvoiceWorkflowState(
            messages=[{"role": "user", "content": user_message}],
            user_id=user_id,
            images=images,
            extracted_data=None,
            policy_violations=None,
            user_confirmation=None,
            workflow_stage="starting",
            reimbursement_form=None,
            manager_notification_sent=None
        )
        
        # Run the workflow
        try:
            result = await self._workflow_graph.ainvoke(initial_state)
            return result
        except Exception as e:
            self.logger.error(f"❌ Workflow execution failed: {e}")
            raise
    
    async def handle_user_response(
        self, 
        state: InvoiceWorkflowState, 
        user_response: str
    ) -> InvoiceWorkflowState:
        """Handle user response during workflow (e.g., confirmation, fixes)."""
        
        # Handle confirmation responses
        if state.get("workflow_stage") == "awaiting_confirmation":
            if user_response.upper() == "CONFIRM":
                state["user_confirmation"] = True
                state["workflow_stage"] = "confirmed"
                # Continue workflow from manager notification
                return await self._workflow_graph.ainvoke(state)
            elif user_response.upper() == "CANCEL":
                state["user_confirmation"] = False
                state["workflow_stage"] = "cancelled"
                state["messages"] = state.get("messages", []) + [
                    {"role": "assistant", "content": "❌ Reimbursement request cancelled by user."}
                ]
                return state
        
        # Handle policy violation fixes
        if state.get("policy_violations"):
            # User provided fixes, restart verification
            state["workflow_stage"] = "fixes_provided" 
            state["messages"] = state.get("messages", []) + [
                {"role": "user", "content": user_response},
                {"role": "assistant", "content": "🔄 Processing your updates..."}
            ]
            # Re-run verification with updated data
            return await self._policy_verification_node(state)
        
        return state