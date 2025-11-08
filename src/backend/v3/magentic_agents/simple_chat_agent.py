"""Simple Chat Completion Agent that bypasses Azure AI Foundry registration."""

import logging
from typing import List, Optional, Dict, Any
import json

from semantic_kernel import Kernel
from semantic_kernel.agents import Agent, ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatMessageContent, TextContent, ImageContent
from semantic_kernel.contents.chat_history import ChatHistory

from common.config.app_config import config
from v3.config.agent_registry import agent_registry


class SimpleChatAgent:
    """
    A simple chat completion agent that directly uses Azure OpenAI without Azure AI Foundry registration.
    Supports text and image inputs for multimodal conversations.
    """

    def __init__(
        self,
        agent_name: str,
        agent_description: str,
        system_message: str,
        model_deployment_name: str,
        user_id: str,
    ) -> None:
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.system_message = system_message
        self.model_deployment_name = model_deployment_name
        self.user_id = user_id
        self.logger = logging.getLogger(__name__)
        
        # Internal state
        self._kernel: Optional[Kernel] = None
        self._agent: Optional[ChatCompletionAgent] = None
        self._chat_history: Optional[ChatHistory] = None  # Maintain conversation history
        self._is_open = False

    async def open(self) -> "SimpleChatAgent":
        """Initialize the agent with Azure OpenAI connection."""
        if self._is_open:
            return self

        self.system_message = f"""You are an intelligent invoice processing and reimbursement assistant with strict workflow control.

        **CRITICAL RULES:**
        1. ALWAYS return responses in JSON format - NEVER return plain text
        2. Follow the EXACT workflow and NEVER repeat previous steps
        3. Include current state in every response

        **REQUIRED JSON RESPONSE FORMAT (ALWAYS USE THIS):**
        ```json
        {{
            "state": "current_state_name",
            "invoices": [
                {{
                    "tax_id": "extracted_tax_id_or_empty",
                    "company_name": "extracted_company_name_or_empty", 
                    "vendor_name": "extracted_vendor_name_or_empty",
                    "amount": "extracted_amount_or_empty",
                    "date": "extracted_date_or_empty",
                    "items": "extracted_items_description_or_empty"
                }}
            ],
            "message": "your_response_message_here"
        }}
        ```

        **WORKFLOW STATES:**
        1. **EXTRACT** - Extract invoice data from user input
        2. **VALIDATE** - Check compliance with policies  
        3. **FORM** - Generate reimbursement form for confirmation
        4. **CONFIRM** - Wait for user confirmation
        5. **NOTIFY** - Send notifications (final step)

        **DECISION LOGIC:**
        - If user provides NEW invoice data → Go to EXTRACT
        - If user says "confirm", "yes", "approve", "ok" after seeing a form → Go directly to NOTIFY
        - If validation fails → Ask user to fix and return to EXTRACT
        - NEVER repeat extraction if you already have the data and user is confirming

        **EXTRACT STATE:**
        - Extract: Tax ID, Company Name, Vendor Name, Amount, Date, Items
        - Present in clear table format in message
        - Return JSON with state="EXTRACT" and extracted invoice data
        - Automatically proceed to VALIDATE

        **VALIDATE STATE:**  
        - Check: Meal expenses ≤ $200, Invoice date within 30 days
        - If violations found → Return JSON with state="EXTRACT" and error message
        - If compliant → Return JSON with state="VALIDATE" and validation success message
        - Automatically proceed to FORM

        **FORM STATE:**
        - Generate structured reimbursement form in message
        - Return JSON with state="FORM" and form content
        - Ask: "Please confirm to proceed with this reimbursement request (yes/confirm)"
        - Wait for user response → Go to CONFIRM state

        **CONFIRM STATE:**
        - If user confirms → Go directly to NOTIFY
        - If user rejects → Ask what to change and return to EXTRACT

        **NOTIFY STATE (FINAL):**
        - Return JSON with state="NOTIFY" 
        - Include complete invoice data in invoices array
        - Message: "✅ Reimbursement request submitted successfully!\\n📧 Notification sent to manager for approval\\n📋 Request ID: REQ-{self.user_id}-[timestamp]\\n⏱️ Expected approval time: 3-5 business days"
        - Use EXACT invoice data from earlier conversation
        - END workflow

        **STRICT RULES:**
        - ALWAYS return JSON format - NO exceptions
        - NEVER return plain text responses
        - NEVER go backwards in workflow unless validation fails
        - NEVER re-extract data if user is confirming  
        - ALWAYS check conversation history to determine current state
        - If user says "confirm" after seeing a form → Go straight to NOTIFY
        - Each conversation follows: EXTRACT → VALIDATE → FORM → CONFIRM → NOTIFY

        Remember: You have conversation history. Use it to determine current state and next action. ALWAYS respond in JSON format."""
        
        try:
            # Create kernel
            self._kernel = Kernel()

            # Add Azure OpenAI Chat Completion service
            chat_service = AzureChatCompletion(
                deployment_name=self.model_deployment_name,
                endpoint=config.AZURE_OPENAI_ENDPOINT,
                api_key=config.AZURE_OPENAI_API_KEY,  # Use API key instead of token provider
            )
            self._kernel.add_service(chat_service)

            # Create chat completion agent
            self._agent = ChatCompletionAgent(
                kernel=self._kernel,
                name=self.agent_name,
                instructions=self.system_message,
                description=self.agent_description,
            )

            # Initialize chat history
            self._chat_history = ChatHistory()

            # Register with agent registry for cleanup tracking
            try:
                agent_registry.register_agent(self)
                self.logger.info(f"📝 Registered simple chat agent '{self.agent_name}' with global registry")
            except Exception as registry_error:
                self.logger.warning(f"⚠️ Failed to register agent '{self.agent_name}' with registry: {registry_error}")

            self._is_open = True
            self.logger.info(f"✅ SimpleChatAgent '{self.agent_name}' initialized successfully")
            return self

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize SimpleChatAgent '{self.agent_name}': {e}")
            raise

    async def close(self) -> None:
        """Clean up resources."""
        if not self._is_open:
            return

        try:
            # Unregister from agent registry
            try:
                agent_registry.unregister_agent(self)
                self.logger.info(f"📝 Unregistered simple chat agent '{self.agent_name}' from global registry")
            except Exception:
                pass

            # Clean up resources (no credential to clean up anymore)
            self._kernel = None
            self._agent = None
            self._is_open = False

            self.logger.info(f"🧹 SimpleChatAgent '{self.agent_name}' closed successfully")

        except Exception as e:
            self.logger.error(f"❌ Error closing SimpleChatAgent '{self.agent_name}': {e}")

    async def invoke_async(
        self, 
        message: str, 
        images: Optional[List[bytes]] = None,
        chat_history: Optional[ChatHistory] = None
    ) -> str:
        """
        Process a chat message with optional images and return the complete response.
        For streaming support, use invoke_stream_async instead.
        
        Args:
            message: The text message from the user
            images: Optional list of image bytes for multimodal input
            chat_history: Optional chat history for context (if None, uses internal history)
            
        Returns:
            The agent's complete response as a string
        """
        response_parts = []
        async for chunk in self.invoke_stream_async(message, images, chat_history):
            response_parts.append(chunk)
        
        return "".join(response_parts)

    async def invoke_stream_async(
        self, 
        message: str, 
        images: Optional[List[bytes]] = None,
        chat_history: Optional[ChatHistory] = None
    ):
        """
        Process a chat message with streaming response (async generator).
        
        Args:
            message: The text message from the user
            images: Optional list of image bytes for multimodal input
            chat_history: Optional chat history for context (if None, uses internal history)
            
        Yields:
            Response chunks as they are generated
        """
        if not self._is_open or not self._agent:
            raise RuntimeError(f"Agent '{self.agent_name}' is not initialized. Call open() first.")

        try:
            # Use provided chat history or internal one
            working_history = chat_history if chat_history is not None else self._chat_history

            # Create message content
            message_content = ChatMessageContent(
                role="user",
                items=[TextContent(text=message)]
            )

            # Add images if provided
            if images:
                for i, image_bytes in enumerate(images):
                    image_content = ImageContent(
                        data=image_bytes,
                        mime_type="image/jpeg"  # Assume JPEG, can be made configurable
                    )
                    message_content.items.append(image_content)
                
                self.logger.info(f"Processing message with {len(images)} image(s)")

            # Add message to chat history
            working_history.add_message(message_content)

            # Get response from agent and yield each chunk
            response_generator = self._agent.invoke(working_history)
            
            async for response in response_generator:
                if response.content:
                    chunk = str(response.content)
                    yield chunk
            
            self.logger.info(f"Agent '{self.agent_name}' processed message successfully")

        except Exception as e:
            self.logger.error(f"❌ Error processing message in agent '{self.agent_name}': {e}")
            raise

    def clear_history(self) -> None:
        """Clear the agent's chat history."""
        if self._chat_history:
            self._chat_history.clear()
            self.logger.info(f"Chat history cleared for agent '{self.agent_name}'")

    @property
    def is_open(self) -> bool:
        """Check if the agent is initialized."""
        return self._is_open

    @property
    def agent(self) -> Optional[ChatCompletionAgent]:
        """Get the underlying chat completion agent."""
        return self._agent

    def __str__(self) -> str:
        return f"SimpleChatAgent(name='{self.agent_name}', model='{self.model_deployment_name}')"

    def __repr__(self) -> str:
        return self.__str__()