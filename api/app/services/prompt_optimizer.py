"""
Prompt Optimizer Service for LUMEN

This service uses Claude (Anthropic) to analyze and improve user prompts
for legal document generation. It implements a Self-Refine pattern where
Claude acts as a meta-optimizer for prompt quality.
"""

import json
import logging
from typing import Optional
from datetime import datetime

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.clients import anthropic_client, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

# Legal-specific meta-prompt template for optimization
LEGAL_PROMPT_OPTIMIZER_TEMPLATE = """You are an expert legal AI assistant. Your task is to enhance this user's prompt for legal document generation by making it more specific and actionable, while keeping it concise.

USER REQUEST: {user_prompt}
DOCUMENT TYPE: {document_type}
CURRENT CONTEXT: {context_summary}

OPTIMIZATION GUIDELINES:

1. **Clarify Jurisdiction**: Make vague jurisdictions specific (e.g., "California" → "State of California, USA"; "Portuguese law" → "governed by Portuguese law (Portugal jurisdiction)")

2. **Add Legal Precision**: Use proper legal terminology where helpful (e.g., "NDA" → "mutual non-disclosure agreement"; "prenup" → "prenuptial agreement")

3. **Suggest Standard Sections**: Briefly mention key sections/clauses typically needed for this document type, WITHOUT demanding specific information

4. **Keep It Actionable**: The improved prompt should remain a clear directive, NOT a list of questions or requirements for the user to fill in

5. **Stay Concise**: The improved prompt should be 2-4 sentences max. Do NOT create lengthy checklists or requirement documents.

6. **Preserve Intent**: Never change what the user is fundamentally asking for.

EXAMPLES:

Bad optimization (too verbose, asks questions):
"Draft a marriage agreement. PARTIES NEEDED: Full legal names, ID numbers, dates of birth. PROPERTY: List all assets. REQUIREMENTS: ..."

Good optimization (enhances while staying concise):
"Draft a comprehensive prenuptial agreement governed by Portuguese law, including standard clauses for matrimonial property regime, asset division, and spousal rights. Use Portuguese legal terminology and cite relevant articles from the Portuguese Civil Code where applicable."

OUTPUT FORMAT - Return valid JSON only:
{{
  "improved_prompt": "The enhanced version (2-4 sentences, stays a directive, no checklists)",
  "changes": [
    "Brief description of each improvement"
  ],
  "missing_info": [],
  "confidence": "high|medium|low"
}}

Return ONLY the JSON object, no other text."""


