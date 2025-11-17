#!/usr/bin/env python3
"""
Simple test script for local chunking logic (no Azure dependencies)
"""

import tiktoken


class DocumentChunk:
    """Represents a chunk of text with metadata"""
    def __init__(self, content, chunk_index, token_count, char_start, char_end):
        self.content = content
        self.chunk_index = chunk_index
        self.token_count = token_count
        self.char_start = char_start
        self.char_end = char_end


class LocalChunker:
    """High-performance local text chunker with semantic awareness"""

    def __init__(self, chunk_size=800, chunk_overlap=200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding

    def chunk_text(self, text):
        """Chunk text using semantic boundaries and token-based splitting."""
        chunks = []

        # Split into paragraphs
        paragraphs = text.split('\n\n')

        current_chunk = []
        current_tokens = 0
        char_position = 0
        chunk_start_char = 0
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = self.encoding.encode(para)
            para_token_count = len(para_tokens)

            # If single paragraph is too large, split by sentences
            if para_token_count > self.chunk_size:
                # Save current chunk if exists
                if current_chunk:
                    chunk_text = '\n\n'.join(current_chunk)
                    chunks.append(DocumentChunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        token_count=current_tokens,
                        char_start=chunk_start_char,
                        char_end=char_position
                    ))
                    chunk_index += 1

                # Split large paragraph by sentences
                sentences = self._split_sentences(para)
                sentence_chunk = []
                sentence_tokens = 0
                sentence_start = char_position

                for sentence in sentences:
                    sent_tokens = self.encoding.encode(sentence)
                    sent_token_count = len(sent_tokens)

                    if sentence_tokens + sent_token_count > self.chunk_size and sentence_chunk:
                        # Save sentence chunk
                        chunk_text = ' '.join(sentence_chunk)
                        chunks.append(DocumentChunk(
                            content=chunk_text,
                            chunk_index=chunk_index,
                            token_count=sentence_tokens,
                            char_start=sentence_start,
                            char_end=char_position
                        ))
                        chunk_index += 1

                        # Add overlap from previous chunk
                        overlap_text = self._get_overlap_text(sentence_chunk, self.chunk_overlap)
                        sentence_chunk = [overlap_text] if overlap_text else []
                        sentence_tokens = len(self.encoding.encode(' '.join(sentence_chunk)))
                        sentence_start = char_position

                    sentence_chunk.append(sentence)
                    sentence_tokens += sent_token_count
                    char_position += len(sentence) + 1

                # Save remaining sentences
                if sentence_chunk:
                    chunk_text = ' '.join(sentence_chunk)
                    chunks.append(DocumentChunk(
                        content=chunk_text,
                        chunk_index=chunk_index,
                        token_count=sentence_tokens,
                        char_start=sentence_start,
                        char_end=char_position
                    ))
                    chunk_index += 1

                # Reset for next paragraph
                current_chunk = []
                current_tokens = 0
                chunk_start_char = char_position

            # Normal case: paragraph fits in chunk
            elif current_tokens + para_token_count > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = '\n\n'.join(current_chunk)
                chunks.append(DocumentChunk(
                    content=chunk_text,
                    chunk_index=chunk_index,
                    token_count=current_tokens,
                    char_start=chunk_start_char,
                    char_end=char_position
                ))
                chunk_index += 1

                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                current_chunk = [overlap_text, para] if overlap_text else [para]
                current_tokens = len(self.encoding.encode('\n\n'.join(current_chunk)))
                chunk_start_char = char_position

            else:
                # Add to current chunk
                current_chunk.append(para)
                current_tokens += para_token_count

            char_position += len(para) + 2  # +2 for \n\n

        # Save final chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(DocumentChunk(
                content=chunk_text,
                chunk_index=chunk_index,
                token_count=current_tokens,
                char_start=chunk_start_char,
                char_end=char_position
            ))

        print(f"Chunked text into {len(chunks)} chunks (avg {sum(c.token_count for c in chunks) / len(chunks) if chunks else 0:.0f} tokens/chunk)")
        return chunks

    def _split_sentences(self, text):
        """Split text into sentences using basic punctuation rules"""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_text(self, chunks, overlap_tokens):
        """Get last N tokens from chunks as overlap text"""
        combined = '\n\n'.join(chunks)
        tokens = self.encoding.encode(combined)

        if len(tokens) <= overlap_tokens:
            return combined

        overlap_token_list = tokens[-overlap_tokens:]
        return self.encoding.decode(overlap_token_list)


# Sample test text
sample_text = """
EMPLOYMENT AGREEMENT

This Employment Agreement (the "Agreement") is entered into as of January 1, 2024, by and between TechCorp Inc., a Delaware corporation (the "Company"), and John Smith (the "Employee").

RECITALS

WHEREAS, the Company desires to employ the Employee, and the Employee desires to be employed by the Company, on the terms and conditions set forth in this Agreement.

1. POSITION AND DUTIES

1.1 Position. The Company hereby employs the Employee as Chief Technology Officer, and the Employee hereby accepts such employment, upon the terms and conditions set forth in this Agreement.

1.2 Duties. The Employee shall perform such duties and responsibilities as are customarily associated with the position of Chief Technology Officer, and such other duties as may be assigned to the Employee by the Board of Directors or the Chief Executive Officer from time to time.

2. COMPENSATION

2.1 Base Salary. As compensation for services rendered hereunder, the Company shall pay the Employee a base salary at the annual rate of $250,000, payable in accordance with the Company's standard payroll practices.

2.2 Annual Bonus. The Employee shall be eligible to receive an annual performance bonus targeted at 30% of base salary, subject to achievement of performance objectives established by the Board.

3. BENEFITS

3.1 Employee Benefits. The Employee shall be entitled to participate in all employee benefit plans, practices, and programs maintained by the Company, as in effect from time to time, on a basis which is no less favorable than is provided to other similarly situated executives of the Company.

4. TERMINATION

4.1 Termination for Cause. The Company may terminate the Employee's employment hereunder for Cause at any time upon written notice to the Employee.

4.2 Termination Without Cause. The Company may terminate the Employee's employment hereunder without Cause at any time upon thirty days' written notice to the Employee.
"""

print("\n" + "=" * 80)
print("LOCAL CHUNKING TEST")
print("=" * 80)

chunker = LocalChunker(chunk_size=800, chunk_overlap=200)
print(f"\nInput text length: {len(sample_text)} characters")

chunks = chunker.chunk_text(sample_text)

print(f"\nGenerated {len(chunks)} chunks")
print("\n" + "=" * 80)

for i, chunk in enumerate(chunks):
    print(f"\n--- Chunk {i} ---")
    print(f"Tokens: {chunk.token_count}")
    print(f"Preview: {chunk.content[:150]}...")

print("\n" + "=" * 80)
print("✓ Chunking test completed successfully!")
print("=" * 80 + "\n")
