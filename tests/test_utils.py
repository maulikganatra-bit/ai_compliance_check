"""Unit tests for utility functions."""

import pytest
from app.utils.utils import response_parser


class TestResponseParser:
    """Tests for response_parser function."""
    
    def test_parse_valid_json_object(self):
        """Test parsing valid JSON object."""
        response = '{"violations": false, "response": "No violations found"}'
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is False
        assert result["response"] == "No violations found"
    
    def test_parse_valid_json_array(self):
        """Test parsing valid JSON array."""
        response = '[{"id": 1}, {"id": 2}]'
        result = response_parser(response)
        
        # Parser finds first { and parses that object
        assert isinstance(result, dict)
        assert result["id"] == 1
    
    def test_parse_json_with_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = '''```json
{
    "violations": true,
    "response": "Found violation"
}
```'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is True
        assert result["response"] == "Found violation"
    
    def test_parse_json_with_backticks_only(self):
        """Test parsing JSON wrapped in simple backticks."""
        response = '''```
{"violations": false, "response": "OK"}
```'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is False
    
    def test_parse_json_with_leading_text(self):
        """Test parsing JSON with leading text."""
        response = '''Here is the result:
{"violations": true, "response": "Issue found"}'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is True
    
    def test_parse_json_with_trailing_text(self):
        """Test parsing JSON with trailing text."""
        response = '''{"violations": false, "response": "All good"}
This is additional commentary.'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is False
    
    def test_parse_json_with_whitespace(self):
        """Test parsing JSON with extra whitespace."""
        response = '''
        
        {
            "violations": false,
            "response": "Clean"
        }
        
        '''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is False
    
    def test_parse_nested_json(self):
        """Test parsing nested JSON structures."""
        response = '''{
            "violations": true,
            "details": {
                "type": "FAIR",
                "severity": "high"
            },
            "response": "Multiple issues"
        }'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is True
        assert result["details"]["type"] == "FAIR"
    
    def test_parse_json_with_arrays(self):
        """Test parsing JSON with array values."""
        response = '''{
            "violations": true,
            "issues": ["Issue 1", "Issue 2"],
            "response": "Found 2 issues"
        }'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert len(result["issues"]) == 2
    
    def test_parse_json_with_special_characters(self):
        """Test parsing JSON with special characters."""
        response = '''{
            "violations": false,
            "response": "Property has \\"nice\\" features and costs $500,000"
        }'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert '"nice"' in result["response"]
        assert "$500,000" in result["response"]
    
    def test_parse_invalid_json_returns_none(self):
        """Test that invalid JSON returns None."""
        response = "This is not JSON at all"
        result = response_parser(response)
        
        assert result is None
    
    def test_parse_incomplete_json_returns_none(self):
        """Test that incomplete JSON returns None."""
        response = '{"violations": true, "response":'
        result = response_parser(response)
        
        assert result is None
    
    def test_parse_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = response_parser("")
        assert result is None
    
    def test_parse_only_whitespace_returns_none(self):
        """Test that whitespace-only string returns None."""
        result = response_parser("   \n\t  ")
        assert result is None
    
    def test_parse_json_boolean_values(self):
        """Test parsing JSON with boolean values."""
        response = '''{
            "violations": true,
            "has_images": false,
            "verified": true,
            "response": "Mixed values"
        }'''
        result = response_parser(response)
        
        assert result["violations"] is True
        assert result["has_images"] is False
        assert result["verified"] is True
    
    def test_parse_json_null_values(self):
        """Test parsing JSON with null values."""
        response = '''{
            "violations": false,
            "details": null,
            "response": "OK"
        }'''
        result = response_parser(response)
        
        assert result["violations"] is False
        assert result["details"] is None
    
    def test_parse_json_number_values(self):
        """Test parsing JSON with various number types."""
        response = '''{
            "violations": false,
            "count": 42,
            "score": 98.5,
            "large_number": 1234567890,
            "response": "Numbers work"
        }'''
        result = response_parser(response)
        
        assert result["count"] == 42
        assert result["score"] == 98.5
        assert result["large_number"] == 1234567890
    
    def test_parse_multiple_json_objects_returns_first(self):
        """Test that multiple JSON objects returns the first one."""
        response = '''{"violations": false, "response": "First"}
{"violations": true, "response": "Second"}'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert result["violations"] is False
        assert result["response"] == "First"
    
    def test_parse_json_with_unicode(self):
        """Test parsing JSON with unicode characters."""
        response = '''{
            "violations": false,
            "response": "Property in São Paulo with café nearby 🏠"
        }'''
        result = response_parser(response)
        
        assert isinstance(result, dict)
        assert "São Paulo" in result["response"]
        assert "café" in result["response"]