class PromptOptimizerService:
    """
    Service for optimizing user prompts using Claude's Self-Refine pattern.

    This service analyzes user input and suggests improvements specifically
    tailored for legal document generation, ensuring clarity, completeness,
    and legal precision.
    """

    def __init__(self):
        """Initialize the prompt optimizer service."""
        if not anthropic_client:
            raise RuntimeError("Anthropic client not initialized. Check ANTHROPIC_API_KEY.")
        self.client: AsyncAnthropic = anthropic_client
        # Use Haiku for prompt optimization - much faster and cheaper than Sonnet
        # Haiku is ~20x cheaper and 3x faster with minimal quality loss for this task
        self.model = "claude-3-haiku-20240307"

    async def improve_prompt(
        self,
        user_prompt: str,
        document_type: Optional[str] = None,
        thread_id: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> dict:
        """
        Improve a user's prompt for legal document generation.

        Args:
            user_prompt: The original user input to optimize
            document_type: Optional document type (e.g., "nda", "contract", "lease")
            thread_id: Optional thread ID for context retrieval
            session: Optional database session for context lookup

        Returns:
            Dictionary containing:
                - original: The original user prompt
                - improved: The optimized version
                - changes: List of improvements made
                - missing_info: Optional list of info user should consider providing
                - confidence: Optimizer's confidence level (high/medium/low)
                - timestamp: ISO timestamp of optimization

        Raises:
            Exception: If the optimization fails or returns invalid JSON
        """
        logger.info(f"Optimizing prompt for document_type={document_type}, thread_id={thread_id}")

        try:
            # Get context summary if thread_id provided
            context_summary = "No previous context available."
            if thread_id and session:
                context_summary = await self._get_context_summary(thread_id, session)

            # Format the meta-prompt
            meta_prompt = LEGAL_PROMPT_OPTIMIZER_TEMPLATE.format(
                user_prompt=user_prompt,
                document_type=document_type or "unspecified",
                context_summary=context_summary
            )

            # Call Claude to optimize
            optimization_result = await self._call_optimizer(meta_prompt)

            # Build response
            result = {
                "original": user_prompt,
                "improved": optimization_result.get("improved_prompt", user_prompt),
                "changes": optimization_result.get("changes", []),
                "missing_info": optimization_result.get("missing_info", []),
                "confidence": optimization_result.get("confidence", "medium"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            logger.info(f"Successfully optimized prompt with confidence={result['confidence']}")
            return result

        except Exception as e:
            logger.error(f"Prompt optimization failed: {str(e)}", exc_info=True)
            # Return original prompt on failure - graceful degradation
            return {
                "original": user_prompt,
                "improved": user_prompt,
                "changes": [],
                "missing_info": [],
                "confidence": "low",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "error": str(e)
            }

    async def _get_context_summary(
        self,
        thread_id: str,
        session: AsyncSession
    ) -> str:
        """
        Get relevant context from thread (recent messages, document type).

        Args:
            thread_id: The thread ID to get context from
            session: Database session

        Returns:
            A brief summary of the thread context
        """
        try:
            # Import here to avoid circular dependencies
            from ..models import Message
            from sqlalchemy import select, desc

            # Get last 3 messages from thread for context
            query = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(desc(Message.created_at))
                .limit(3)
            )
            result = await session.execute(query)
            messages = result.scalars().all()

            if not messages:
                return "New conversation, no previous context."

            # Build context summary
            context_parts = []
            for msg in reversed(messages):  # Chronological order
                role = msg.role.capitalize()
                content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                context_parts.append(f"{role}: {content_preview}")

            context = "Recent conversation:\n" + "\n".join(context_parts)
            return context

        except Exception as e:
            logger.warning(f"Failed to get context summary: {str(e)}")
            return "Context unavailable."

    async def _call_optimizer(self, meta_prompt: str) -> dict:
        """
        Call Claude API with the meta-prompt to optimize the user's input.

        Args:
            meta_prompt: The formatted meta-prompt for Claude

        Returns:
            Parsed JSON response from Claude containing optimization results

        Raises:
            Exception: If API call fails or response is invalid JSON
        """
        try:
            # Call Claude with the meta-prompt
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,  # Reduced - we want concise responses (2-4 sentences)
                temperature=0.5,  # Slightly higher for more natural improvements
                messages=[
                    {
                        "role": "user",
                        "content": meta_prompt
                    }
                ]
            )

            # Extract text from response
            if not response.content or len(response.content) == 0:
                raise ValueError("Empty response from Claude")

            response_text = response.content[0].text.strip()

            # Parse JSON response
            # Claude might wrap JSON in markdown code blocks, so handle that
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Remove ```json
            if response_text.startswith("```"):
                response_text = response_text[3:]  # Remove ```
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Remove trailing ```

            response_text = response_text.strip()

            # Parse JSON
            result = json.loads(response_text)

            # Validate required fields
            if "improved_prompt" not in result:
                raise ValueError("Response missing 'improved_prompt' field")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude: {str(e)}")
            logger.debug(f"Raw response: {response_text if 'response_text' in locals() else 'N/A'}")
            raise Exception("Failed to parse optimization response")
        except Exception as e:
            logger.error(f"Claude API call failed: {str(e)}")
            raise


# Singleton instance
_optimizer_service = None


def get_optimizer_service() -> PromptOptimizerService:
    """
    Get or create the singleton PromptOptimizerService instance.

    Returns:
        PromptOptimizerService instance
    """
    global _optimizer_service
    if _optimizer_service is None:
        _optimizer_service = PromptOptimizerService()
    return _optimizer_service
