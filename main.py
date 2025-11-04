import asyncio
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from tenacity import retry, wait_random_exponential, stop_after_attempt
from dotenv import load_dotenv

from ai_rule_functions import (
    get_fair_housing_violation_response,
    get_comp_violation_response,
)

load_dotenv()

client = AsyncOpenAI()

# ---------------------------
# FastAPI App
# ---------------------------
app = FastAPI(
    title="AI Compliance Checker API",
    description="Async multi-rule compliance checker using OpenAI responses",
    version="2.0.0"
)

# ---------------------------
# Pydantic Models
# ---------------------------
class RuleConfig(BaseModel):
    ID: str
    CheckColumns: str

class DataItem(BaseModel):
    mlsnum: str
    Remarks: Optional[str] = ""
    PrivateRemarks: Optional[str] = ""

class ComplianceRequest(BaseModel):
    AIViolationID: List[RuleConfig]
    Data: List[DataItem]



class APIResponse(BaseModel):
    ok: int
    results: List
    error_message: str
    total_tokens: Optional[int] = 0
    elapsed_time: Optional[float] = 0.0


# ---------------------------
# Async Wrappers for Rule Functions
# ---------------------------
@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def async_get_fair_housing(public_remarks, private_remarks):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_fair_housing_violation_response, public_remarks, private_remarks)


@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(3))
async def async_get_comp(public_remarks, private_remarks):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_comp_violation_response, public_remarks, private_remarks)


# ---------------------------
# Main Processing Logic
# ---------------------------
async def process_record(record: DataItem, ai_rules: Dict[str, List[str]], semaphore: asyncio.Semaphore):
    async with semaphore:
        start_time = time.time()
        mlsnum = record.mlsnum
        record_result = {"mlsnum": mlsnum}
        total_tokens = 0

        for rule_id, columns in ai_rules.items():
            public_remarks = record.Remarks if "Remarks" in columns else ""
            private_remarks = record.PrivateRemarks if "PrivateRemarks" in columns else ""

            try:
                if rule_id.upper() == "FAIR":
                    result = await async_get_fair_housing(public_remarks, private_remarks)
                    total_tokens += result.get("Total_tokens", 0)
                elif rule_id.upper() == "COMP":
                    result = await async_get_comp(public_remarks, private_remarks)
                    total_tokens += result.get("Total_tokens", 0)
                else:
                    result = {"Remarks": [], "PrivateRemarks": []}

                # formatted = {
                #     "Remarks": [
                #         {
                #             "DetectedText": r.get("extracted_text", ""),
                #             "explanation": r.get("explanation", "")
                #         } for r in result.get("Remarks", [])
                #     ],
                #     "PrivateRemarks": [
                #         {
                #             "DetectedText": r.get("extracted_text", ""),
                #             "explanation": r.get("explanation", "")
                #         } for r in result.get("PrivateRemarks", [])
                #     ]
                # }

                record_result[rule_id.upper()] = result

            except Exception as e:
                record_result[rule_id.upper()] = {
                    "Remarks": [],
                    "PrivateRemarks": [],
                    "error": str(e)
                }

        latency = time.time() - start_time
        record_result["latency"] = latency
        record_result["tokens_used"] = total_tokens
        return record_result


async def process_all_records(request: ComplianceRequest, concurrency_limit: int = 10):
    ai_rules = {rule.ID: rule.CheckColumns.split(",") for rule in request.AIViolationID}
    semaphore = asyncio.Semaphore(concurrency_limit)
    start_time = time.time()

    tasks = [process_record(record, ai_rules, semaphore) for record in request.Data]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    total_tokens = sum(r["tokens_used"] for r in results if isinstance(r, dict))
    elapsed = time.time() - start_time
    clean_results = [r for r in results if isinstance(r, dict)]

    return APIResponse(
        ok=200,
        results= clean_results,
        error_message="",
        total_tokens=total_tokens,
        elapsed_time=elapsed
    )


# ---------------------------
# API Endpoint
# ---------------------------
@app.post("/check_compliance", response_model=APIResponse)
async def check_compliance(request: ComplianceRequest):
    if not request.Data:
        raise HTTPException(status_code=400, detail="Empty data list")

    try:
        return await process_all_records(request)
    except Exception as e:
        return APIResponse(ok=500, results=[], error_message=str(e))


# ---------------------------
# Health Check
# ---------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "AI Compliance Checker API is running!"}
