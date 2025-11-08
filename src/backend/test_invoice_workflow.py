#!/usr/bin/env python3
"""
End-to-End Testing script for Invoice Processing Workflow
Tests: Invalid Invoice → Validation Failed → Correction → Confirmation → Notification
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

from v3.magentic_agents.invoice_workflow import InvoiceProcessingWorkflow
from v3.api.simple_chat_handler import SimpleChatHandler


class SimpleInputTask:
    """Mock input task for testing."""
    def __init__(self, description: str):
        self.description = description
        self.session_id = "test_session"


async def test_complete_workflow_with_validation_fix():
    """Test complete workflow: Invalid → Validation Failed → Fix → Confirmation → Notification"""
    print("🧪 Testing Complete Workflow with Validation & Fix")
    print("=" * 60)
    
    # Step 1: Submit invalid invoice (missing required fields, old date)
    invalid_invoice = "create a invoice for me: Tax ID 123, Company Name abc , Vendor Name KFC, Amount 250, Date 2023-01-01, Items meal"
    user_id = "test_user_e2e"
    
    try:
        handler = SimpleChatHandler()
        
        print("📝 STEP 1: Submit Invalid Invoice")
        print("-" * 40)
        print(f"Input: {invalid_invoice}")
        print()
        
        input_task = SimpleInputTask(invalid_invoice)
        json_response = await handler.handle_invoice_workflow(user_id, input_task)
        response_data = json.loads(json_response)
        
        print(f"State: {response_data.get('state')}")
        print(f"Message: {response_data.get('message')}")
        print(f"Expected: Should be in VALIDATE state with violations")
        
        # Verify we're in validation state
        if response_data.get('state') != 'VALIDATE':
            print("❌ Expected VALIDATE state but got:", response_data.get('state'))
            return False
        
        print("✅ Step 1 passed - Invoice validation failed as expected")
        print()
        
        # Step 2: Submit corrections
        correction_input = "update the invoice: Tax ID 123456789, Company Name Microsoft Corp, Amount 150, Date 2023-10-01"
        
        print("📝 STEP 2: Submit Corrections")
        print("-" * 40)
        print(f"Correction: {correction_input}")
        print()
        
        # Note: For workflow continuation, we need to handle user response
        # This would normally be done through the handler's response mechanism
        # For testing, we'll simulate the workflow state continuation
        
        workflow = InvoiceProcessingWorkflow()
        await workflow.initialize()
        
        # Get the current workflow state from the handler's session
        # In real implementation, this would be retrieved from session storage
        # For testing, we'll recreate the state manually
        
        print("� Processing corrections...")
        
        # Create a workflow state that represents after validation failure
        from v3.magentic_agents.invoice_workflow import InvoiceWorkflowState
        
        # Simulate the state after validation failure
        validation_failed_state = InvoiceWorkflowState(
            messages=[
                {"role": "user", "content": invalid_invoice},
                {"role": "assistant", "content": "Policy violations found - please fix these issues and resubmit"}
            ],
            user_id=user_id,
            images=None,
            extracted_data={
                "tax_id": "",
                "company_name": "",
                "vendor_name": "KFC",
                "total_amount": 250.0,
                "invoice_date": "2023-01-01",
                "items": "meal",
                "invoice_number": "",
                "currency": "USD"
            },
            policy_violations=[
                "Missing required field: tax_id",
                "Missing required field: company_name", 
                "Meal expense $250.0 exceeds the $200 limit",
                "Invoice is 675 days old, exceeds 30-day policy"
            ],
            user_confirmation=None,
            workflow_stage="awaiting_fixes",
            reimbursement_form=None,
            manager_notification_sent=None
        )
        
        # Process the user correction
        corrected_state = await workflow.handle_user_response(validation_failed_state, correction_input)
        
        print(f"State after correction: {corrected_state.get('workflow_stage')}")
        print(f"Policy violations: {len(corrected_state.get('policy_violations', []))}")
        
        # Check extracted data after correction
        corrected_data = corrected_state.get('extracted_data', {})
        print("� Corrected Data:")
        for key, value in corrected_data.items():
            print(f"  {key}: {value}")
        print()
        
        if corrected_state.get('policy_violations'):
            print("❌ Still have violations after correction:")
            for violation in corrected_state.get('policy_violations', []):
                print(f"  - {violation}")
            return False
        
        print("✅ Step 2 passed - Corrections processed successfully")
        print()
        
        # Step 3: User confirmation
        print("� STEP 3: User Confirmation")
        print("-" * 40)
        
        if corrected_state.get('workflow_stage') == 'awaiting_confirmation':
            print("Workflow is awaiting user confirmation")
            
            # Simulate user confirming
            confirmed_state = await workflow.handle_user_response(corrected_state, "CONFIRM")
            
            print(f"State after confirmation: {confirmed_state.get('workflow_stage')}")
            
            if confirmed_state.get('workflow_stage') == 'completed':
                print("✅ Step 3 passed - User confirmation processed")
                print()
                
                # Step 4: Check final results
                print("📝 STEP 4: Final Results")
                print("-" * 40)
                
                reimbursement_form = confirmed_state.get('reimbursement_form', {})
                if reimbursement_form:
                    print("� Reimbursement Form Generated:")
                    for key, value in reimbursement_form.items():
                        print(f"  {key}: {value}")
                    print()
                
                if confirmed_state.get('manager_notification_sent'):
                    print("✅ Manager notification sent successfully")
                else:
                    print("❌ Manager notification failed")
                    return False
                
                print("🎉 Complete workflow test PASSED!")
                return True
            else:
                print(f"❌ Expected 'completed' state but got: {confirmed_state.get('workflow_stage')}")
                return False
        else:
            print(f"❌ Expected 'awaiting_confirmation' but got: {corrected_state.get('workflow_stage')}")
            return False
        
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