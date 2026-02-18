"""Pydantic models for API request/response validation.

These models define the schema for:
- Incoming compliance check requests
- Data items (MLS listings)
- API responses with results
"""

from pydantic import BaseModel, model_validator
from typing import List, Optional

class RuleConfig(BaseModel):
    """Configuration for a compliance rule.
    
    Attributes:
        ID: Rule identifier (FAIR, COMP, PROMO)
        CheckColumns: Comma-separated list of columns to check (e.g., "Remarks,PrivateRemarks")
    """
    ID: str  # Rule type: FAIR (Fair Housing), COMP (Compensation), PROMO (Marketing)
    CheckColumns: str  # Columns to analyze for this rule (comma-separated)
    # Accept both `mlsId` and common-typo `mlsIds` in incoming payloads; normalize to `mlsId`.
    mlsId: Optional[str] = None
    mlsIds: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def normalize_mlsid(cls, values):
        # If payload used `mlsIds` (typo), normalize to `mlsId`
        if isinstance(values, dict):
            if 'mlsIds' in values and 'mlsId' not in values:
                values['mlsId'] = values.pop('mlsIds')
        return values

    def columns_list(self):
        """Return the CheckColumns as a trimmed list of column names."""
        if not self.CheckColumns:
            return []
        return [c.strip() for c in self.CheckColumns.split(',') if c.strip()]

class DataItem(BaseModel):
    """Represents a single MLS listing to check for compliance.
    
    Attributes:
        mlsnum: Unique MLS listing number (mandatory)
        mlsId: MLS system identifier (mandatory)
        Remarks: Public remarks/description (optional, defaults to empty string)
        PrivateRemarks: Agent-only private remarks (optional, defaults to empty string)
        Directions: Property directions (optional, defaults to empty string)
    """
    mlsnum: str  # Mandatory: Unique listing identifier
    mlsId: str  # Mandatory: MLS system ID (used for custom rule loading)
    Remarks: Optional[str] = ""  # Public listing description
    PrivateRemarks: Optional[str] = ""  # Private agent notes
    Directions: Optional[str] = ""  # Directions to property
    # Additional optional fields used by rules when present in CheckColumns
    ShowingInstructions: Optional[str] = ""
    ConfidentialRemarks: Optional[str] = ""
    SupplementRemarks: Optional[str] = ""
    Concessions: Optional[str] = ""
    SaleFactors: Optional[str] = ""

class ComplianceRequest(BaseModel):
    """Main request body for compliance checking.
    
    Attributes:
        AIViolationID: List of rules to apply (FAIR, COMP, PROMO)
        Data: List of MLS listings to check
    
    Example:
        {
            "AIViolationID": [
                {"ID": "FAIR", "CheckColumns": "Remarks,PrivateRemarks"}
            ],
            "Data": [
                {"mlsnum": "ML123", "mlsId": "TESTMLS", "Remarks": "Beautiful home"}
            ]
        }
    """
    AIViolationID: List[RuleConfig]  # Rules to apply to all data items
    Data: List[DataItem]  # MLS listings to analyze

class APIResponse(BaseModel):
    """Response returned after compliance checking.
    
    Attributes:
        ok: HTTP status code (200 for success)
        results: List of dicts containing results for each listing
        error_message: Error description (empty string if no errors)
        total_tokens: Total OpenAI tokens used across all API calls
        elapsed_time: Total processing time in seconds
    """
    ok: int  # HTTP status code
    results: List  # Results for each listing with rule outcomes
    request_id: Optional[str] = None  # UUID for request tracing
    error_message: str  # Error details (empty if successful)
    total_tokens: Optional[int] = 0  # Total tokens consumed
    elapsed_time: Optional[float] = 0.0  # Total time in seconds
