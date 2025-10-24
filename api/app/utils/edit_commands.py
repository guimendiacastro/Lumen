# lumen/api/app/utils/edit_commands.py
from pydantic import BaseModel, Field
from typing import Literal, List
import re


class EditCommand(BaseModel):
    """A single edit operation to apply to the document."""
    type: Literal["replace", "insert_after", "insert_before", "delete", "append"]
    anchor: str | None = Field(None, description="Unique text to locate the edit position")
    content: str | None = Field(None, description="New content to insert/replace with")
    section_heading: str | None = Field(None, description="Section heading for context")
    
    
class EditPlan(BaseModel):
    """Complete plan of edits to apply to a document."""
    reasoning: str = Field(description="Brief explanation of what changes are being made and why")
    edits: List[EditCommand] = Field(description="Ordered list of edit commands to apply")


def apply_edits(original_doc: str, edit_plan: EditPlan) -> str:
    """
    Apply a series of edit commands to a document.
    Returns the fully edited document.
    """
    result = original_doc
    
    for edit in edit_plan.edits:
        if edit.type == "append":
            # Add to end of document
            result = result.rstrip() + "\n\n" + (edit.content or "")
            
        elif edit.type == "insert_after":
            # Find anchor text and insert after it
            if not edit.anchor:
                continue
            pos = result.find(edit.anchor)
            if pos == -1:
                # Try fuzzy match if exact match fails
                pos = _fuzzy_find(result, edit.anchor)
            if pos != -1:
                insert_pos = pos + len(edit.anchor)
                result = result[:insert_pos] + "\n\n" + (edit.content or "") + result[insert_pos:]
                
        elif edit.type == "insert_before":
            # Find anchor text and insert before it
            if not edit.anchor:
                continue
            pos = result.find(edit.anchor)
            if pos == -1:
                pos = _fuzzy_find(result, edit.anchor)
            if pos != -1:
                result = result[:pos] + (edit.content or "") + "\n\n" + result[pos:]
                
        elif edit.type == "replace":
            # Replace anchor text with new content
            if not edit.anchor:
                continue
            pos = result.find(edit.anchor)
            if pos == -1:
                pos = _fuzzy_find(result, edit.anchor)
            if pos != -1:
                end_pos = pos + len(edit.anchor)
                result = result[:pos] + (edit.content or "") + result[end_pos:]
                
        elif edit.type == "delete":
            # Remove anchor text
            if not edit.anchor:
                continue
            result = result.replace(edit.anchor, "")
    
    return result


def _fuzzy_find(text: str, anchor: str, threshold: int = 20) -> int:
    """
    Fuzzy search for anchor text in document.
    Returns position if found within threshold, -1 otherwise.
    """
    # Simple implementation: try to find first few words
    anchor_words = anchor.split()[:5]
    search_pattern = r'\s+'.join(re.escape(w) for w in anchor_words)
    
    match = re.search(search_pattern, text, re.IGNORECASE)
    return match.start() if match else -1


def generate_edit_system_prompt() -> str:
    """System prompt for edit-based generation."""
    return """You are a legal drafting assistant that generates EDIT COMMANDS, not full documents.

CRITICAL: You must return a JSON object with this exact structure:
{
  "reasoning": "Brief explanation of changes",
  "edits": [
    {
      "type": "replace|insert_after|insert_before|delete|append",
      "anchor": "unique text snippet to locate position (required for all except append)",
      "content": "new content to insert (omit for delete)",
      "section_heading": "## Section Name (for context only)"
    }
  ]
}

RULES:
1. Each edit specifies ONE atomic change
2. "anchor" must be a unique snippet (10-50 chars) from the existing document
3. For "replace": anchor is the text to replace
4. For "insert_after": anchor is text to insert after
5. For "insert_before": anchor is text to insert before
6. For "delete": anchor is text to remove
7. For "append": no anchor needed, adds to end of document
8. Order edits logically (top to bottom of document)
9. NEVER regenerate unchanged content
10. Keep anchors precise but not overly long
11. ALL content must use proper Markdown formatting:
    - Use # for main title, ## for sections, ### for subsections
    - Use **bold** for emphasis on key terms
    - Use numbered lists (1., 2., 3.) or bullet points (- item) where appropriate
    - Use proper paragraph spacing with blank lines between sections

Example:
User: "Add more detail to the Amendment clause"

Good response:
{
  "reasoning": "Adding procedural requirements for amendments",
  "edits": [
    {
      "type": "replace",
      "anchor": "This Agreement may not be amended or modified except in writing signed by both Parties.",
      "content": "This Agreement may not be amended or modified except by a written instrument signed by both Parties. Any proposed amendment must be submitted in writing at least thirty (30) days prior to the proposed effective date. The Parties agree to negotiate any proposed amendments in good faith.",
      "section_heading": "## 6. MISCELLANEOUS"
    }
  ]
}

Bad response (regenerating full sections):
{
  "edits": [
    {
      "type": "replace",
      "anchor": "## 6. MISCELLANEOUS",
      "content": "## 6. MISCELLANEOUS\n\n6.1 Severability...\n\n6.2 Entire Agreement...\n\n6.3 Amendment: [long text]"
    }
  ]
}"""