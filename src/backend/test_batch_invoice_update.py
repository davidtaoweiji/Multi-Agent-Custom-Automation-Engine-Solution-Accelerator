"""
Test batch invoice update functionality.
Tests:
1. Query pending invoices
2. Approve multiple invoices in one request
3. Reject multiple invoices in one request
"""

import asyncio
import logging
from v3.magentic_agents.invoice_manager_agent import InvoiceManagerAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress Azure HTTP logging
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.ERROR)
logging.getLogger('azure.identity').setLevel(logging.ERROR)


async def main():
    """Test batch invoice update functionality."""
    
    manager_id = "00000000-0000-0000-0000-000000000000"
    
    logger.info("🚀 Starting Batch Invoice Update Test")
    logger.info("="*80)
    
    try:
        # Initialize agent
        logger.info(f"\n🤖 Initializing agent for manager: {manager_id}")
        agent = InvoiceManagerAgent(manager_id=manager_id)
        await agent.initialize()
        logger.info("✅ Agent initialized\n")
        
        # Step 1: Query pending invoices
        logger.info("="*80)
        logger.info("STEP 1: Query Pending Invoices")
        logger.info("="*80)
        response = await agent.process_request("Show me all pending invoices")
        logger.info(f"\n📄 Response:\n{response}\n")
        
        # Step 2: Approve multiple invoices using comma-separated IDs
        logger.info("="*80)
        logger.info("STEP 2: Batch Approve Multiple Invoices")
        logger.info("="*80)
        # Example: Use actual invoice IDs from the query above
        response = await agent.process_request(
            "Approve invoices INV-001, INV-002, INV-003"
        )
        logger.info(f"\n📄 Response:\n{response}\n")
        
        # Step 3: Reject multiple invoices with reason
        logger.info("="*80)
        logger.info("STEP 3: Batch Reject Multiple Invoices")
        logger.info("="*80)
        response = await agent.process_request(
            "Reject invoices INV-004, INV-005 because they exceed the budget limit"
        )
        logger.info(f"\n📄 Response:\n{response}\n")
        
        # Step 4: Test conversational follow-up
        logger.info("="*80)
        logger.info("STEP 4: Conversational Follow-up")
        logger.info("="*80)
        response = await agent.process_request(
            "Show me the remaining pending invoices"
        )
        logger.info(f"\n📄 Response:\n{response}\n")
        
        # Cleanup
        await agent.close()
        logger.info("✅ Agent closed successfully")
        
        logger.info("\n" + "="*80)
        logger.info("🎉 Batch Update Test Completed!")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
