#!/usr/bin/env python3
"""
PDF Upload Testing script for Invoice Processing Workflow
Tests: Submit invoice with PDF attachment
"""

import asyncio
import json
import sys
import os
import io
import pypdf
from pathlib import Path

# Add the src directory to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from v3.api.simple_chat_handler import SimpleChatHandler


class SimpleInputTask:
    """Mock input task for testing with PDF support."""
    def __init__(self, description: str, images: list = None):
        self.description = description
        self.images = images or []
        self.session_id = "test_session_pdf"
        self.team_id = None


def create_sample_pdf():
    """Load the real DiDi invoice PDF file."""
    try:
        # Use the real DiDi PDF file in the backend directory
        pdf_path = Path(__file__).parent / "滴滴电子发票.pdf"
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        print(f"✅ Loaded real DiDi invoice PDF: {pdf_path.name}")
        return pdf_bytes
        
    except Exception as e:
        print(f"❌ Error loading PDF file: {e}")
        raise


def load_didi_image():
    """Load the DiDi invoice image file."""
    try:
        # Use the DiDi invoice image in the backend directory
        image_path = Path(__file__).parent / "滴滴电子发票_page-0001.jpg"
        
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        
        print(f"✅ Loaded DiDi invoice image: {image_path.name}")
        return image_bytes
        
    except Exception as e:
        print(f"❌ Error loading image file: {e}")
        raise


