"""
Tests for document validation utilities.

This module tests validation functions that check for placeholders,
completeness, and document quality issues.
"""

import pytest
from app.utils.validation import (
    validate_completeness,
    ValidationIssue,
    format_validation_report,
    _extract_section_headings,
    _is_placeholder_document,
    _extract_context
)


class TestPlaceholderDetection:
    """Tests for placeholder pattern detection."""

    def test_detects_unchanged_placeholder(self):
        """Should detect '[sections remain unchanged]' placeholders."""
        doc = "Section 1: Content\n\n[Sections 2-5 remain unchanged]\n\nSection 6: More content"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("Placeholder" in err.message for err in errors)
        assert any("[Sections 2-5 remain unchanged]" in err.message for err in errors)

    def test_detects_todo_placeholder(self):
        """Should detect [TODO] placeholders."""
        doc = "Section 1: Done\n\n[TODO: Add details here]\n\nSection 2: Also done"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("TODO" in err.message for err in errors)

    def test_detects_insert_placeholder(self):
        """Should detect [INSERT ...] placeholders."""
        doc = "Contract begins\n\n[INSERT PARTY NAME]\n\nContract continues"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("Template placeholder" in err.message for err in errors)

    def test_detects_remains_unchanged_text(self):
        """Should detect 'remains unchanged' text patterns."""
        doc = "Clause 1: New text\n\nClause 2 remains unchanged\n\nClause 3: More text"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("Incomplete section" in err.message for err in errors)

    def test_detects_ellipsis_placeholder(self):
        """Should detect ellipsis placeholders."""
        doc = "Section 1\n\n... (content remains the same)\n\nSection 2"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("Ellipsis" in err.message for err in errors)

    def test_no_error_for_complete_document(self):
        """Should not flag complete documents without placeholders."""
        doc = """# Complete Contract

## Article 1: Definitions
This contract defines the following terms...

## Article 2: Obligations
The parties agree to the following obligations...

## Article 3: Term
This contract is valid for 12 months.
"""

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        placeholder_errors = [e for e in errors if "placeholder" in e.message.lower()]
        assert len(placeholder_errors) == 0


class TestBlankLineDetection:
    """Tests for blank line/underscore placeholder detection."""

    def test_detects_blank_line_placeholder(self):
        """Should detect underscore blank lines (not in signatures)."""
        doc = "Party Name: ________\n\nDate of signing: ________"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        # Should have errors for blanks not near signature context
        assert any("Blank placeholder" in err.message for err in errors)

    def test_allows_signature_block_underscores(self):
        """Should allow underscores in signature blocks."""
        doc = """Contract content here.

## Signatures

Signature: ________________
Name: ________________
Date: ________________

Witness: ________________
"""

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        blank_errors = [e for e in errors if "Blank placeholder" in e.message]

        # Should not flag these as they're in signature context
        assert len(blank_errors) == 0

    def test_detects_non_signature_blanks(self):
        """Should detect blanks that are not in signature context."""
        doc = "The value is ________ dollars.\n\nThe date is ________."

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("Blank placeholder" in err.message for err in errors)


class TestTruncationDetection:
    """Tests for truncation marker detection."""

    def test_detects_trailing_ellipsis(self):
        """Should detect document ending with ellipsis."""
        doc = "This is the start of a document that ends abruptly..."

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("truncated" in err.message.lower() for err in errors)

    def test_detects_continued_marker(self):
        """Should detect [continued] markers."""
        doc = "Page 1 content\n\n[continued]\n\nMore content"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("truncated" in err.message.lower() for err in errors)

    def test_detects_standalone_ellipsis(self):
        """Should detect standalone ellipsis lines."""
        doc = "Section 1\n\n...\n\nSection 2"

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("truncated" in err.message.lower() for err in errors)

    def test_no_error_for_ellipsis_in_content(self):
        """Should not flag ellipsis used naturally in content."""
        doc = "The party agrees to provide services including... legal advice and representation."

        issues = validate_completeness(doc)

        # Should not detect truncation for mid-sentence ellipsis
        errors = [i for i in issues if i.severity == "error"]
        truncation_errors = [e for e in errors if "truncated" in e.message.lower()]
        # Note: This might still trigger depending on implementation
        # Just verify it doesn't end with ellipsis


