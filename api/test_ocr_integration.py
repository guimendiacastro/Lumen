#!/usr/bin/env python3
"""
Test script for OCR integration

This script tests the OCR functionality by simulating PDF processing
with both text-based and scanned PDFs.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.file_processor import FileProcessor
from app.services.azure_ocr_service import AzureOCRService


async def test_ocr_availability():
    """Test if OCR is properly configured"""
    print("=" * 60)
    print("Testing OCR Availability")
    print("=" * 60)

    is_available = AzureOCRService.is_ocr_available()

    if is_available:
        print("✅ OCR is properly configured")
        print("   Azure Document Intelligence credentials found")
        return True
    else:
        print("⚠️  OCR is NOT configured")
        print("   Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and")
        print("   AZURE_DOCUMENT_INTELLIGENCE_KEY environment variables")
        return False


async def test_text_based_pdf():
    """Test processing a text-based PDF (should use PyPDF2, not OCR)"""
    print("\n" + "=" * 60)
    print("Test 1: Text-Based PDF Processing")
    print("=" * 60)

    # Create a simple text-based PDF for testing
    # In real usage, you would load an actual PDF file
    print("ℹ️  This test requires an actual text-based PDF file")
    print("   Skipping automated test - please test manually by uploading a PDF")
    print("   Expected: PyPDF2 extraction (avg chars/page > 50)")


async def test_scanned_pdf():
    """Test processing a scanned PDF (should trigger OCR)"""
    print("\n" + "=" * 60)
    print("Test 2: Scanned PDF Processing")
    print("=" * 60)

    print("ℹ️  This test requires an actual scanned PDF file")
    print("   Skipping automated test - please test manually by uploading a scanned PDF")
    print("   Expected: OCR extraction triggered (avg chars/page < 50)")


async def test_file_processor_initialization():
    """Test that FileProcessor can be initialized"""
    print("\n" + "=" * 60)
    print("Test 3: FileProcessor Initialization")
    print("=" * 60)

    try:
        # Test that the class exists and methods are accessible
        assert hasattr(FileProcessor, 'extract_text_from_pdf')
        assert hasattr(FileProcessor, 'process_file')
        print("✅ FileProcessor class properly initialized")
        print("   Methods: extract_text_from_pdf, process_file")
        return True
    except Exception as e:
        print(f"❌ FileProcessor initialization failed: {e}")
        return False


async def test_ocr_service_initialization():
    """Test OCR service initialization"""
    print("\n" + "=" * 60)
    print("Test 4: OCR Service Initialization")
    print("=" * 60)

    if not AzureOCRService.is_ocr_available():
        print("⚠️  OCR not configured - skipping service initialization test")
        return False

    try:
        from app.services.azure_ocr_service import get_ocr_service
        service = get_ocr_service()
        print("✅ OCR service initialized successfully")
        print(f"   Service type: {type(service).__name__}")
        return True
    except Exception as e:
        print(f"❌ OCR service initialization failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n" + "🔍 OCR Integration Test Suite" + "\n")

    results = {
        "OCR Availability": await test_ocr_availability(),
        "FileProcessor Init": await test_file_processor_initialization(),
        "OCR Service Init": await test_ocr_service_initialization(),
    }

    # Manual test guidance
    await test_text_based_pdf()
    await test_scanned_pdf()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("\n" + "=" * 60)
    print("Manual Testing Required")
    print("=" * 60)
    print("1. Upload a text-based PDF through LUMEN UI")
    print("   Expected logs: 'Using PyPDF2 extraction'")
    print()
    print("2. Upload a scanned PDF through LUMEN UI")
    print("   Expected logs: 'Attempting OCR extraction...'")
    print("                  'OCR extraction successful'")
    print()
    print("3. Check that text is properly extracted and indexed")
    print("   Query the uploaded files to verify RAG works")
    print("=" * 60)

    # Exit code
    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
