"""Utility functions for data processing.

Currently contains:
- response_parser: Extracts JSON from OpenAI responses
"""

import re
import json

def response_parser(output_text: str):
    """Parse JSON content from OpenAI response text.
    
    OpenAI Responses API may return JSON wrapped in markdown code blocks.
    This function:
    1. Looks for ```json...``` fenced code blocks
    2. Extracts the JSON content from within the fence
    3. Falls back to raw text if no fence found
    4. Parses and returns as Python dict
    
    Args:
        output_text: Raw text output from OpenAI Responses API
        
    Returns:
        Parsed JSON as Python dictionary, or None if parsing fails
        
    Example:
        Input: "```json\n{\"result\": [1, 2, 3]}\n```"
        Output: {"result": [1, 2, 3]}
    """
    try:
        # Return None for empty strings
        if not output_text or not output_text.strip():
            return None
            
        # First try: Look for fenced code blocks
        pattern = r"```(?:json)?\s*(.*?)\s*```"
        match = re.search(pattern, output_text, re.DOTALL)
        
        if match:
            json_str = match.group(1).strip()
            if json_str:
                return json.loads(json_str)
        
        # Second try: Look for JSON object or array in the text
        # Find first { or [ and try to parse from there
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start_idx = output_text.find(start_char)
            if start_idx != -1:
                # Find matching closing bracket
                depth = 0
                for i, char in enumerate(output_text[start_idx:], start=start_idx):
                    if char == start_char:
                        depth += 1
                    elif char == end_char:
                        depth -= 1
                        if depth == 0:
                            json_str = output_text[start_idx:i+1]
                            try:
                                return json.loads(json_str)
                            except json.JSONDecodeError:
                                continue
        
        # Last try: Parse the whole thing
        return json.loads(output_text.strip())
        
    except (json.JSONDecodeError, AttributeError):
        return None
