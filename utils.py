import re
import json

def response_parser(output_text: str):
    """
    Extracts the JSON content from model response, even if wrapped in ```json ... ```
    """
    pattern = r"```json\s*(.*?)\s*```"
    match = re.search(pattern, output_text, re.DOTALL)
    json_str = match.group(1) if match else output_text.strip()
    return json.loads(json_str)