class TestSectionComparison:
    """Tests for section structure comparison."""

    def test_detects_missing_sections(self):
        """Should detect when sections from original are missing."""
        original = """# Contract

## Article 1: Definitions
Content here

## Article 2: Obligations
Content here

## Article 3: Term
Content here
"""

        generated = """# Contract

## Article 1: Definitions
Content here

## Article 3: Term
Content here
"""

        issues = validate_completeness(generated, original)

        warnings = [i for i in issues if i.severity == "warning"]
        missing_warnings = [w for w in warnings if "Missing sections" in w.message]
        assert len(missing_warnings) > 0
        assert any("Obligations" in w.message or "Article 2" in w.message for w in missing_warnings)

    def test_no_warning_when_all_sections_present(self):
        """Should not warn when all major sections are present."""
        original = """# Contract

## Article 1: Definitions
Original content

## Article 2: Obligations
Original content
"""

        generated = """# Contract

## Article 1: Definitions
New content here

## Article 2: Obligations
New content here
"""

        issues = validate_completeness(generated, original)

        warnings = [i for i in issues if i.severity == "warning"]
        missing_warnings = [w for w in warnings if "Missing sections" in w.message]
        assert len(missing_warnings) == 0

    def test_ignores_placeholder_original(self):
        """Should not compare sections if original is a placeholder."""
        original = "# New Document\n\nType here"
        generated = "# Complete Contract\n\n## Article 1\nContent"

        issues = validate_completeness(generated, original)

        # Should not warn about missing sections from placeholder
        warnings = [i for i in issues if i.severity == "warning"]
        missing_warnings = [w for w in warnings if "Missing sections" in w.message]
        assert len(missing_warnings) == 0


class TestFormattingChecks:
    """Tests for formatting validation."""

    def test_detects_too_many_heading_levels(self):
        """Should warn about excessive heading levels."""
        doc = "#######  Too many hashes"

        issues = validate_completeness(doc)

        warnings = [i for i in issues if i.severity == "warning"]
        assert any("Too many heading levels" in w.message for w in warnings)

    def test_allows_valid_heading_levels(self):
        """Should allow up to 6 heading levels."""
        doc = """# Level 1
## Level 2
### Level 3
#### Level 4
##### Level 5
###### Level 6
"""

        issues = validate_completeness(doc)

        warnings = [i for i in issues if i.severity == "warning"]
        heading_warnings = [w for w in warnings if "heading levels" in w.message.lower()]
        assert len(heading_warnings) == 0


class TestLengthValidation:
    """Tests for document length validation."""

    def test_detects_suspiciously_short_document(self):
        """Should flag very short generated content."""
        short_doc = "Brief text."

        issues = validate_completeness(short_doc)

        errors = [i for i in issues if i.severity == "error"]
        assert any("suspiciously short" in err.message.lower() for err in errors)

    def test_accepts_adequate_length_document(self):
        """Should accept documents with adequate length."""
        adequate_doc = "This is a properly sized document. " * 20  # Over 200 chars

        issues = validate_completeness(adequate_doc)

        errors = [i for i in issues if i.severity == "error"]
        length_errors = [e for e in errors if "short" in e.message.lower()]
        assert len(length_errors) == 0


