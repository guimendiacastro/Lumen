# lumen/api/migrate_rag.py
"""
RAG migration script with improved chunking strategy.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.db import member_session
from app.crypto.vault import encrypt_text, decrypt_text
from app.utils.chunking import (
    chunk_legal_document,
    create_metadata_chunk,
    Chunk
)
import PyPDF2
from sentence_transformers import SentenceTransformer

# Configuration
SCHEMA = "mem_01"
KEY_ID = "transit/keys/dev_member"
PDF_PATH = "/Users/Gui/Downloads/contract.pdf"  # Update with your path
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Chunking parameters
CHUNK_SIZE = 1200  # Characters per chunk
OVERLAP = 200      # Character overlap between chunks
MIN_SIMILARITY_THRESHOLD = 0.50  # Lower threshold for better recall


async def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF."""
    print(f"📄 Extracting text from {pdf_path}...")
    
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page_num, page in enumerate(reader.pages, 1):
            page_text = page.extract_text()
            text += page_text + "\n\n"
            print(f"   Page {page_num}: {len(page_text)} chars")
    
    print(f"✅ Extracted {len(text)} total characters\n")
    return text


async def create_embeddings(chunks: list[Chunk], model_name: str = EMBEDDING_MODEL):
    """Generate embeddings for all chunks."""
    print(f"🧠 Loading embedding model: {model_name}...")
    model = SentenceTransformer(model_name)
    
    print(f"🔢 Generating embeddings for {len(chunks)} chunks...")
    texts = [chunk.content for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    
    print(f"✅ Generated embeddings (shape: {embeddings.shape})\n")
    return embeddings


async def store_chunks_in_db(chunks: list[Chunk], embeddings, schema: str, key_id: str):
    """Store chunks with embeddings in database."""
    print(f"💾 Storing {len(chunks)} chunks in database (schema: {schema})...")
    
    # Create RAG table if it doesn't exist (split into separate commands)
    async with member_session(schema) as session:
        # Create table
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID,
                chunk_index INTEGER NOT NULL,
                content_enc TEXT NOT NULL,
                embedding vector(384),
                metadata JSONB,
                start_char INTEGER,
                end_char INTEGER,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        
        # Create vector index
        await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunk_embedding 
            ON document_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        
        # Create metadata index
        await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_chunk_metadata 
            ON document_chunks USING GIN (metadata)
        """))
        
        await session.commit()
        print("✅ Tables and indexes created/verified\n")
    
    # Insert chunks
    inserted = 0
    async with member_session(schema) as session:
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Encrypt content
            content_enc = await encrypt_text(key_id, chunk.content)
            
            # Convert numpy array to list for Postgres
            embedding_list = embedding.tolist()
            
            # Insert chunk
            await session.execute(text("""
                INSERT INTO document_chunks 
                (chunk_index, content_enc, embedding, metadata, start_char, end_char)
                VALUES (:idx, :content, :embedding::vector, :metadata::jsonb, :start_char, :end_char)
            """), {
                "idx": i,
                "content": content_enc,
                "embedding": str(embedding_list),
                "metadata": str(chunk.metadata),
                "start_char": chunk.start_char,
                "end_char": chunk.end_char
            })
            
            inserted += 1
            if (i + 1) % 10 == 0:
                print(f"   Inserted {i + 1}/{len(chunks)} chunks...")
        
        await session.commit()
    
    print(f"✅ Successfully stored {inserted} chunks in database\n")


async def test_search(schema: str, key_id: str, query: str, top_k: int = 12):
    """Test similarity search."""
    print(f"🔍 Testing search with query: '{query}'")
    print(f"   Retrieving top {top_k} results with threshold >= {MIN_SIMILARITY_THRESHOLD}\n")
    
    # Generate query embedding
    model = SentenceTransformer(EMBEDDING_MODEL)
    query_embedding = model.encode([query])[0].tolist()
    
    # Search
    async with member_session(schema) as session:
        result = await session.execute(text("""
            SELECT 
                chunk_index,
                content_enc,
                metadata,
                1 - (embedding <=> :query_embedding::vector) as similarity
            FROM document_chunks
            WHERE 1 - (embedding <=> :query_embedding::vector) >= :threshold
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :limit
        """), {
            "query_embedding": str(query_embedding),
            "threshold": MIN_SIMILARITY_THRESHOLD,
            "limit": top_k
        })
        
        rows = result.fetchall()
    
    print(f"📊 Found {len(rows)} results:\n")
    
    # Decrypt results
    for row in rows:
        idx, content_enc, metadata, similarity = row
        content = await decrypt_text(key_id, content_enc)
        
        print(f"--- Chunk {idx} (similarity: {similarity:.3f}) ---")
        print(f"Metadata: {metadata}")
        print(f"Content preview: {content[:200]}...")
        print()


async def main():
    """Main migration workflow."""
    print("=" * 70)
    print("RAG MIGRATION - Smart Chunking for Legal Documents")
    print("=" * 70)
    print()
    
    # Step 1: Extract text
    if not os.path.exists(PDF_PATH):
        print(f"❌ Error: PDF not found at {PDF_PATH}")
        return
    
    contract_text = await extract_pdf_text(PDF_PATH)
    
    # Step 2: Create metadata summary chunk (special first chunk)
    print("📋 Creating metadata summary chunk...")
    metadata_chunk = create_metadata_chunk(contract_text)
    print(f"✅ Metadata chunk created ({len(metadata_chunk.content)} chars)\n")
    
    # Step 3: Smart chunking
    print(f"✂️  Chunking document (size={CHUNK_SIZE}, overlap={OVERLAP})...")
    content_chunks = chunk_legal_document(
        contract_text,
        chunk_size=CHUNK_SIZE,
        overlap=OVERLAP
    )
    print(f"✅ Created {len(content_chunks)} content chunks\n")
    
    # Combine metadata chunk + content chunks
    all_chunks = [metadata_chunk] + content_chunks
    
    # Print chunk statistics
    print("📊 Chunk Statistics:")
    print(f"   Total chunks: {len(all_chunks)}")
    print(f"   Average size: {sum(len(c.content) for c in all_chunks) // len(all_chunks)} chars")
    
    # Count chunks with metadata
    financial_chunks = sum(1 for c in all_chunks if c.metadata.get('content_type') == 'financial')
    parties_chunks = sum(1 for c in all_chunks if c.metadata.get('has_parties_info'))
    term_chunks = sum(1 for c in all_chunks if c.metadata.get('has_term_info'))
    
    print(f"   Financial chunks: {financial_chunks}")
    print(f"   Parties chunks: {parties_chunks}")
    print(f"   Term chunks: {term_chunks}")
    print()
    
    # Step 4: Generate embeddings
    embeddings = await create_embeddings(all_chunks, EMBEDDING_MODEL)
    
    # Step 5: Store in database
    await store_chunks_in_db(all_chunks, embeddings, SCHEMA, KEY_ID)
    
    # Step 6: Test searches
    print("=" * 70)
    print("TESTING SEARCH FUNCTIONALITY")
    print("=" * 70)
    print()
    
    test_queries = [
        "Give me a 10-bullet executive summary of this tenancy: parties, address, term, rent, deposit, bills, agent, guarantor, notice rules, and any special conditions",
        "What is the monthly rent amount?",
        "Who is the managing agent?",
        "What are the notice requirements for termination?",
    ]
    
    for query in test_queries:
        await test_search(SCHEMA, KEY_ID, query, top_k=12)
        print("-" * 70)
        print()
    
    print("=" * 70)
    print("✅ MIGRATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())