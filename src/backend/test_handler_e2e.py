#!/usr/bin/env python3
"""
End-to-End Testing script for Invoice Processing Workflow
Tests: Invalid Invoice → Validation Failed → Correction → Confirmation → Notification
Uses the same handler throughout the entire process
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from v3.api.simple_chat_handler import SimpleChatHandler


class SimpleInputTask:
    """Mock input task for testing."""
    def __init__(self, description: str):
        self.description = description
        self.session_id = "test_session"


async def test_complete_workflow_with_validation_fix():
    """Test complete workflow: Invalid → Validation Failed → Fix → Confirmation → Notification"""
    print("🧪 Testing Complete Workflow with Same Handler")
    print("=" * 60)
    
    user_id = "test_user_e2e"
    handler = SimpleChatHandler()  # Use same handler throughout
    
    try:
        # Step 1: Submit invalid invoice (missing fields, meal over limit, old date)
        print("📝 STEP 1: Submit Invalid Invoice")
        print("-" * 40)
        
        invalid_invoice = "create a invoice for me: Tax ID 123, Company Name 456, Vendor Name KFC, Amount 250, Date 2023-01-01, Items meal"
        print(f"Input: {invalid_invoice}")
        print()
        
        input_task = SimpleInputTask(invalid_invoice)
        response1 = await handler.handle_invoice_workflow(user_id, input_task)
        data1 = json.loads(response1)
        
        print(f"State: {data1.get('state')}")
        print(f"Message: {data1.get('message')}")
        
        if data1.get('state') != 'VALIDATE':
            print(f"❌ Expected VALIDATE state but got: {data1.get('state')}")
            return False
        
        print("✅ Step 1 passed - Validation failed as expected")
        print(data1)
        print(response1)
        
        # Step 2: Submit corrections using the same handler
        print("📝 STEP 2: Submit Corrections")
        print("-" * 40)
        
        correction = "update: Tax ID 123456789, Company Name Microsoft Corp, Amount 150, Date 2025-11-01"
        print(f"Correction: {correction}")
        print()
        
        correction_task = SimpleInputTask(correction)
        response2 = await handler.handle_invoice_workflow(user_id, correction_task)
        data2 = json.loads(response2)
        
        print(f"State: {data2.get('state')}")
        print(f"Message: {data2.get('message')}")
        
        # Check corrected invoice data
        invoices2 = data2.get('invoices', [])
        if invoices2:
            print("📋 Corrected Invoice Data:")
            for key, value in invoices2[0].items():
                print(f"  {key}: {value}")
            print()
        print(data2)
        if data2.get('state') != 'CONFIRM':
            print(f"❌ Expected CONFIRM state but got: {data2.get('state')}")
            return False
        
        print("✅ Step 2 passed - Corrections processed, awaiting confirmation")
        print()
        
        # Step 3: User confirmation using the same handler
        print("📝 STEP 3: User Confirmation")
        print("-" * 40)
        
        confirmation = "CONFIRM"
        print(f"User response: {confirmation}")
        print()
        
        confirmation_task = SimpleInputTask(confirmation)
        response3 = await handler.handle_invoice_workflow(user_id, confirmation_task)
        data3 = json.loads(response3)
        
        print(f"State: {data3.get('state')}")
        print(f"Message: {data3.get('message')}")
        
        # Check final invoice data
        invoices3 = data3.get('invoices', [])
        if invoices3:
            print("📋 Final Invoice Data:")
            print(invoices3)
        
        if data3.get('state') not in ['NOTIFY', 'COMPLETED']:
            print(f"❌ Expected NOTIFY/COMPLETED state but got: {data3.get('state')}")
            return False
        
        print("✅ Step 3 passed - Confirmation processed, manager notified")
        print()
        
    #     # Step 4: Summary
    #     print("📝 STEP 4: Final Summary")
    #     print("-" * 40)
    #     print(f"Final State: {data3.get('state')}")
    #     print(f"Final Message: {data3.get('message')}")
    #     print()
        
    #     print("🎉 COMPLETE WORKFLOW TEST PASSED!")
    #     print("✅ Successfully processed: Invalid → Validation → Fix → Confirmation → Notification")
    #     print("✅ Used same handler throughout entire process")
        return True
        
    except Exception as e:
        print(f"❌ Error in complete workflow test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the complete end-to-end test."""
    print("🧪 Invoice Workflow End-to-End Testing")
    print("=" * 50)
    print("Testing: Invalid Invoice → Validation → Fix → Confirmation → Notification")
    print("Using the same handler throughout the entire process")
    print()
    
    # Run the complete workflow test
    success = await test_complete_workflow_with_validation_fix()
    
    print("\n🏁 Testing Summary")
    print("=" * 30)
    if success:
        print("✅ End-to-End Workflow Test: PASSED")
        print("🎉 All stages completed successfully!")
    else:
        print("❌ End-to-End Workflow Test: FAILED")
        print("⚠️ Check the logs above for details")


if __name__ == "__main__":
    asyncio.run(main())