# lumen/api/app/utils/validation.py
import re
from typing import List


class ValidationIssue:
    """Represents a validation problem found in generated content."""
    def __init__(self, severity: str, message: str, location: str = ""):
        self.severity = severity  # "error", "warning", "info"
        self.message = message
        self.location = location


def validate_completeness(generated: str, original: str | None = None) -> List[ValidationIssue]:
    """
    Validate that generated document is complete and doesn't contain placeholders.
    Returns list of issues found.
    """
    issues: List[ValidationIssue] = []

    # Check for placeholder patterns (skip typical signature blocks later)
    placeholder_patterns = [
        (r'\[.*?(?:remain|unchanged|same|previous).*?\]', "Placeholder found"),
        (r'\.\.\.\s*\(.*?(?:remain|unchanged|same).*?\)', "Ellipsis placeholder found"),
        (r'(?:content|section|text)\s+(?:remains?|unchanged)', "Incomplete section reference"),
        (r'\[INSERT\s+.*?\]', "Template placeholder not filled"),
        (r'\[TODO.*?\]', "TODO placeholder found"),
    ]

    for pattern, msg in placeholder_patterns:
        for match in re.finditer(pattern, generated, re.IGNORECASE):
            context = _extract_context(generated, match.start(), match.end())
            issues.append(ValidationIssue(
                severity="error",
                message=f"{msg}: '{match.group()}'",
                location=context
            ))

    # Detect long underscore lines often used as blanks; allow signature blocks.
    blank_pattern = r'_{3,}'
    for match in re.finditer(blank_pattern, generated):
        context_before = generated[max(0, match.start() - 100):match.start()].lower()
        context_after = generated[match.end():min(len(generated), match.end() + 100)].lower()

        signature_keywords = ['signature', 'by:', 'name:', 'title:', 'date:', 'witness', 'signed']
        is_signature = any(kw in context_before or kw in context_after for kw in signature_keywords)

        if not is_signature:
            context = _extract_context(generated, match.start(), match.end())
            issues.append(ValidationIssue(
                severity="error",
                message=f"Blank placeholder line: '{match.group()}'",
                location=context
            ))

    # Truncation markers
    truncation_patterns = [
        r'\.\.\.$',                    # Ends with ellipsis
        r'\[cont(?:inued|\.)\]',       # [continued] marker
        r'(?:^|\n)\.\.\.(?:\n|$)',     # Standalone ellipsis line
    ]
    for pattern in truncation_patterns:
        if re.search(pattern, generated, re.IGNORECASE | re.MULTILINE):
            issues.append(ValidationIssue(
                severity="error",
                message="Document appears truncated or incomplete",
                location="End of document"
            ))
            break

    # Compare section structure against original when we have one
    if original and not _is_placeholder_document(original):
        orig_sections = _extract_section_headings(original)
        gen_sections = _extract_section_headings(generated)
        missing = set(orig_sections) - set(gen_sections)
        if missing:
            # Only list a few to avoid noisy reports
            preview = ', '.join(list(missing)[:3])
            issues.append(ValidationIssue(
                severity="warning",
                message=f"Missing sections from original: {preview}",
                location="Document structure"
            ))

    # Formatting sanity checks
    if re.search(r'#{7,}', generated):
        issues.append(ValidationIssue(
            severity="warning",
            message="Too many heading levels (> 6)",
            location="Document formatting"
        ))

    # Very short output usually means the model failed or returned a stub
    if len(generated.strip()) < 200:
        issues.append(ValidationIssue(
            severity="error",
            message="Generated content is suspiciously short (< 200 chars)",
            location="Document length"
        ))

    return issues


def _extract_context(text: str, start: int, end: int, window: int = 50) -> str:
    """Extract surrounding context for an issue location."""
    before = max(0, start - window)
    after = min(len(text), end + window)
    context = text[before:after]

    # Clean up for display
    context = context.replace('\n', ' ').strip()
    if len(context) > 100:
        context = context[:97] + "..."
    return context


def _extract_section_headings(text: str) -> List[str]:
    """
    Extract major Markdown headings from a document.

    We track:
      - ATX headings: "# Title", "## Title", ...
      - Setext headings: "Title" underlined with "====" or "----"

    Only level 1–2 ATX are considered "major" to avoid noise.
    """
    headings: List[str] = []

    # ATX-style (# .. ######) — capture up to trailing hashes; keep core title.
    for match in re.finditer(r'^(#{1,6})\s+(.+?)\s*#*\s*$', text, re.MULTILINE):
        level = len(match.group(1))
        title = match.group(2).strip()
        # Normalize: strip leading numbering like "1. ", "2) ", etc.
        title = re.sub(r'^\d+[\.\)]\s*', '', title)
        if level <= 2:
            headings.append(title)

    # Setext-style (underlines with === or ---)
    for match in re.finditer(
        r'^(?P<title>[^\n]+)\n(?P<underline>=+|-{2,})\s*$',
        text,
        re.MULTILINE
    ):
        title = match.group('title').strip()
        title = re.sub(r'^\d+[\.\)]\s*', '', title)
        headings.append(title)

    return headings


def _is_placeholder_document(text: str) -> bool:
    """Heuristic: is the original just a stub/placeholder?"""
    stripped = text.strip()
    placeholders = [
        "# New Document",
        "Type here",
        "Start typing",
        "Enter text",
        "Untitled",
    ]
    if len(stripped) < 100:
        for p in placeholders:
            if p.lower() in stripped.lower():
                return True
    return False


def format_validation_report(issues: List[ValidationIssue]) -> str:
    """Format validation issues as a human-readable report."""
    if not issues:
        return "✓ No validation issues found"

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    lines: List[str] = []

    if errors:
        lines.append(f"❌ {len(errors)} Error(s):")
        for idx, err in enumerate(errors, 1):
            lines.append(f"  {idx}. {err.message}")
            if err.location:
                lines.append(f"     Context: {err.location}")

    if warnings:
        lines.append(f"\n⚠️  {len(warnings)} Warning(s):")
        for idx, warn in enumerate(warnings, 1):
            lines.append(f"  {idx}. {warn.message}")
            if warn.location:
                lines.append(f"     Context: {warn.location}")

    return "\n".join(lines)
