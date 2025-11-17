#!/usr/bin/env python3
"""
Test script for local chunking with Azure RAG service
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.azure_rag_service import LocalChunker


def test_chunker():
    """Test the local chunker with sample text"""
    chunker = LocalChunker(chunk_size=800, chunk_overlap=200)

    # Sample legal document text
    sample_text = """
EMPLOYMENT AGREEMENT

This Employment Agreement (the "Agreement") is entered into as of January 1, 2024, by and between TechCorp Inc., a Delaware corporation (the "Company"), and John Smith (the "Employee").

RECITALS

WHEREAS, the Company desires to employ the Employee, and the Employee desires to be employed by the Company, on the terms and conditions set forth in this Agreement.

NOW, THEREFORE, in consideration of the mutual covenants and agreements hereinafter set forth and for other good and valuable consideration, the receipt and sufficiency of which are hereby acknowledged, the parties agree as follows:

1. POSITION AND DUTIES

1.1 Position. The Company hereby employs the Employee as Chief Technology Officer, and the Employee hereby accepts such employment, upon the terms and conditions set forth in this Agreement.

1.2 Duties. The Employee shall perform such duties and responsibilities as are customarily associated with the position of Chief Technology Officer, and such other duties as may be assigned to the Employee by the Board of Directors or the Chief Executive Officer from time to time.

1.3 Devotion of Time. During the term of this Agreement, the Employee shall devote substantially all of the Employee's business time, attention, skill, and efforts to the faithful performance of the Employee's duties hereunder.

2. COMPENSATION

2.1 Base Salary. As compensation for services rendered hereunder, the Company shall pay the Employee a base salary at the annual rate of $250,000, payable in accordance with the Company's standard payroll practices.

2.2 Annual Bonus. The Employee shall be eligible to receive an annual performance bonus targeted at 30% of base salary, subject to achievement of performance objectives established by the Board.

2.3 Equity Compensation. The Employee shall be granted stock options to purchase 100,000 shares of the Company's common stock, subject to the terms of the Company's Stock Option Plan.

3. BENEFITS

3.1 Employee Benefits. The Employee shall be entitled to participate in all employee benefit plans, practices, and programs maintained by the Company, as in effect from time to time, on a basis which is no less favorable than is provided to other similarly situated executives of the Company.

3.2 Vacation. The Employee shall be entitled to four weeks of paid vacation per year, to be taken at such times as are mutually agreed upon.

4. TERMINATION

4.1 Termination for Cause. The Company may terminate the Employee's employment hereunder for Cause at any time upon written notice to the Employee.

4.2 Termination Without Cause. The Company may terminate the Employee's employment hereunder without Cause at any time upon thirty days' written notice to the Employee.

4.3 Severance. In the event of termination without Cause, the Employee shall be entitled to receive severance pay equal to six months of base salary, payable in accordance with the Company's standard payroll practices.

5. CONFIDENTIALITY AND NON-COMPETE

5.1 Confidential Information. The Employee acknowledges that during the course of employment, the Employee will have access to and become familiar with confidential information belonging to the Company.

5.2 Non-Disclosure. The Employee agrees that the Employee will not, at any time during or after the term of employment, disclose any Confidential Information to any person or entity for any reason or purpose whatsoever.

5.3 Non-Compete. During the term of employment and for a period of twelve months thereafter, the Employee shall not directly or indirectly engage in any business that competes with the Company.

6. GENERAL PROVISIONS

6.1 Governing Law. This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware.

6.2 Entire Agreement. This Agreement constitutes the entire agreement between the parties with respect to the subject matter hereof and supersedes all prior agreements and understandings.

6.3 Amendment. This Agreement may not be amended or modified except by a written instrument signed by both parties.

IN WITNESS WHEREOF, the parties have executed this Agreement as of the date first written above.

TECHCORP INC.

By: _______________________
Name: Jane Doe
Title: Chief Executive Officer

EMPLOYEE

