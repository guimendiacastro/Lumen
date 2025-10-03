# lumen/api/app/utils/chunking.py
"""
Smart chunking for legal documents that preserves semantic structure.
"""
from __future__ import annotations
import re
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a document chunk with metadata."""
    content: str
    metadata: Dict[str, Any]
    start_char: int
    end_char: int


def chunk_legal_document(
    text: str, 
    chunk_size: int = 1200, 
    overlap: int = 200
) -> List[Chunk]:
    """
    Smart chunking for legal documents that preserves section integrity.
    
    Strategy:
    1. Keep major sections together when possible
    2. Split at subsection boundaries if needed
    3. Use sliding window with overlap as last resort
    4. Add metadata to each chunk for better retrieval
    """
    chunks = []
    
    # First, split by major sections (numbered headings like "1. DEFINITIONS")
    section_pattern = r'\n(?=\d+\.\s+[A-Z])'
    sections = re.split(section_pattern, text)
    
    current_pos = 0
    
    for section in sections:
        if not section.strip():
            continue
            
        section_start = text.find(section, current_pos)
        
        # If section is small enough, keep it whole
        if len(section) <= chunk_size:
            chunks.append(Chunk(
                content=section,
                metadata=extract_section_info(section),
                start_char=section_start,
                end_char=section_start + len(section)
            ))
        else:
            # Split long sections at subsection boundaries (e.g., "1.1", "1.2")
            subsection_pattern = r'\n(?=\d+\.\d+\.)'
            subsections = re.split(subsection_pattern, section)
            
            subsection_pos = section_start
            for subsection in subsections:
                if not subsection.strip():
                    continue
                    
                if len(subsection) <= chunk_size:
                    chunks.append(Chunk(
                        content=subsection,
                        metadata=extract_section_info(subsection),
                        start_char=subsection_pos,
                        end_char=subsection_pos + len(subsection)
                    ))
                else:
                    # Last resort: split by paragraphs with overlap
                    para_chunks = sliding_window_chunk(
                        subsection, 
                        chunk_size, 
                        overlap,
                        start_offset=subsection_pos
                    )
                    chunks.extend(para_chunks)
                
                subsection_pos += len(subsection)
        
        current_pos = section_start + len(section)
    
    return chunks


def extract_section_info(text: str) -> Dict[str, Any]:
    """
    Extract metadata from chunk for better retrieval.
    Returns dict with section info and content tags.
    """
    metadata = {}
    
    # Extract section number and title
    title_match = re.match(r'(\d+(?:\.\d+)?)\.\s+([A-Z][A-Z\s&]+)', text)
    if title_match:
        metadata['section_num'] = title_match.group(1)
        metadata['section_title'] = title_match.group(2).strip()
    
    # Tag content type for better filtering
    lower_text = text.lower()
    
    if any(word in lower_text for word in ['rent', 'payment', '£', '$', 'deposit', 'price']):
        metadata['content_type'] = 'financial'
    
    if any(word in lower_text for word in ['landlord', 'tenant', 'party', 'parties', 'guarantor']):
        if 'content_type' not in metadata:
            metadata['content_type'] = 'parties'
        metadata['has_parties_info'] = True
    
    if any(word in lower_text for word in ['term', 'duration', 'commence', 'expire', 'notice']):
        if 'content_type' not in metadata:
            metadata['content_type'] = 'term'
        metadata['has_term_info'] = True
    
    if any(word in lower_text for word in ['address', 'property', 'premises', 'located']):
        metadata['has_address_info'] = True
    
    if any(word in lower_text for word in ['special', 'additional', 'condition']):
        metadata['has_special_conditions'] = True
    
    # Extract any monetary amounts
    money_pattern = r'£([\d,]+(?:\.\d{2})?)'
    amounts = re.findall(money_pattern, text)
    if amounts:
        metadata['contains_amounts'] = [f"£{amt}" for amt in amounts]
    
    return metadata


def sliding_window_chunk(
    text: str, 
    chunk_size: int, 
    overlap: int,
    start_offset: int = 0
) -> List[Chunk]:
    """
    Split text using sliding window with overlap.
    Tries to break at paragraph boundaries.
    """
    chunks = []
    paragraphs = text.split('\n\n')
    
    current_chunk = ""
    current_start = start_offset
    
    for para in paragraphs:
        # Would adding this paragraph exceed chunk size?
        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            # Save current chunk
            chunks.append(Chunk(
                content=current_chunk.strip(),
                metadata=extract_section_info(current_chunk),
                start_char=current_start,
                end_char=current_start + len(current_chunk)
            ))
            
            # Start new chunk with overlap
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + "\n\n" + para
            current_start = current_start + len(current_chunk) - len(overlap_text) - len(para) - 2
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append(Chunk(
            content=current_chunk.strip(),
            metadata=extract_section_info(current_chunk),
            start_char=current_start,
            end_char=current_start + len(current_chunk)
        ))
    
    return chunks


def create_metadata_chunk(contract_text: str) -> Chunk:
    """
    Create a special metadata/summary chunk that contains extracted key facts.
    This chunk should be indexed first and will be retrieved for summary queries.
    """
    metadata = {
        'parties': extract_parties(contract_text),
        'property_address': extract_address(contract_text),
        'rent': extract_rent(contract_text),
        'deposit': extract_deposit(contract_text),
        'term': extract_term(contract_text),
        'start_date': extract_start_date(contract_text),
        'agent': extract_agent(contract_text),
        'notice_rules': extract_notice_rules(contract_text),
    }
    
    # Format as searchable text
    summary = f"""=== TENANCY AGREEMENT SUMMARY (METADATA) ===

