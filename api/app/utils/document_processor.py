# lumen/api/app/utils/document_processor.py
import re


def expand_unchanged_sections(draft: str, current_doc: str) -> str:
    """
    Replace placeholders like '[Sections 1-4 remain unchanged]' with actual content
    from the current document.
    
    Handles patterns like:
    - [Sections 1-4 remain unchanged]
    - [Section 3 remains unchanged]
    - [Sections 1, 2, and 5 remain the same]
    - [Previous sections unchanged]
    """
    if not current_doc or not draft:
        return draft
    
    # Pattern matches various "unchanged" placeholder formats
    patterns = [
        r'\[Sections? [\d\-,\s]+(?:and [\d]+)?\s+(?:remain|remains|stay)s?\s+(?:unchanged|the same)\]',
        r'\[Previous sections?\s+(?:remain\s+)?unchanged\]',
        r'\[All previous sections?\s+(?:remain\s+)?unchanged\]',
        r'\[.*?unchanged.*?\]',  # Catch-all for other variations
    ]
    
    # Check if draft contains any "unchanged" placeholder
    has_placeholder = False
    for pattern in patterns:
        if re.search(pattern, draft, re.IGNORECASE):
            has_placeholder = True
            break
    
    if not has_placeholder:
        return draft
    
    # Extract sections from current document
    # Match markdown headers (## Section or # Section)
    sections = _extract_sections(current_doc)
    
    # Try to intelligently replace placeholders
    result = draft
    
    for pattern in patterns:
        matches = list(re.finditer(pattern, result, re.IGNORECASE))
        
        for match in reversed(matches):  # Process from end to avoid offset issues
            placeholder = match.group(0)
            
            # Try to extract which sections are "unchanged"
            section_refs = _parse_section_refs(placeholder)
            
            if section_refs:
                # Replace with actual sections
                replacement = _build_section_text(sections, section_refs)
            else:
                # Can't parse specific sections, use all sections before this point
                replacement = _get_sections_before_placeholder(current_doc, sections, match.start())
            
            if replacement:
                result = result[:match.start()] + replacement + result[match.end():]
    
    return result


def _extract_sections(doc: str) -> list[dict]:
    """
    Extract all markdown sections with their headers and content.
    Returns list of {'level': int, 'title': str, 'number': str, 'content': str, 'start': int}
    """
    sections = []
    
    # Match markdown headers with optional numbering
    # Supports: ## 1. DEFINITIONS, ### 5.1 Governing Law, etc.
    pattern = r'^(#{1,6})\s+(\d+(?:\.\d+)*\.?)?\s*(.+?)$'
    
    lines = doc.split('\n')
    current_section = None
    
    for i, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            # Save previous section
            if current_section:
                sections.append(current_section)
            
            level = len(match.group(1))
            number = match.group(2) or ''
            title = match.group(3).strip()
            
            current_section = {
                'level': level,
                'number': number.rstrip('.'),
                'title': title,
                'content': line + '\n',
                'start': i,
                'header': line,
            }
        elif current_section:
            current_section['content'] += line + '\n'
    
    # Add last section
    if current_section:
        sections.append(current_section)
    
    return sections


def _parse_section_refs(placeholder: str) -> list[str]:
    """
    Parse section references from placeholder text.
    '[Sections 1-4 remain unchanged]' -> ['1', '2', '3', '4']
    '[Section 3 remains unchanged]' -> ['3']
    """
    # Look for patterns like "1-4", "1, 2, and 5", "3"
    numbers = re.findall(r'\d+', placeholder)
    if not numbers:
        return []
    
    # Check for range (1-4)
    range_match = re.search(r'(\d+)\s*-\s*(\d+)', placeholder)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        return [str(i) for i in range(start, end + 1)]
    
    # Individual numbers
    return numbers


def _build_section_text(sections: list[dict], section_refs: list[str]) -> str:
    """Build text for specified sections."""
    result = []
    for section in sections:
        # Match top-level sections (1, 2, 3) or subsections (5.1, 5.2)
        section_num = section['number'].split('.')[0] if section['number'] else ''
        
        if section_num in section_refs:
            result.append(section['content'].rstrip())
    
    return '\n\n'.join(result) if result else ''


def _get_sections_before_placeholder(doc: str, sections: list[dict], placeholder_pos: int) -> str:
    """
    Get all sections that appear before the placeholder position.
    This is the fallback when we can't parse specific section numbers.
    """
    # Count characters in doc to find which sections are before placeholder
    char_count = 0
    previous_sections = []
    
    for section in sections:
        if char_count < placeholder_pos:
            previous_sections.append(section['content'].rstrip())
            char_count += len(section['content'])
        else:
            break
    
    return '\n\n'.join(previous_sections) if previous_sections else ''