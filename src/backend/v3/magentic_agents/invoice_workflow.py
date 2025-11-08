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
from langchain_core.messages import HumanMessage

from common.config.app_config import config


class InvoiceWorkflowState(TypedDict):
    """State definition for the invoice processing workflow."""
    messages: Annotated[list, add_messages]
    user_id: str
    images: Optional[List[bytes]]
    extracted_data: Optional[List[Dict[str, Any]]]  # 🔄 Changed to List to support multiple invoices
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
                instructions="""You are an expert invoice processing agent specializing in strict JSON responses.

                CRITICAL REQUIREMENT: ALL responses must be ONLY valid JSON format, no additional text, formatting, or explanations.

                Your capabilities:
                1. Analyze invoice images and extract structured data  
                2. Verify compliance with company policies
                3. Generate reimbursement forms
                4. Process approvals and notifications

                For invoice analysis, return:
                {
                    "message": "Brief status message",
                    "extracted_data": [{"invoice_1": {...}}, {"invoice_2": {...}}],
                    "success": true/false
                }

                For data merging, return only the merged data array:
                [
                    {
                        "tax_id": "...",
                        "vendor_name": "...",
                        ...
                    }
                ]

                Never include markdown, tables, explanations, or any text outside the JSON structure.""",
                                description="Strict JSON-only invoice processing agent",
            )
            
            # Build the workflow graph
            self._build_workflow_graph()
            self._is_initialized = True
            
            self.logger.info("✅ Invoice processing workflow initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize invoice workflow: {e}")
            raise
    
    def _build_workflow_graph(self):
        """Build the LangGraph workflow with proper interrupt + resume semantics.

        流程說明:
        1. invoice_analysis → policy_verification
        2. 若有違規 → wait_for_fixes (interrupt_after) → (resume) → invoice_analysis 重新提取+驗證
        3. 若無違規 → user_confirmation (interrupt_after 等待用戶確認) → (resume) → manager_notification → END
        """
        workflow = StateGraph(InvoiceWorkflowState)

        # Add nodes
        workflow.add_node("invoice_analysis", self._invoice_analysis_node)
        workflow.add_node("policy_verification", self._policy_verification_node)
        workflow.add_node("wait_for_fixes", self._wait_for_fixes_node)
        workflow.add_node("user_confirmation", self._user_confirmation_node)
        workflow.add_node("manager_notification", self._manager_notification_node)

        # Entry
        workflow.set_entry_point("invoice_analysis")

        # Normal forward edge
        workflow.add_edge("invoice_analysis", "policy_verification")

        # Branch after verification
        workflow.add_conditional_edges(
            "policy_verification",
            self._should_ask_for_fixes,
            {
                "ask_for_fixes": "wait_for_fixes",
                "proceed_to_confirmation": "user_confirmation"
            }
        )

        # After user provides fixes, loop back to re-extract from full message history
        workflow.add_edge("wait_for_fixes", "invoice_analysis")

        # Confirmation branch
        workflow.add_conditional_edges(
            "user_confirmation",
            self._check_user_confirmation,
            {
                "confirmed": "manager_notification",
                "wait_for_confirmation": END  # interrupt here waiting for explicit confirm/cancel
            }
        )
        workflow.add_edge("manager_notification", END)

        # Interrupt AFTER nodes that require human input 
        self._workflow_graph = workflow.compile(interrupt_after=["wait_for_fixes", "user_confirmation"])
    
    async def _invoice_analysis_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 1: Analyze invoice data from text input and/or images.
        
        Uses full message history as context to handle corrections from user.
        """
        self.logger.info("🔍 Processing invoice analysis node")
        
        try:
            # Build conversation context from ALL messages (including corrections)
            existing_invoices = state.get("extracted_data", [])
            all_messages = state["messages"]
            latest_message = ""
            for msg in reversed(all_messages):
                if type(msg) == HumanMessage:
                    latest_message = msg.content
                    break

            full_context = f"Existing Invoice Data: {json.dumps(existing_invoices)}\n\nLatest User Message: {latest_message}"
            # Check if we have images
            has_images = state.get("images") and len(state["images"]) > 0

            # Context-aware analysis prompt
            analysis_prompt = f"""
            You are an expert invoice processing agent. You must extract structured data from the conversation history.
            
            IMPORTANT: The user may provide MULTIPLE invoices/receipts in a single request. Extract ALL of them as a list.

            CONVERSATION HISTORY (includes original request and any corrections):
            {full_context}

            Images provided: {"Yes - " + str(len(state["images"])) + " image(s)" if has_images else "No"}

            TASK: Extract ALL invoice data from the conversation. If user provided corrections, use the corrected values.
            If there are multiple invoices/images, return a list with all of them.

            FOR TEXT EXTRACTION, look for these patterns:
            - Tax ID numbers (e.g., "Tax ID 123" → extract "123")
            - Company names (e.g., "Company Name microsoft" → extract "microsoft")
            - Vendor names (e.g., "Vendor Name KFC" → extract "KFC") 
            - Amounts (e.g., "Amount 200" → extract 200.0)
            - Dates (e.g., "Date 2023-10" → convert to "2023-10-01")
            - Items/descriptions (e.g., "Items meal" → extract "meal")

            {"FOR IMAGE ANALYSIS: Analyze ALL uploaded images for invoice details. Each image may be a separate invoice." if has_images else ""}

            CRITICAL: Your response must be ONLY valid JSON in this exact format:
            {{
                "message": "Successfully extracted N invoice(s)",
                "extracted_data": [
                    {{
                        "tax_id": "extracted_tax_id_or_empty_string",
                        "company_name": "extracted_company_name", 
                        "vendor_name": "extracted_vendor_name",
                        "invoice_date": "YYYY-MM-DD",
                        "total_amount": 0.00,
                        "items": "extracted_items_description",
                        "invoice_number": "extracted_invoice_number_or_empty",
                        "currency": "USD"
                    }}
                ],
                "success": true
            }}

            IMPORTANT RULES:
            1. Always return extracted_data as an ARRAY, even for single invoice
            2. User corrections override previous values for the corresponding invoice
            3. Keep values from earlier messages if not corrected
            4. Return ONLY the JSON object, no additional text
            5. If a field wasn't mentioned at all, use NULL for that field
            6. Each image typically represents a separate invoice - extract them all
            """
            # Create message with unified prompt
            message_content = ChatMessageContent(
                role="user",
                items=[TextContent(text=analysis_prompt)]
            )
            
            # Add images if provided
            if has_images:
                for i, image_bytes in enumerate(state["images"]):
                    image_content = ImageContent(
                        data=image_bytes,
                        mime_type="image/jpeg"
                    )
                    message_content.items.append(image_content)
                
                self.logger.info(f"Processing conversation context + {len(state['images'])} image(s)")
            else:
                self.logger.info(f"Processing invoice from conversation history messages)")

            
            response_content = ""
            async for response in self._agent.invoke(message_content):
                if response.content:
                    response_content += str(response.content)
            # Parse JSON response strictly
            try:
                json_response = json.loads(response_content.strip())
                
                if json_response.get("success"):
                    extracted_data = json_response.get("extracted_data", [])
                    # Ensure it's always a list
                    if not isinstance(extracted_data, list):
                        extracted_data = [extracted_data] if extracted_data else []
                    status_message = json_response.get("message", f"Invoice analysis completed - extracted {len(extracted_data)} invoice(s)")
                else:
                    extracted_data = [{"parsing_error": json_response.get("error", "Unknown error")}]
                    status_message = json_response.get("message", "Invoice analysis failed")
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON response: {e}")
                extracted_data = [{"parsing_error": f"Invalid JSON response: {str(e)}"}]
                status_message = "Failed to parse invoice data - invalid response format"
            
            # Update state
            state["extracted_data"] = extracted_data
            state["workflow_stage"] = "analysis_completed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": status_message}
            ]
            self.logger.info("✅ Invoice analysis completed successfully")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error in invoice analysis: {e}")
            state["extracted_data"] = [{"parsing_error": str(e)}]
            state["workflow_stage"] = "analysis_failed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"Failed to analyze invoice: {str(e)}"}
            ]
            return state
    
    async def _policy_verification_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 2: Verify compliance with company policies for all invoices."""
        self.logger.info("📋 Processing policy verification node")
        try:
            extracted_data_list = state.get("extracted_data", [])
            all_violations = []
            
            # Validate each invoice
            for idx, extracted_data in enumerate(extracted_data_list):
                invoice_prefix = f"Invoice #{idx + 1}: "
                
                # Skip error entries
                if extracted_data.get("parsing_error"):
                    all_violations.append(f"{invoice_prefix}Failed to parse invoice data")
                    continue
                
                # Policy 1: Meal expenses must not exceed $200
                total_amount = float(extracted_data.get("total_amount", 0))
                if "meal" in str(extracted_data.get("items", "")).lower() or "restaurant" in str(extracted_data.get("vendor_name", "")).lower():
                    if total_amount > 200:
                        all_violations.append(f"{invoice_prefix}Meal expense ${total_amount} exceeds the $200 limit")
                
                # Policy 2: Invoices must be dated within 30 days
                invoice_date_str = extracted_data.get("invoice_date")
                if invoice_date_str:
                    try:
                        invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d")
                        days_old = (datetime.now() - invoice_date).days
                        if days_old > 30:
                            all_violations.append(f"{invoice_prefix}Invoice is {days_old} days old, exceeds 30-day policy")
                    except ValueError:
                        all_violations.append(f"{invoice_prefix}Invalid invoice date format")
                
                # Policy 3: Required fields validation
                required_fields = ["tax_id", "company_name", "vendor_name", "total_amount"]
                for field in required_fields:
                    if not extracted_data.get(field):
                        all_violations.append(f"{invoice_prefix}Missing required field: {field}")
            
            # Update state
            state["policy_violations"] = all_violations
            state["workflow_stage"] = "verification_completed"
            
            if all_violations:
                violation_message = f"Policy violations found in {len(extracted_data_list)} invoice(s) - please fix these issues and resubmit"
                
                state["messages"] = state.get("messages", []) + [
                    {"role": "assistant", "content": violation_message}
                ]
            else:
                success_message = f"Policy verification passed for all {len(extracted_data_list)} invoice(s) - all company policies are satisfied"
                state["messages"] = state.get("messages", []) + [
                    {"role": "assistant", "content": success_message}
                ]
            
            self.logger.info(f"Policy verification completed. Violations: {len(all_violations)}")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error in policy verification: {e}")
            state["policy_violations"] = [f"System error: {str(e)}"]
            state["workflow_stage"] = "verification_failed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"Failed to verify policies: {str(e)}"}
            ]
            return state
    
    async def _wait_for_fixes_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node: Wait for user to provide fixes for policy violations."""
        self.logger.info("⏳ Waiting for user to provide fixes")
        try:
            violations = state.get("policy_violations", [])
            
            # Create violation details message for user
            violation_details = "Policy violations found:\n\n"
            for i, violation in enumerate(violations, 1):
                violation_details += f"{i}. {violation}\n"
            violation_details += "\nPlease provide corrections for these issues."
            
            state["workflow_stage"] = "awaiting_fixes"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": violation_details}
            ]
            
            self.logger.info("🔑 Workflow will interrupt here, waiting for user fixes")
            # 🔑 關鍵：工作流會在這裡中斷，等待用戶輸入
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error in wait for fixes: {e}")
            state["workflow_stage"] = "wait_fixes_failed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"Failed to process violations: {str(e)}"}
            ]
            return state
    
    async def _user_confirmation_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 3: Generate reimbursement form and ask for confirmation."""
        self.logger.info("📝 Processing user confirmation node")
        try:
            if state.get("user_confirmation", False) is True:
                return state
            extracted_data_list = state.get("extracted_data", [])

            # Generate summary for all invoices
            total_invoices = len(extracted_data_list)
            total_amount_all = sum(float(inv.get("total_amount", 0)) for inv in extracted_data_list if not inv.get("parsing_error"))
            
            confirmation_message = (
                f"📋 Reimbursement request prepared:\n"
                f"- Total invoices: {total_invoices}\n"
                f"- Total amount: ${total_amount_all:.2f}\n\n"
                f"Please review and reply CONFIRM to proceed or CANCEL to abort."
            )

            state["workflow_stage"] = "awaiting_confirmation"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": confirmation_message}
            ]

            self.logger.info("🔑 Workflow will interrupt here, waiting for user confirmation")
            return state
        except Exception as e:
            self.logger.error(f"❌ Error generating confirmation: {e}")
            state["workflow_stage"] = "confirmation_failed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"Failed to generate reimbursement form: {str(e)}"}
            ]
            return state
    
    async def _manager_notification_node(self, state: InvoiceWorkflowState) -> InvoiceWorkflowState:
        """Node 4: Send notification to manager (mock implementation)."""
        self.logger.info("📧 Processing manager notification node")
        try:
            extracted_data_list = state.get("extracted_data", [])
            
            # Generate summary for notification
            total_invoices = len(extracted_data_list)
            total_amount = sum(float(inv.get("total_amount", 0)) for inv in extracted_data_list if not inv.get("parsing_error"))
            
            # Mock email notification
            notification_details = {
                "to": "manager@company.com",
                "subject": f"New Reimbursement Request - {total_invoices} Invoice(s)",
                "body": f"""
                New reimbursement request submitted:

                Employee: {state.get('user_id')}
                Total Invoices: {total_invoices}
                Total Amount: ${total_amount:.2f}
                Submission Date: {datetime.now().isoformat()}

                Invoice Details:
                {self._format_invoice_list(extracted_data_list)}

                Please review and approve/reject in the system.
                """,
                "status": "sent_successfully"
            }
            
            # Simulate saving to database
            for invoice_data in extracted_data_list:
                if not invoice_data.get("parsing_error"):
                    await self._save_reimbursement_form(invoice_data)
            
            success_message = f"✅ Reimbursement request with {total_invoices} invoice(s) (${total_amount:.2f}) submitted successfully for manager approval"
            
            state["manager_notification_sent"] = True
            state["workflow_stage"] = "completed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": success_message}
            ]
            
            self.logger.info("Manager notification sent successfully")
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error sending manager notification: {e}")
            state["workflow_stage"] = "notification_failed"
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": f"Failed to send manager notification: {str(e)}"}
            ]
            return state
    
    def _format_invoice_list(self, invoices: List[Dict[str, Any]]) -> str:
        """Format invoice list for email notification."""
        lines = []
        for idx, inv in enumerate(invoices, 1):
            if inv.get("parsing_error"):
                lines.append(f"  {idx}. [Error: {inv.get('parsing_error')}]")
            else:
                lines.append(
                    f"  {idx}. {inv.get('vendor_name', 'N/A')} - "
                    f"${inv.get('total_amount', 0)} - "
                    f"{inv.get('invoice_date', 'N/A')} - "
                    f"Tax ID: {inv.get('tax_id', 'N/A')}"
                )
        return "\n".join(lines)
    
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
        """Handle user response during workflow using interrupt/resume mechanism."""
        
        # Handle confirmation responses
        if state.get("workflow_stage") == "awaiting_confirmation":
            upper_resp = user_response.strip().upper()
            if upper_resp in ["CONFIRM", "YES", "APPROVE", "OK"]:
                # Positive confirmation – set flag and resume graph
                # Graph will automatically continue from user_confirmation → manager_notification via conditional edge
                state["user_confirmation"] = True
                state["workflow_stage"] = "confirmed"
                self.logger.info("🔄 User confirmed, resuming workflow for notification")

                return await self._manager_notification_node(state)
            if upper_resp in ["CANCEL", "NO", "REJECT"]:
                # Cancellation – clear workflow state and terminate
                state["user_confirmation"] = False
                state["workflow_stage"] = "cancelled"
                state["reimbursement_form"] = None
                state["extracted_data"] = None
                state["policy_violations"] = None
                state["messages"] = state.get("messages", []) + [
                    {"role": "assistant", "content": "Reimbursement request cancelled. Please submit a new invoice if needed."}
                ]
                self.logger.info("🛑 User cancelled - state cleared")
                return state
            # Invalid input at confirmation stage
            self.logger.info("⚠️ Non-confirm/cancel input received during confirmation stage")
            state["messages"] = state.get("messages", []) + [
                {"role": "assistant", "content": "Please reply CONFIRM to proceed or CANCEL to abort."}
            ]
            return state
        
        # Handle policy violation fixes - append user message and resume to re-extract
        if state.get("workflow_stage") == "awaiting_fixes":
            self.logger.info("🔄 User provided fixes, resuming workflow from invoice_analysis")
            state["messages"] = state.get("messages", []) + [
                {"role": "user", "content": user_response}
            ]
            # Resume graph - will continue from wait_for_fixes → invoice_analysis → policy_verification
            return await self._workflow_graph.ainvoke(state)
        
        return state