PARTIES:
Landlord: {metadata['parties'].get('landlord', 'Not specified')}
Tenant: {metadata['parties'].get('tenant', 'Not specified')}
Guarantor: {metadata['parties'].get('guarantor', 'Not specified')}

PROPERTY:
Address: {metadata['property_address']}

FINANCIAL TERMS:
Monthly Rent: {metadata['rent']}
Deposit Amount: {metadata['deposit']}

TERM:
Duration: {metadata['term']}
Commencement Date: {metadata['start_date']}

AGENT:
{metadata['agent']}

NOTICE REQUIREMENTS:
{metadata['notice_rules']}

=== END METADATA SUMMARY ===

Note: This is an auto-generated summary. Full legal text available in subsequent chunks.
"""
    
    return Chunk(
        content=summary,
        metadata={
            'is_summary': True,
            'content_type': 'metadata_summary',
            'section_title': 'DOCUMENT SUMMARY'
        },
        start_char=0,
        end_char=0
    )


# Extraction helpers
def extract_parties(text: str) -> Dict[str, str]:
    """Extract party information."""
    parties = {}
    
    # Look for "The Landlord:" definition
    landlord_match = re.search(r'The Landlord:\s*\n\s*(.+?)(?=\n\s*The\s+(?:Tenant|Guarantor))', text, re.DOTALL)
    if landlord_match:
        parties['landlord'] = landlord_match.group(1).strip()[:200]
    
    # Look for "The Tenant:" definition
    tenant_match = re.search(r'The Tenant:\s*\n\s*(.+?)(?=\n\s*The\s+(?:Guarantor|Landlord))', text, re.DOTALL)
    if tenant_match:
        parties['tenant'] = tenant_match.group(1).strip()[:200]
    
    # Look for "The Guarantor:" definition
    guarantor_match = re.search(r'The Guarantor:\s*\n\s*(.+?)(?=\n\s*The\s+(?:Landlord|Property))', text, re.DOTALL)
    if guarantor_match:
        parties['guarantor'] = guarantor_match.group(1).strip()[:200]
    
    return parties


def extract_address(text: str) -> str:
    """Extract property address."""
    # Look for "The Property:" definition
    property_match = re.search(r'The Property:\s*\n\s*(.+?)(?=\n\s*The\s+(?:Lease|Contents)|Doc ID)', text, re.DOTALL)
    if property_match:
        address = property_match.group(1).strip()
        # Clean up
        address = re.sub(r'\s+', ' ', address)
        return address[:300]
    
    # Fallback: look for UK postcode pattern
    postcode_pattern = r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})'
    postcode_match = re.search(postcode_pattern, text)
    if postcode_match:
        # Extract surrounding context
        start = max(0, postcode_match.start() - 150)
        end = min(len(text), postcode_match.end() + 50)
        context = text[start:end]
        return context.strip()
    
    return "Not specified in extracted content"


def extract_rent(text: str) -> str:
    """Extract monthly rent amount."""
    patterns = [
        r'Rent[:\s]+£([\d,]+(?:\.\d{2})?)\s+per\s+(?:calendar\s+)?month',
        r'monthly\s+rent[:\s]+£([\d,]+(?:\.\d{2})?)',
        r'£([\d,]+(?:\.\d{2})?)\s+pcm',
        r'sum of £([\d,]+(?:\.\d{2})?)\s+per month',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"£{match.group(1)} per month"
    
    return "Not specified in extracted content"


def extract_deposit(text: str) -> str:
    """Extract deposit amount."""
    patterns = [
        r'Deposit[:\s]+£([\d,]+(?:\.\d{2})?)',
        r'deposit of £([\d,]+(?:\.\d{2})?)',
        r'security deposit[:\s]+£([\d,]+(?:\.\d{2})?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"£{match.group(1)}"
    
    return "Not specified in extracted content"


def extract_term(text: str) -> str:
    """Extract tenancy term/duration."""
    patterns = [
        r'Initial Fixed Term[:\s]+(\d+)\s+(month|year)s?',
        r'term of (\d+)\s+(month|year)s?',
        r'(\d+)[ -](month|year)\s+tenancy',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} {match.group(2)}(s)"
    
    return "Not specified in extracted content"


def extract_start_date(text: str) -> str:
    """Extract commencement date."""
    # UK date formats: 15th October 2026, 15/10/2026, 15-10-2026
    patterns = [
        r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return "Not specified in extracted content"


def extract_agent(text: str) -> str:
    """Extract managing agent information."""
    agent_match = re.search(
        r'The Landlord\'?s Agent:\s*\n\s*(.+?)(?=\n\s*The\s+(?:Property|Lease)|Doc ID)', 
        text, 
        re.DOTALL
    )
    if agent_match:
        agent = agent_match.group(1).strip()
        agent = re.sub(r'\s+', ' ', agent)
        return agent[:250]
    
    return "Not specified in extracted content"


def extract_notice_rules(text: str) -> str:
    """Extract notice period requirements."""
    notice_section = re.search(
        r'(?:notice|termination).*?tenant must.*?(\d+)\s+month',
        text,
        re.IGNORECASE | re.DOTALL
    )
    
    if notice_section:
        # Extract broader context
        start = max(0, notice_section.start() - 100)
        end = min(len(text), notice_section.end() + 200)
        context = text[start:end]
        return re.sub(r'\s+', ' ', context.strip())[:300]
    
    return "Not specified in extracted content"


def expand_query_for_summary(query: str) -> str:
    """
    Expand query terms when user asks for summary/overview.
    This increases recall by adding related terms.
    """
    lower_query = query.lower()
    
    # Check if this is a summary-type query
    summary_indicators = ['summary', 'executive', 'overview', 'bullet', 'key terms', 'main points']
    
    if any(indicator in lower_query for indicator in summary_indicators):
        # Add comprehensive search terms
        expansion_terms = [
            "parties", "landlord", "tenant", "guarantor",
            "property", "address", "premises",
            "rent", "payment", "monthly", "deposit",
            "term", "duration", "commencement", "start date",
            "notice", "termination", "ending",
            "agent", "managing agent",
            "special conditions", "additional clauses"
        ]
        
        expanded = query + " " + " ".join(expansion_terms)
        return expanded
    
    return query