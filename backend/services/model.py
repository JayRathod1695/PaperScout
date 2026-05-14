# services/model.py
import json
import logging
import asyncio
from typing import Optional

from openai import OpenAI, AsyncOpenAI  # Note: we need async client; OpenAI's default is sync but we can use AsyncOpenAI
from utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# ============================================================
# NVIDIA NIM client (OpenAI-compatible)
# ============================================================

# Use AsyncOpenAI for async compatibility
client = AsyncOpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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",  # Replace with env var if needed
)

MODEL_NAME = "nvidia/nvidia-nemotron-nano-9b-v2"


async def _generate(prompt: str, system_content: str = "/think") -> str:
    """
    Call the NVIDIA NIM model with streaming, collect and return the final content.
    The model may return 'reasoning_content' and regular 'content'.
    We ignore reasoning and only capture the final assistant message content.
    """
    try:
        # Using streaming as in the snippet
        stream = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            top_p=0.95,
            max_tokens=4096,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True,
            extra_body={
                "min_thinking_tokens": 256,
                "max_thinking_tokens": 1024,
            }
        )
        
        collected_content = []
        thinking_chunks = 0
        content_chunks = 0
        logger.info("LLM stream started")
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Track thinking tokens for visibility (reasoning_content is separate from content)
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                thinking_chunks += 1
                if thinking_chunks == 1:
                    logger.info("LLM thinking phase started...")

            # Always collect content independently — don't use elif so we never miss
            # a chunk where both reasoning_content and content are present
            if delta.content is not None:
                if content_chunks == 0:
                    if thinking_chunks > 0:
                        logger.info(f"LLM thinking done ({thinking_chunks} chunks), generating response...")
                    logger.info(f"First content chunk: {repr(delta.content)}")
                content_chunks += 1
                collected_content.append(delta.content)
        
        full_response = "".join(collected_content).strip()
        logger.info(f"LLM stream finished — {content_chunks} content chunks, response length: {len(full_response)}")
        logger.info(f"LLM raw response preview: {repr(full_response[:200])}")
        if not full_response:
            raise ValueError("Empty response from LLM")
        return full_response
    
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise


# ============================================================
# PROMPTS (unchanged from original plan)
# ============================================================

TRIAGE_PROMPT = """You are a brutally honest research advisor for ML/CS researchers.
Given this paper text, respond ONLY in valid JSON matching this exact schema:
{
  "claim": "one sentence — what the paper claims to prove or demonstrate",
  "method": "two sentences max — what they actually did technically",
  "catch": "the biggest limitation, hidden assumption, or weakness",
  "verdict": "Read fully | Skim [specific section name] | Skip",
  "verdict_reason": "one sentence — why this verdict",
  "steal": "one concrete, actionable idea from this paper adaptable to other work"
}

Rules:
- No hedging. No 'the authors propose'. Be direct.
- 'catch' must be something NOT obvious from the abstract.
- 'steal' must be specific enough to act on, not generic.
- 'verdict' MUST be exactly one of: 'Read fully', 'Skim [Section Name]', or 'Skip'.
- Respond with ONLY the JSON object. No markdown, no explanation, no code block.

Paper text:
"""

KEYWORD_PROMPT = """Extract 5-7 search keywords or phrases from this paper for finding related work on Semantic Scholar.
Return ONLY a valid JSON array of strings. No explanation, no markdown.
Focus on: core technique names, problem domain, novel concepts introduced.
Example output: ["contrastive learning", "vision transformers", "self-supervised pretraining"]

Paper text (first 3000 chars):
{text}"""

RELEVANCE_PROMPT = """You are a brutally honest research advisor.
Given a paper abstract and a researcher's goal, do two things:
1. Triage the paper
2. Score its relevance to the researcher's specific goal

Researcher's goal: {user_goal}

Paper title: {title}
Paper abstract: {abstract}

Respond ONLY in valid JSON matching this exact schema (no markdown, no explanation):
{
  "claim": "one sentence",
  "method": "two sentences max",
  "catch": "biggest limitation or assumption",
  "verdict": "Read fully | Skim [Section Name] | Skip",
  "verdict_reason": "one sentence",
  "steal": "one concrete actionable idea",
  "relevance_score": 0.0,
  "relevance_reason": "one sentence explaining score relative to researcher goal"
}

relevance_score must be a float between 0.0 (irrelevant) and 1.0 (directly on-topic)."""