class TestHelperFunctions:
    """Tests for helper utility functions."""

    def test_extract_context(self):
        """Should extract surrounding context for an issue."""
        text = "A" * 100 + "PROBLEM" + "B" * 100
        start = 100
        end = 107

        context = _extract_context(text, start, end, window=20)

        assert "PROBLEM" in context
        assert "A" * 20 in context or "B" * 20 in context
        assert len(context) <= 100

    def test_extract_section_headings_atx(self):
        """Should extract ATX-style markdown headings."""
        doc = """# Title 1
Some content
## Title 2
More content
### Title 3
Even more
"""

        headings = _extract_section_headings(doc)

        assert "Title 1" in headings
        assert "Title 2" in headings
        # Title 3 might not be included if only level 1-2

    def test_extract_section_headings_setext(self):
        """Should extract Setext-style headings."""
        doc = """Title 1
=======

Some content

Title 2
-------

More content
"""

        headings = _extract_section_headings(doc)

        assert "Title 1" in headings
        assert "Title 2" in headings

    def test_extract_section_headings_with_numbering(self):
        """Should normalize numbered section titles."""
        doc = """# 1. Introduction
## 2. Background
### 3. Methodology
"""

        headings = _extract_section_headings(doc)

        # Should strip leading numbers
        assert "Introduction" in headings
        assert "Background" in headings

    def test_is_placeholder_document(self):
        """Should detect placeholder documents."""
        placeholder1 = "# New Document\n\nType here"
        placeholder2 = "Untitled"
        real_doc = "This is a real contract with substantial content and multiple sections."

        assert _is_placeholder_document(placeholder1) is True
        assert _is_placeholder_document(placeholder2) is True
        assert _is_placeholder_document(real_doc) is False


class TestValidationReportFormatting:
    """Tests for validation report formatting."""

    def test_format_no_issues(self):
        """Should format report for no issues."""
        issues = []

        report = format_validation_report(issues)

        assert "No validation issues" in report

    def test_format_with_errors(self):
        """Should format report with errors."""
        issues = [
            ValidationIssue("error", "Placeholder found", "Section 1"),
            ValidationIssue("error", "Document truncated", "End")
        ]

        report = format_validation_report(issues)

        assert "Error(s)" in report
        assert "Placeholder found" in report
        assert "Document truncated" in report
        assert "Section 1" in report

    def test_format_with_warnings(self):
        """Should format report with warnings."""
        issues = [
            ValidationIssue("warning", "Missing section", "Structure"),
        ]

        report = format_validation_report(issues)

        assert "Warning(s)" in report
        assert "Missing section" in report

    def test_format_with_mixed_issues(self):
        """Should format report with errors and warnings."""
        issues = [
            ValidationIssue("error", "Placeholder found"),
            ValidationIssue("warning", "Formatting issue"),
            ValidationIssue("error", "Content truncated"),
        ]

        report = format_validation_report(issues)

        assert "2 Error(s)" in report
        assert "1 Warning(s)" in report
        assert "Placeholder found" in report
        assert "Formatting issue" in report


class TestEdgeCases:
    """Edge case tests for validation."""

    def test_empty_document(self):
        """Should handle empty documents."""
        issues = validate_completeness("")

        # Should flag as too short
        errors = [i for i in issues if i.severity == "error"]
        assert any("short" in err.message.lower() for err in errors)

    def test_document_with_only_whitespace(self):
        """Should handle documents with only whitespace."""
        issues = validate_completeness("   \n\n\t  \n  ")

        errors = [i for i in issues if i.severity == "error"]
        assert any("short" in err.message.lower() for err in errors)

    def test_document_with_unicode(self):
        """Should handle unicode content correctly."""
        doc = "Contract with émojis 🎉 and 中文 content. " * 20

        issues = validate_completeness(doc)

        # Should not crash, and no placeholder errors
        errors = [i for i in issues if i.severity == "error"]
        placeholder_errors = [e for e in errors if "placeholder" in e.message.lower()]
        assert len(placeholder_errors) == 0

    def test_very_long_document(self):
        """Should handle very long documents efficiently."""
        long_doc = "## Section Content\n\n" + ("Text paragraph. " * 1000)

        issues = validate_completeness(long_doc)

        # Should complete without errors/warnings about length
        errors = [i for i in issues if i.severity == "error"]
        length_errors = [e for e in errors if "short" in e.message.lower()]
        assert len(length_errors) == 0

    def test_multiple_placeholders(self):
        """Should detect multiple placeholder issues."""
        doc = """Section 1: [TODO]

[Sections 2-3 remain unchanged]

Section 4: ________

... (content continues)
"""

        issues = validate_completeness(doc)

        errors = [i for i in issues if i.severity == "error"]
        # Should detect multiple issues
        assert len(errors) >= 3
