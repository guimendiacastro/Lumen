# lumen/api/test_rag.py
"""
Interactive script to test RAG retrieval quality.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.db import member_session
from app.crypto.vault import decrypt_text
from sentence_transformers import SentenceTransformer

SCHEMA = "mem_01"
KEY_ID = "transit/keys/dev_member"
MODEL = "all-MiniLM-L6-v2"


async def search_chunks(query: str, top_k: int = 15, min_similarity: float = 0.50):
    """Search for relevant chunks."""
    print(f"\n{'='*70}")
    print(f"🔍 QUERY: {query}")
    print(f"{'='*70}\n")
    
    # Generate embedding
    model = SentenceTransformer(MODEL)
    query_embedding = model.encode([query])[0].tolist()
    
    # Search database
    async with member_session(SCHEMA) as session:
        result = await session.execute(text("""
            SELECT 
                chunk_index,
                content_enc,
                metadata,
                1 - (embedding <=> :query_embedding::vector) as similarity
            FROM document_chunks
            WHERE 1 - (embedding <=> :query_embedding::vector) >= :threshold
            ORDER BY 
                (metadata->>'is_summary')::boolean DESC NULLS LAST,
                embedding <=> :query_embedding::vector
            LIMIT :limit
        """), {
            "query_embedding": str(query_embedding),
            "threshold": min_similarity,
            "limit": top_k
        })
        
        rows = result.fetchall()
    
    if not rows:
        print("❌ No results found")
        return
    
    print(f"📊 Found {len(rows)} results\n")
    
    # Display results
    for i, (idx, content_enc, metadata, similarity) in enumerate(rows, 1):
        content = await decrypt_text(KEY_ID, content_enc)
        
        print(f"{'─'*70}")
        print(f"RESULT #{i} | Chunk {idx} | Similarity: {similarity:.4f}")
        
        if metadata:
            print(f"Metadata: {metadata}")
        
        print(f"\nContent Preview:")
        preview = content[:400] if len(content) > 400 else content
        print(preview)
        if len(content) > 400:
            print("...")
        print()


async def interactive_mode():
    """Interactive testing mode."""
    print("\n" + "="*70)
    print("RAG INTERACTIVE TEST MODE")
    print("="*70)
    print("\nCommands:")
    print("  - Enter a query to search")
    print("  - Type 'exit' or 'quit' to exit")
    print("  - Type 'stats' to see database statistics")
    print("="*70 + "\n")
    
    while True:
        try:
            query = input("\n🔍 Enter query (or command): ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['exit', 'quit', 'q']:
                print("👋 Goodbye!")
                break
            
            if query.lower() == 'stats':
                await show_stats()
                continue
            
            # Search
            await search_chunks(query)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


async def show_stats():
    """Show database statistics."""
    async with member_session(SCHEMA) as session:
        # Count chunks
        result = await session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE (metadata->>'is_summary')::boolean = true) as summaries,
                   COUNT(*) FILTER (WHERE metadata->>'content_type' = 'financial') as financial,
                   COUNT(*) FILTER (WHERE metadata->>'content_type' = 'parties') as parties,
                   COUNT(*) FILTER (WHERE metadata->>'content_type' = 'term') as term,
                   AVG(LENGTH(content_enc)) as avg_size
            FROM document_chunks
        """))
        row = result.first()
    
    print(f"\n{'='*70}")
    print("DATABASE STATISTICS")
    print(f"{'='*70}")
    print(f"Total chunks: {row[0]}")
    print(f"  - Summary chunks: {row[1]}")
    print(f"  - Financial chunks: {row[2]}")
    print(f"  - Parties chunks: {row[3]}")
    print(f"  - Term chunks: {row[4]}")
    print(f"Average chunk size (encrypted): {row[5]:.0f} chars")
    print(f"{'='*70}\n")


async def run_preset_queries():
    """Run preset test queries."""
    queries = [
        "Give me a 10-bullet executive summary of this tenancy: parties, address, term, rent, deposit, bills, agent, guarantor, notice rules, and any special conditions",
        "What is the monthly rent amount?",
        "What is the property address?",
        "What is the deposit amount?",
        "Who is the managing agent and their contact details?",
        "What are the notice requirements to terminate the tenancy?",
        "What special conditions apply to this tenancy?",
        "When does the tenancy commence and what is its duration?",
    ]
    
    print("\n" + "="*70)
    print("RUNNING PRESET TEST QUERIES")
    print("="*70)
    
    for i, query in enumerate(queries, 1):
        await search_chunks(query)
        
        if i < len(queries):
            input("\nPress Enter to continue to next query...")


async def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "preset":
            await run_preset_queries()
        elif sys.argv[1] == "stats":
            await show_stats()
        else:
            # Treat as query
            query = " ".join(sys.argv[1:])
            await search_chunks(query)
    else:
        await interactive_mode()


if __name__ == "__main__":
    asyncio.run(main())