"""
Simple test for InvoiceManagerAgent.
1. Query pending invoices
2. Follow-up to update status of one invoice
"""

import asyncio
import logging
from v3.magentic_agents.invoice_manager_agent import InvoiceManagerAgent
from common.database.database_factory import DatabaseFactory
from v3.magentic_agents.models.data_models import Invoice, InvoiceStatus

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
    """Simple test with query and follow-up update."""
      # Get database instance
    # try:

    manager_id = "00000000-0000-0000-0000-000000000000"
    
    logger.info("🚀 Starting Simple InvoiceManagerAgent Test")
    logger.info("="*80)
    
    try:
        # db = await DatabaseFactory.get_database()

        # # Query invoices by manager_id
        # invoices = await db.get_invoices_by_manager("test_user_e2e")

        # # Filter for pending status only
        # pending_invoices = [
        #     inv for inv in invoices 
        #     if inv.status == InvoiceStatus.pending
        # ]
        
        # print(f"Found {len(pending_invoices)} pending invoices for manager 'test_user_e2e':")
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
        
        # Step 2: Follow-up to approve one invoice
        logger.info("="*80)
        logger.info("STEP 2: Follow-up - Approve First Invoice")
        logger.info("="*80)
        response = await agent.process_request("Approve the first invoice")
        logger.info(f"\n📄 Response:\n{response}\n")
        
        # # Cleanup
        # await agent.close()
        # logger.info("✅ Agent closed successfully")
        
        # logger.info("\n" + "="*80)
        # logger.info("🎉 Test Completed!")
        # logger.info("="*80)
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
