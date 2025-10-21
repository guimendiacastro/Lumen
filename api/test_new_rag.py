# lumen/api/test_new_rag.py
"""
Test script for new RAG system
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.rag_service import get_rag_service


async def test_rag():
    """Test the new RAG system"""
    print("="*70)
    print("Testing New RAG System")
    print("="*70)
    
    rag_service = get_rag_service()
    
    # Test document
    test_text = """
    This is a test tenancy agreement.
    
    The monthly rent is £1,500.
    The landlord is John Smith.
    The tenant is Jane Doe.
    The property is located at 123 Main Street, London.
    
    The tenancy starts on January 1, 2024 and ends on December 31, 2024.
    A deposit of £3,000 is required.
    """
    
    test_file_id = "test_file_123"
    
    # Test 1: Index document
    print("\n[TEST 1] Indexing document...")
    try:
        chunk_count = await rag_service.index_document(
            file_id=test_file_id,
            text=test_text,
            metadata={"filename": "test.txt"}
        )
        print(f"✅ Indexed {chunk_count} chunks")
    except Exception as e:
        print(f"❌ Indexing failed: {e}")
        return
    
    # Test 2: Retrieve
    print("\n[TEST 2] Testing retrieval...")
    queries = [
        "What is the monthly rent?",
        "Who is the landlord?",
        "What is the deposit amount?",
    ]
    
    for query in queries:
        print(f"\nQuery: {query}")
        try:
            chunks = await rag_service.retrieve(
                file_id=test_file_id,
                query=query,
                top_k=3
            )
            print(f"Retrieved {len(chunks)} chunks:")
            for i, chunk in enumerate(chunks, 1):
                print(f"  {i}. Score: {chunk.score:.3f}")
                print(f"     Text: {chunk.text[:100]}...")
        except Exception as e:
            print(f"❌ Retrieval failed: {e}")
    
    # Test 3: Cleanup
    print("\n[TEST 3] Cleaning up...")
    try:
        await rag_service.delete_file_index(test_file_id)
        print("✅ Cleanup successful")
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
    
    print("\n" + "="*70)
    print("Testing Complete!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(test_rag())