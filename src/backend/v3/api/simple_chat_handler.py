"""Simple chat handler for direct SimpleChatAgent responses without orchestration."""

import asyncio
import logging
from typing import Optional, Dict
import json

from common.database.database_factory import DatabaseFactory
from v3.config.settings import connection_config
from v3.models.messages import WebsocketMessageType
from v3.magentic_agents.simple_chat_agent import SimpleChatAgent
from v3.magentic_agents.magentic_agent_factory import MagenticAgentFactory


class SimpleChatHandler:
    """Handler for direct SimpleChatAgent responses without multi-agent orchestration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Cache for reusing agents per user/team
        self._agent_cache: Dict[str, SimpleChatAgent] = {}
        
    async def _get_or_create_agent(self, user_id: str, agent_config) -> SimpleChatAgent:
        """
        Get existing agent from cache or create new one.
        
        Args:
            user_id: User ID
            agent_config: Agent configuration
            
        Returns:
            SimpleChatAgent instance
        """
        # Create cache key based on user and agent
        cache_key = f"{user_id}_{agent_config.name}"
        
        # Check if agent already exists in cache
        if cache_key in self._agent_cache:
            existing_agent = self._agent_cache[cache_key]
            if existing_agent.is_open:
                self.logger.info(f"♻️ Reusing existing agent: {agent_config.name}")
                return existing_agent
            else:
                # Remove closed agent from cache
                del self._agent_cache[cache_key]
        
        # Create new agent
        self.logger.info(f"🆕 Creating new agent: {agent_config.name}")
        simple_agent = SimpleChatAgent(
            agent_name=agent_config.name,
            agent_description=getattr(agent_config, "description", ""),
            system_message=getattr(agent_config, "system_message", ""),
            model_deployment_name=agent_config.deployment_name,
            user_id=user_id,
        )
        
        # Initialize agent
        await simple_agent.open()
        
        # Cache the agent
        self._agent_cache[cache_key] = simple_agent
        
        return simple_agent
    
    async def cleanup_agents(self) -> None:
        """
        Clean up all cached agents. Should be called when application shuts down.
        """
        self.logger.info(f"🧹 Cleaning up {len(self._agent_cache)} cached agents...")
        
        for cache_key, agent in self._agent_cache.items():
            try:
                if agent.is_open:
                    await agent.close()
                    self.logger.info(f"✅ Closed agent: {cache_key}")
            except Exception as e:
                self.logger.error(f"❌ Error closing agent {cache_key}: {e}")
        
        self._agent_cache.clear()
        self.logger.info("🧹 Agent cleanup completed")
    
    async def is_simple_chat_team(self, user_id: str) -> bool:
        """
        Check if the current user's team is configured to use SimpleChatAgent.
        
        Args:
            user_id: The user ID
            
        Returns:
            True if team uses SimpleChatAgent, False otherwise
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
            
            self.logger.info(f"Checking team '{team.name}' (ID: {team.team_id}) for SimpleChatAgent usage")
            
            # Check for SimpleChatAgent by name (SimpleInvoiceAgent or SimpleDocumentAnalyzer)
            for agent_config in team.agents:
                if agent_config.name in ['SimpleInvoiceAgent', 'SimpleDocumentAnalyzer']:
                    self.logger.info(f"✅ Found SimpleChatAgent: {agent_config.name}")
                    return True
            
            # Fallback check: If no specific SimpleChatAgent found, check team name
            team_name_lower = team.name.lower()
            if "simple" in team_name_lower and "invoice" in team_name_lower:
                self.logger.info(f"✅ Detected Simple Invoice Team by name: {team.name}")
                return True
                    
            self.logger.info(f"❌ No SimpleChatAgent found in team '{team.name}'")
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking if team uses simple chat: {e}")
            return False
    
    async def handle_simple_chat_request(self, user_id: str, input_task) -> None:
        """
        Handle a chat request using SimpleChatAgent and send response via SSE.
        
        Args:
            user_id: The user ID
            input_task: The input task with user's message
        """
        try:
            self.logger.info(f"🚀 Processing simple chat request for user {user_id}")
            
            # Get team configuration
            memory_store = await DatabaseFactory.get_database(user_id=user_id)
            user_current_team = await memory_store.get_current_team(user_id=user_id)
            team = await memory_store.get_team_by_id(team_id=user_current_team.team_id)
            
            # Find SimpleChatAgent in the team (SimpleInvoiceAgent or SimpleDocumentAnalyzer)
            simple_agent_config = None
            for agent_config in team.agents:
                if (agent_config.name in ['SimpleInvoiceAgent', 'SimpleDocumentAnalyzer'] and 
                    agent_config.deployment_name):  # Has a valid model deployment
                    simple_agent_config = agent_config
                    self.logger.info(f"Found SimpleChatAgent: {agent_config.name}")
                    break
            
            if not simple_agent_config:
                raise ValueError("No SimpleChatAgent (SimpleInvoiceAgent/SimpleDocumentAnalyzer) found in team configuration")
            
            # Get or create SimpleChatAgent (reuse existing if available)
            simple_agent = await self._get_or_create_agent(user_id, simple_agent_config)
            
            # Send start message
            await connection_config.send_status_update_async(
                {
                    "type": WebsocketMessageType.AGENT_MESSAGE,
                    "data": {
                        "agent_name": simple_agent_config.name,
                        "content": f"🤖 {simple_agent_config.name} is processing your request...",
                        "status": "processing",
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                },
                user_id,
                message_type=WebsocketMessageType.AGENT_MESSAGE,
            )
            
            # Process the request with true streaming support
            accumulated_response = ""
            
            # Stream response chunks as they are generated
            async for chunk in simple_agent.invoke_stream_async(
                message=input_task.description,
                images=None,  # TODO: Add image support if needed
                chat_history=None  # Agent manages its own history
            ):
                accumulated_response += chunk
                
                # Send each chunk immediately via SSE
                await connection_config.send_status_update_async(
                    {
                        "type": WebsocketMessageType.AGENT_MESSAGE,
                        "data": {
                            "agent_name": simple_agent_config.name,
                            "content": chunk,
                            "status": "streaming",
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                    },
                    user_id,
                    message_type=WebsocketMessageType.AGENT_MESSAGE,
                )
                
            # Send final completion message
            await connection_config.send_status_update_async(
                {
                    "type": WebsocketMessageType.AGENT_MESSAGE,
                    "data": {
                        "agent_name": simple_agent_config.name,
                        "content": "",  # Empty content for completion signal
                        "status": "completed",
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                },
                user_id,
                message_type=WebsocketMessageType.AGENT_MESSAGE,
            )
            
            # Send final result with accumulated response
            await connection_config.send_status_update_async(
                {
                    "type": WebsocketMessageType.FINAL_RESULT_MESSAGE,
                    "data": {
                        "content": accumulated_response,  # Use the accumulated response
                        "status": "completed",
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                },
                user_id,
                message_type=WebsocketMessageType.FINAL_RESULT_MESSAGE,
            )
            
            self.logger.info(f"✅ Simple chat request completed for user {user_id}")
                
        except Exception as e:
            self.logger.error(f"❌ Error handling simple chat request: {e}")
            
            # Send error message
            await connection_config.send_status_update_async(
                {
                    "type": WebsocketMessageType.AGENT_MESSAGE,
                    "data": {
                        "agent_name": "System",
                        "content": f"Sorry, I encountered an error processing your request: {str(e)}",
                        "status": "error",
                        "timestamp": asyncio.get_event_loop().time(),
                    },
                },
                user_id,
                message_type=WebsocketMessageType.AGENT_MESSAGE,
            )
            
            raise