# ============================================================
# PUBLIC FUNCTIONS (now using LLM)
# ============================================================

@retry_with_backoff(max_retries=3, base_delay=5.0)
async def triage_paper(text: str) -> dict:
    """
    Run triage on paper text using LLM.
    Returns dict with keys: claim, method, catch, verdict, verdict_reason, steal.
    """
    truncated = text[:80_000]  # stay within token limits
    prompt = TRIAGE_PROMPT + "\n" + truncated
    response = await _generate(prompt)
    result = _parse_json_response(response)
    _validate_triage_keys(result)
    return result


@retry_with_backoff(max_retries=3, base_delay=5.0)
async def extract_keywords(text: str) -> list[str]:
    """
    Extract 5-7 search keywords from paper text using LLM.
    Returns list of keyword strings.
    """
    truncated = text[:3_000]
    prompt = KEYWORD_PROMPT.replace("{text}", truncated)
    response = await _generate(prompt, system_content="You are a research assistant that outputs only JSON.")
    keywords = _parse_json_response(response)
    if not isinstance(keywords, list):
        raise ValueError(f"Expected list of keywords, got {type(keywords)}")
    # Ensure we return strings, and limit to 7
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    return keywords[:7]


@retry_with_backoff(max_retries=3, base_delay=5.0)
async def triage_with_relevance(title: str, abstract: str, user_goal: str) -> dict:
    """
    Triage a related paper and score relevance to user_goal using LLM.
    Returns dict with all triage keys + relevance_score + relevance_reason.
    """
    # Use % formatting or manual replacement to avoid KeyError when abstract/goal contain { }
    prompt = RELEVANCE_PROMPT.replace("{user_goal}", user_goal).replace("{title}", title).replace("{abstract}", abstract)
    response = await _generate(prompt)
    result = _parse_json_response(response)
    # Ensure required keys exist
    required_triage = {"claim", "method", "catch", "verdict", "verdict_reason", "steal"}
    if not required_triage.issubset(result.keys()):
        raise ValueError(f"Missing required triage keys in LLM response: {result}")
    if "relevance_score" not in result:
        raise ValueError("Missing relevance_score in LLM response")
    # Convert relevance_score to float if needed
    result["relevance_score"] = float(result["relevance_score"])
    _validate_triage_keys(result)  # includes relevance_score? No, but we already checked.
    return result


# ============================================================
# HELPERS
# ============================================================

def _parse_json_response(text: str) -> dict | list:
    """Extract JSON from model response, handling markdown, missing braces, and thinking bleed."""
    cleaned = text.strip()

    # Remove markdown code blocks if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Extract the first {...} or [...] block from anywhere in the response
    # This handles cases where the model outputs text before/after the JSON
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Last resort: the model may have omitted the opening brace
    # Try wrapping with { } if it looks like a JSON object body
    if cleaned.lstrip().startswith('"'):
        try:
            return json.loads('{' + cleaned + '}')
        except json.JSONDecodeError:
            # Try trimming trailing comma before closing brace
            try:
                trimmed = cleaned.rstrip().rstrip(',')
                return json.loads('{' + trimmed + '}')
            except json.JSONDecodeError:
                pass

    logger.error(f"Failed to parse JSON from LLM response (first 500 chars): {repr(text[:500])}")
    raise ValueError(f"Invalid JSON from LLM — could not extract valid JSON from response")


def _validate_triage_keys(data: dict) -> None:
    """Raise ValueError if required triage keys are missing."""
    required = {"claim", "method", "catch", "verdict", "verdict_reason", "steal"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"AI response missing required keys: {missing}")