_______________________
John Smith
"""

    print("Testing Local Chunker")
    print("=" * 80)
    print(f"\nInput text length: {len(sample_text)} characters")

    # Chunk the text
    chunks = chunker.chunk_text(sample_text)

    print(f"\nGenerated {len(chunks)} chunks")
    print(f"Average chunk size: {sum(c.token_count for c in chunks) / len(chunks):.1f} tokens")
    print("\n" + "=" * 80)

    # Display chunk details
    for i, chunk in enumerate(chunks):
        print(f"\n--- Chunk {i} ---")
        print(f"Tokens: {chunk.token_count}")
        print(f"Char range: {chunk.char_start}-{chunk.char_end}")
        print(f"Preview: {chunk.content[:200]}...")
        print()

    # Verify overlap between consecutive chunks
    print("\n" + "=" * 80)
    print("Overlap Analysis:")
    for i in range(len(chunks) - 1):
        chunk1_end = chunks[i].content[-100:]
        chunk2_start = chunks[i+1].content[:100]

        # Check if there's any overlap
        has_overlap = any(word in chunk2_start for word in chunk1_end.split()[-10:])
        print(f"Chunks {i} → {i+1}: {'✓ Has overlap' if has_overlap else '✗ No overlap'}")

    print("\n" + "=" * 80)
    print("✓ Chunking test completed successfully!")

    return chunks


async def test_full_rag_service():
    """Test the full RAG service (requires Azure credentials)"""
    from app.services.azure_rag_service import get_rag_service

    print("\n" + "=" * 80)
    print("Testing Full RAG Service")
    print("=" * 80)

    try:
        rag_service = get_rag_service()
        print("✓ RAG service initialized successfully")

        # Test with sample document
        sample_content = "This is a test document for the RAG system. It contains multiple sentences. Each sentence provides some information. The chunker should split this appropriately."

        print("\nUploading test document...")
        result = await rag_service.upload_document(
            file_id="test-doc-001",
            org_id="test-org",
            user_id="test-user",
            content=sample_content,
            filename="test.txt"
        )

        print(f"✓ Upload complete: {result['chunk_count']} chunks indexed")
        print(f"  Note: {result['note']}")

        print("\nSearching for content...")
        search_results = await rag_service.search_documents(
            query="test document information",
            org_id="test-org",
            user_id="test-user",
            file_ids=["test-doc-001"],
            top_k=3
        )

        print(f"✓ Search complete: {len(search_results)} results found")
        for i, result in enumerate(search_results):
            print(f"\n  Result {i+1}:")
            print(f"    Score: {result['score']:.4f}")
            print(f"    Content: {result['content'][:100]}...")

        # Clean up
        print("\nCleaning up test document...")
        await rag_service.delete_document(
            file_id="test-doc-001",
            org_id="test-org",
            user_id="test-user"
        )
        print("✓ Test document deleted")

        print("\n" + "=" * 80)
        print("✓ Full RAG service test completed successfully!")

    except Exception as e:
        print(f"\n✗ RAG service test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("LOCAL CHUNKING TEST SUITE")
    print("=" * 80)

    # Test 1: Local chunker only
    test_chunker()

    # Test 2: Full RAG service (if credentials available)
    if os.getenv("AZURE_SEARCH_ENDPOINT"):
        print("\n\nAzure credentials detected. Running full RAG service test...")
        asyncio.run(test_full_rag_service())
    else:
        print("\n\nSkipping full RAG service test (no Azure credentials)")
        print("To test with Azure, set these environment variables:")
        print("  - AZURE_SEARCH_ENDPOINT")
        print("  - AZURE_SEARCH_KEY")
        print("  - AZURE_OPENAI_EMBEDDING_ENDPOINT")
        print("  - AZURE_OPENAI_EMBEDDING_KEY")
        print("  - AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

    print("\n" + "=" * 80)
    print("All tests completed!")
    print("=" * 80 + "\n")
