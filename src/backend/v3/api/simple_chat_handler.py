"""Simple chat handler for LangGraph Invoice Workflow processing.

RECOMMENDED APPROACH for invoice workflow:
This handler uses InvoiceProcessingWorkflow (LangGraph-based) which provides:
- Proper state management with interrupt/resume semantics
- Multi-round conversation support with history awareness
- Policy validation and fix cycles
- Automatic database persistence to Cosmos DB

Advantages over SimpleChatAgent:
- LangGraph provides deterministic workflow control
- State is properly managed across conversation turns
- Supports complex multi-step processes with validation
- Easier to test and maintain

Usage:
- Direct API: POST /v3/simple_chat with message parameter
- The handler automatically detects invoice workflow teams and routes requests
"""

import asyncio
import logging
from typing import Optional, Dict
import json

from common.database.database_factory import DatabaseFactory
from v3.magentic_agents.invoice_workflow import InvoiceProcessingWorkflow


class SimpleChatHandler:
    """Handler for LangGraph Invoice Workflow processing without multi-agent orchestration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # LangGraph workflow for invoice processing
        self._invoice_workflow = InvoiceProcessingWorkflow()
        # Store workflow states per user
        self._workflow_states: Dict[str, Dict] = {}
        
    async def is_simple_chat_team(self, user_id: str) -> bool:
        """
        Check if the current user's team is configured to use Invoice Workflow.
        
        Args:
            user_id: The user ID
            
        Returns:
            True if team uses Invoice Workflow, False otherwise
        """
        try:
            memory_store = await DatabaseFactory.get_database(user_id=user_id)
            user_current_team = await memory_store.get_current_team(user_id=user_id)
            
            if not user_current_team:
                self.logger.warning(f"No current team found for user {user_id}")
                return False
                
            team = await memory_store.get_team_by_id(team_id=user_current_team.team_id)
            if not team:
                self.logger.warning(f"Team {user_current_team.team_id} not found for user {user_id}")
                return False
            
            self.logger.info(f"Checking team '{team.name}' (ID: {team.team_id}) for Invoice Workflow usage")
            
            # Check for Invoice workflow by agent names or team name
            for agent_config in team.agents:
                if agent_config.name in ['SimpleInvoiceAgent', 'InvoiceProcessingAgent']:
                    self.logger.info(f"✅ Found Invoice workflow agent: {agent_config.name}")
                    return True
            
            # Fallback check: If no specific agent found, check team name
            team_name_lower = team.name.lower()
            if "invoice" in team_name_lower or "simple" in team_name_lower:
                self.logger.info(f"✅ Detected Invoice workflow team by name: {team.name}")
                return True
                    
            self.logger.info(f"❌ No Invoice workflow found in team '{team.name}'")
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking if team uses invoice workflow: {e}")
            return False
    
    async def handle_invoice_workflow(self, user_id: str, input_task) -> str:
        """
        Handle an invoice processing request using LangGraph Invoice Workflow.
        
        Args:
            user_id: The user ID
            input_task: The input task with user's message and optional images
            
        Returns:
            Complete response string as JSON
        """
        try:
            self.logger.info(f"🚀 Processing direct invoice workflow request for user {user_id}")
            
            # Initialize workflow if not done already
            if not self._invoice_workflow._is_initialized:
                await self._invoice_workflow.initialize()
            
            user_message = input_task.description
            images = getattr(input_task, 'images', None)  # Get images if available
            
            if images:
                self.logger.info(f"📎 Processing {len(images)} images with workflow")
            
            # Check if user has an existing workflow state
            user_key = f"workflow_{user_id}"
            existing_state = self._workflow_states.get(user_key)
            if existing_state and existing_state.get("workflow_stage") == "awaiting_confirmation":
                # User is responding to a confirmation request
                self.logger.info(f"🔄 Handling user response in confirmation state")
                
                # Handle confirmation or rejection
                updated_state = await self._invoice_workflow.handle_user_response(
                    existing_state, user_message
                )
                
                # Update stored state
                self._workflow_states[user_key] = updated_state
                
                # Create JSON response
                response_data = self._create_json_response(updated_state)
                
                # Clear state if workflow is complete
                if updated_state.get("workflow_stage") in ["completed", "cancelled"]:
                    self._workflow_states.pop(user_key, None)
                    
                return json.dumps(response_data)
                
            elif existing_state and existing_state.get("workflow_stage") == "awaiting_fixes":
                # User is providing fixes for policy violations
                self.logger.info(f"🔧 Handling policy violation fixes")
                
                # Handle fixes
                updated_state = await self._invoice_workflow.handle_user_response(
                    existing_state, user_message
                )
                
                # Update stored state
                self._workflow_states[user_key] = updated_state
                
                # Create JSON response
                response_data = self._create_json_response(updated_state)
                
                return json.dumps(response_data)
            else:
                # New invoice processing request
                self.logger.info(f"📄 Starting new invoice workflow")
                
                # Process through complete workflow with images
                result_state = await self._invoice_workflow.process_invoice_workflow(
                    user_id=user_id,
                    user_message=user_message,
                    images=images  # Pass images to workflow
                )
                
                # Store state for potential follow-up
                self._workflow_states[user_key] = result_state
                
                # Create JSON response
                response_data = self._create_json_response(result_state)
                
                # Clear state if workflow is complete
                if result_state.get("workflow_stage") in ["completed", "cancelled"]:
                    self._workflow_states.pop(user_key, None)
                
                return json.dumps(response_data)
                
        except Exception as e:
            self.logger.error(f"❌ Error in invoice workflow: {e}")
            
            # Return error response in expected JSON format
            error_response = {
                "state": "ERROR",
                "message": f"❌ Workflow error: {str(e)}",
                "invoices": []
            }
            return json.dumps(error_response)
    
    def clear_user_state(self, user_id: str) -> bool:
        """
        Clear stored workflow state for a specific user.
        
        Args:
            user_id: The user ID whose state should be cleared
            
        Returns:
            True if state was cleared, False if no state existed
        """
        user_key = f"workflow_{user_id}"
        if user_key in self._workflow_states:
            del self._workflow_states[user_key]
            self.logger.info(f"🗑️ Cleared workflow state for user {user_id}")
            return True
        else:
            self.logger.info(f"ℹ️ No workflow state found for user {user_id}")
            return False
    
    def clear_all_states(self) -> int:
        """
        Clear all stored workflow states for all users.
        
        Returns:
            Number of states that were cleared
        """
        count = len(self._workflow_states)
        self._workflow_states.clear()
        self.logger.info(f"🗑️ Cleared all workflow states ({count} users)")
        return count
    
    def get_active_users(self) -> list:
        """
        Get list of user IDs with active workflow states.
        
        Returns:
            List of user IDs
        """
        return [key.replace("workflow_", "") for key in self._workflow_states.keys()]
    
    async def reset_workflow(self, user_id: str) -> None:
        """
        Reset the workflow instance (reinitialize).
        Useful for clearing any cached state in the workflow itself.
        
        Args:
            user_id: The user ID (for logging purposes)
        """
        self.logger.info(f"🔄 Resetting workflow instance for user {user_id}")
        self._invoice_workflow = InvoiceProcessingWorkflow()
        self.logger.info(f"✅ Workflow instance reset complete")
            
    def _create_json_response(self, workflow_state: Dict) -> Dict:
        """Create standardized JSON response from workflow state."""
        
        # Get the latest assistant message
        latest_message = ""
        messages = workflow_state.get("messages", [])
        for msg in reversed(messages):
            # Handle both dict and LangGraph message objects (AIMessage, HumanMessage)
            if hasattr(msg, 'content'):
                # LangGraph message object
                latest_message = msg.content
            elif isinstance(msg, dict):
                # Dictionary format
                latest_message = msg.get("content", "")
            else:
                continue
            break
        
        # Extract invoice data - now supports multiple invoices
        invoices = []
        extracted_data_list = workflow_state.get("extracted_data", [])
        
        # Handle both list and dict (backwards compatibility)
        if isinstance(extracted_data_list, dict):
            extracted_data_list = [extracted_data_list]
        
        for extracted_data in extracted_data_list:
            if extracted_data and not extracted_data.get("parsing_error"):
                invoices.append({
                    "tax_id": extracted_data.get("tax_id", ""),
                    "company_name": extracted_data.get("company_name", ""),
                    "vendor_name": extracted_data.get("vendor_name", ""),
                    "amount": str(extracted_data.get("total_amount", "")),
                    "date": extracted_data.get("invoice_date", ""),
                    "items": ", ".join(extracted_data.get("items", [])) if isinstance(extracted_data.get("items"), list) else str(extracted_data.get("items", ""))
                })
        
        # Map workflow stage to state
        stage_to_state = {
            "starting": "EXTRACT",
            "analysis_completed": "EXTRACT", 
            "verification_completed": "VALIDATE",
            "awaiting_fixes": "VALIDATE",  # 🔧 添加等待修复状态
            "fixes_provided": "EXTRACT",
            "awaiting_confirmation": "CONFIRM",
            "confirmed": "CONFIRM", 
            "completed": "NOTIFY",
            "cancelled": "CANCELLED"
        }
        
        current_state = stage_to_state.get(
            workflow_state.get("workflow_stage", "starting"), 
            "UNKNOWN"
        )
        
        return {
            "state": current_state,
            "message": latest_message,
            "invoices": invoices,
        }
    
    