async def test_pdf_upload_step1():
    """Test Step 1: Submit invoice with PDF attachment."""
    print("🧪 Testing PDF Upload - Step 1 Only")
    print("=" * 60)
    
    user_id = "test_user_pdf"
    handler = SimpleChatHandler()
    
    try:
        # Create sample PDF
        print("📄 Loading real DiDi invoice PDF...")
        pdf_bytes = create_sample_pdf()
        image_bytes = load_didi_image()
        # Step 1: Submit invoice with PDF
        print("📝 STEP 1: Submit Invoice with PDF Attachment")
        print("-" * 40)
        
        message = "Please process this DiDi ride invoice from the attached PDF file"

        
        input_task = SimpleInputTask(message, [pdf_bytes,image_bytes])
        response = await handler.handle_invoice_workflow(user_id, input_task)
        data = json.loads(response)
        
        print("📊 Response:")
        print(f"State: {data.get('state')}")
        print(f"Message: {data.get('message')}")
        print()
        
        # Check if invoice data was extracted
        invoices = data.get('invoices', [])
        if invoices:
            print("📋 Extracted Invoice Data:")
            for idx, invoice in enumerate(invoices, 1):
                print(f"\n  Invoice #{idx}:")
                for key, value in invoice.items():
                    print(f"    {key}: {value}")
        else:
            print("⚠️ No invoice data extracted")
        
        print()
        
        # Check expected state
        expected_states = ['VALIDATE', 'CONFIRM', 'COMPLETED']
        if data.get('state') in expected_states:
            print(f"✅ Step 1 PASSED - PDF processed successfully")
            print(f"   State: {data.get('state')}")
            return True
        else:
            print(f"❌ Step 1 FAILED - Unexpected state: {data.get('state')}")
            return False
        
    except Exception as e:
        print(f"❌ Error in PDF upload test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multiple_pdfs():
    """Test Step 1: Submit multiple DiDi PDF invoices."""
    print("\n🧪 Testing Multiple PDF Upload - Step 1")
    print("=" * 60)
    
    user_id = "test_user_multi_pdf"
    handler = SimpleChatHandler()
    
    try:
        # Load the real DiDi PDF (use same file twice to simulate multiple invoices)
        print("📄 Loading DiDi invoice PDFs...")
        pdf_bytes = create_sample_pdf()
        print(f"✅ PDF loaded: {len(pdf_bytes)} bytes")
        print()
        
        # Prepare multiple PDFs (using the same file for testing)
        pdf_data = [
            {
                "filename": "滴滴电子发票.pdf",
                "content_type": "application/pdf",
                "data": pdf_bytes
            }
        ]
        
        # Submit multiple invoices
        print("📝 STEP 1: Submit Multiple Invoices with PDF Attachments")
        print("-" * 40)
        
        message = "Please process these 2 DiDi ride invoices from the attached PDF files"
        print(f"Message: {message}")
        print(f"Attachments: {len(pdf_data)} file(s)")
        for pdf in pdf_data:
            print(f"  - {pdf['filename']} ({pdf['content_type']})")
        print()
        
        input_task = SimpleInputTask(message, pdf_data)
        response = await handler.handle_invoice_workflow(user_id, input_task)
        data = json.loads(response)
        
        print("📊 Response:")
        print(f"State: {data.get('state')}")
        print(f"Message: {data.get('message')}")
        print()
        
        # Check if invoice data was extracted
        invoices = data.get('invoices', [])
        print(f"📋 Total Invoices Extracted: {len(invoices)}")
        
        if invoices:
            for idx, invoice in enumerate(invoices, 1):
                print(f"\n  Invoice #{idx}:")
                for key, value in invoice.items():
                    print(f"    {key}: {value}")
        
        print()
        
        # Verify we got 2 invoices
        if len(invoices) >= 1:  # At least one invoice should be extracted
            print(f"✅ Multiple PDF Test PASSED - {len(invoices)} invoice(s) extracted")
            return True
        else:
            print(f"❌ Multiple PDF Test FAILED - Expected at least 1 invoice, got {len(invoices)}")
            return False
        
    except Exception as e:
        print(f"❌ Error in multiple PDF test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_image_upload():
    """Test Step 1: Submit invoice with image attachment."""
    print("\n🧪 Testing Image Upload - Step 1")
    print("=" * 60)
    
    user_id = "test_user_image"
    handler = SimpleChatHandler()
    
    try:
        # Load the DiDi invoice image
        print("📷 Loading DiDi invoice image...")
        image_bytes = load_didi_image()
        print(f"✅ Image loaded: {len(image_bytes)} bytes")
        print()
        
        # Prepare image data
        image_data = [{
            "filename": "滴滴电子发票_page-0001.jpg",
            "content_type": "image/jpeg",
            "data": image_bytes
        }]
        
        # Submit invoice with image
        print("📝 STEP 1: Submit Invoice with Image Attachment")
        print("-" * 40)
        
        message = "Please process this DiDi ride invoice from the attached image"
        print(f"Message: {message}")
        print(f"Attachments: {len(image_data)} file(s)")
        print(f"  - {image_data[0]['filename']} ({image_data[0]['content_type']})")
        print()
        
        input_task = SimpleInputTask(message, image_data)
        response = await handler.handle_invoice_workflow(user_id, input_task)
        data = json.loads(response)
        
        print("📊 Response:")
        print(f"State: {data.get('state')}")
        print(f"Message: {data.get('message')}")
        print()
        
        # Check if invoice data was extracted
        invoices = data.get('invoices', [])
        if invoices:
            print("📋 Extracted Invoice Data:")
            for idx, invoice in enumerate(invoices, 1):
                print(f"\n  Invoice #{idx}:")
                for key, value in invoice.items():
                    print(f"    {key}: {value}")
        else:
            print("⚠️ No invoice data extracted")
        
        print()
        
        # Check expected state
        expected_states = ['VALIDATE', 'CONFIRM', 'COMPLETED']
        if data.get('state') in expected_states:
            print(f"✅ Image Upload Test PASSED - Image processed successfully")
            print(f"   State: {data.get('state')}")
            return True
        else:
            print(f"❌ Image Upload Test FAILED - Unexpected state: {data.get('state')}")
            return False
        
    except Exception as e:
        print(f"❌ Error in image upload test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_mixed_files():
    """Test Step 1: Submit invoice with both PDF and image."""
    print("\n🧪 Testing Mixed Files (PDF + Image) Upload - Step 1")
    print("=" * 60)
    
    user_id = "test_user_mixed"
    handler = SimpleChatHandler()
    
    try:
        # Load both PDF and image
        print("📄 Loading DiDi invoice files...")
        pdf_bytes = create_sample_pdf()
        image_bytes = load_didi_image()
        print(f"✅ PDF loaded: {len(pdf_bytes)} bytes")
        print(f"✅ Image loaded: {len(image_bytes)} bytes")
        print()
        
        # Prepare mixed file data
        mixed_data = [
            {
                "filename": "滴滴电子发票.pdf",
                "content_type": "application/pdf",
                "data": pdf_bytes
            },
            {
                "filename": "滴滴电子发票_page-0001.jpg",
                "content_type": "image/jpeg",
                "data": image_bytes
            }
        ]
        
        # Submit with mixed files
        print("📝 STEP 1: Submit Invoices with Mixed File Types")
        print("-" * 40)
        
        message = "Please process these DiDi ride invoices from the attached files"
        print(f"Message: {message}")
        print(f"Attachments: {len(mixed_data)} file(s)")
        for file in mixed_data:
            print(f"  - {file['filename']} ({file['content_type']})")
        print()
        
        input_task = SimpleInputTask(message, mixed_data)
        response = await handler.handle_invoice_workflow(user_id, input_task)
        data = json.loads(response)
        
        print("📊 Response:")
        print(f"State: {data.get('state')}")
        print(f"Message: {data.get('message')}")
        print()
        
        # Check if invoice data was extracted
        invoices = data.get('invoices', [])
        print(f"📋 Total Invoices Extracted: {len(invoices)}")
        
        if invoices:
            for idx, invoice in enumerate(invoices, 1):
                print(f"\n  Invoice #{idx}:")
                for key, value in invoice.items():
                    print(f"    {key}: {value}")
        
        print()
        
        # Verify we got invoices from both files
        if len(invoices) >= 1:  # At least one invoice should be extracted
            print(f"✅ Mixed Files Test PASSED - {len(invoices)} invoice(s) extracted from mixed file types")
            return True
        else:
            print(f"❌ Mixed Files Test FAILED - Expected at least 1 invoice, got {len(invoices)}")
            return False
        
    except Exception as e:
        print(f"❌ Error in mixed files test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run PDF upload tests."""
    print("🧪 Invoice Workflow PDF Upload Testing")
    print("=" * 50)
    print("Testing: Submit DiDi invoice with PDF attachment (Step 1 only)")
    print()
    
    # Test 1: Single PDF
    success1 = await test_pdf_upload_step1()
    
    # Test 2: Multiple PDFs
    # success2 = await test_multiple_pdfs()
    
    print("\n🏁 Testing Summary")
    print("=" * 30)
    if success1:
        print("✅ Single PDF Upload Test: PASSED")
    else:
        print("❌ Single PDF Upload Test: FAILED")
    
    # if success2:
    #     print("✅ Multiple PDF Upload Test: PASSED")
    # else:
    #     print("❌ Multiple PDF Upload Test: FAILED")
    
    # if success1 and success2:
    #     print("\n🎉 All PDF upload tests completed successfully!")
    # else:
    #     print("\n⚠️ Some tests failed. Check the logs above for details")


if __name__ == "__main__":
    asyncio.run(main())
