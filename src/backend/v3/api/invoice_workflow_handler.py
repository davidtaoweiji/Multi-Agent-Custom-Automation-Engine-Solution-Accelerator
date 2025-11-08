"""
Invoice workflow handler that integrates LangGraph workflow with the existing system.
"""

import logging
from typing import List, Optional, Dict, Any
import asyncio

from v3.magentic_agents.invoice_workflow import InvoiceProcessingWorkflow, InvoiceWorkflowState
from v3.config.settings import connection_config
from v3.models.messages import WebsocketMessageType
from common.database.database_factory import DatabaseFactory


class InvoiceWorkflowHandler:
    """Handler for LangGraph-based invoice processing workflow."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.workflow = InvoiceProcessingWorkflow()
        # Cache for ongoing workflows per user
        self._user_workflows: Dict[str, InvoiceWorkflowState] = {}
        
    async def initialize(self):
        """Initialize the workflow handler."""
        await self.workflow.initialize()
        self.logger.info("✅ Invoice workflow handler initialized")
    
    async def handle_invoice_request(
        self, 
        user_id: str, 
        user_message: str, 
        images: Optional[List[bytes]] = None
    ) -> None:
        """
        Handle a new invoice processing request.
        
        Args:
            user_id: The user ID
            user_message: User's message/request
            images: List of invoice image bytes
        """
        try:
            self.logger.info(f"🚀 Starting invoice workflow for user {user_id}")
            
            # Send initial processing message
            await self._send_message(
                user_id,
                "🔄 **Starting Invoice Processing Workflow**\n\nAnalyzing uploaded invoices...",
                "processing"
            )
            
            # Start the workflow
            workflow_state = await self.workflow.process_invoice_workflow(
                user_id=user_id,
                user_message=user_message,
                images=images
            )
            
            # Cache the workflow state for this user
            self._user_workflows[user_id] = workflow_state
            
            # Send the workflow results
            await self._send_workflow_messages(user_id, workflow_state)
            
        except Exception as e:
            self.logger.error(f"❌ Error handling invoice request: {e}")
            await self._send_message(
                user_id,
                f"❌ **Error Processing Invoice**\n\n{str(e)}",
                "error"
            )
    
    async def handle_user_response(
        self, 
        user_id: str, 
        user_response: str
    ) -> None:
        """
        Handle user response during an ongoing workflow.
        
        Args:
            user_id: The user ID
            user_response: User's response (confirmation, fixes, etc.)
        """
        try:
            # Get existing workflow state
            workflow_state = self._user_workflows.get(user_id)
            if not workflow_state:
                await self._send_message(
                    user_id,
                    "❌ **No Active Workflow**\n\nPlease start a new invoice processing request.",
                    "error"
                )
                return
            
            self.logger.info(f"🔄 Processing user response for workflow in stage: {workflow_state.get('workflow_stage')}")
            
            # Process the user response
            updated_state = await self.workflow.handle_user_response(
                workflow_state, 
                user_response
            )
            
            # Update cached state
            self._user_workflows[user_id] = updated_state
            
            # Send updated workflow messages
            await self._send_workflow_messages(user_id, updated_state)
            
            # Clean up if workflow is completed
            if updated_state.get("workflow_stage") in ["completed", "cancelled"]:
                del self._user_workflows[user_id]
                self.logger.info(f"🧹 Cleaned up completed workflow for user {user_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling user response: {e}")
            await self._send_message(
                user_id,
                f"❌ **Error Processing Response**\n\n{str(e)}",
                "error"
            )
    
    async def _send_workflow_messages(self, user_id: str, workflow_state: InvoiceWorkflowState):
        """Send workflow messages to the user via WebSocket."""
        messages = workflow_state.get("messages", [])
        
        # Send the latest assistant messages
        for message in messages:
            if message.get("role") == "assistant":
                content = message.get("content", "")
                
                # Determine status based on content and workflow stage
                stage = workflow_state.get("workflow_stage", "")
                if "❌" in content or "error" in stage.lower():
                    status = "error"
                elif "✅" in content or stage == "completed":
                    status = "completed"
                elif "🔄" in content or "processing" in stage.lower():
                    status = "processing"
                elif "📝" in content or "confirmation" in stage.lower():
                    status = "awaiting_confirmation"
                else:
                    status = "processing"
                
                await self._send_message(user_id, content, status)
    
    async def _send_message(
        self, 
        user_id: str, 
        content: str, 
        status: str = "processing"
    ):
        """Send a message to the user via WebSocket."""
        try:
            await connection_config.send_status_update_async(
                {
                    "type": WebsocketMessageType.AGENT_MESSAGE,
                    "data": {
                        "agent_name": "InvoiceProcessingAgent",
                        "content": content,
                        "status": status,
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                },
                user_id,
                message_type=WebsocketMessageType.AGENT_MESSAGE,
            )
        except Exception as e:
            self.logger.error(f"❌ Failed to send message via WebSocket: {e}")
    
    async def get_workflow_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the current workflow status for a user."""
        workflow_state = self._user_workflows.get(user_id)
        if not workflow_state:
            return None
            
        return {
            "user_id": user_id,
            "stage": workflow_state.get("workflow_stage"),
            "has_violations": bool(workflow_state.get("policy_violations")),
            "awaiting_confirmation": workflow_state.get("workflow_stage") == "awaiting_confirmation",
            "form_id": workflow_state.get("reimbursement_form", {}).get("form_id"),
        }
    
    def has_active_workflow(self, user_id: str) -> bool:
        """Check if user has an active workflow."""
        return user_id in self._user_workflows
    
    async def cancel_workflow(self, user_id: str) -> bool:
        """Cancel an active workflow for a user."""
        if user_id in self._user_workflows:
            del self._user_workflows[user_id]
            await self._send_message(
                user_id,
                "🛑 **Workflow Cancelled**\n\nInvoice processing workflow has been cancelled.",
                "cancelled"
            )
            return True
        return False
    
    async def cleanup(self):
        """Clean up resources."""
        self._user_workflows.clear()
        self.logger.info("🧹 Invoice workflow handler cleaned up")


# Global instance
invoice_workflow_handler = InvoiceWorkflowHandler()