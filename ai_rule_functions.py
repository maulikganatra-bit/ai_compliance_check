from openai import OpenAI
from utils import response_parser
from dotenv import load_dotenv
load_dotenv()

client = OpenAI()

def get_fair_housing_violation_response(public_remarks: str, private_agent_remarks: str):
    response = client.responses.create(
        prompt={
            "id": "pmpt_68c29d3553688193b6d064d556ebc3c7039d675dbb8aefa0",
            "variables": {
                "public_remarks": public_remarks or "",
                "private_agent_remarks": private_agent_remarks or ""
            }
        }
    )

    json_content = response_parser(response.output_text)
    json_result = json_content['result']
    json_result['Remarks'] = json_result.pop('public_remarks', [])
    json_result['PrivateRemarks'] = json_result.pop('private_agent_remarks', [])
    json_result['Total_tokens'] = response.usage.total_tokens
    return json_result


def get_comp_violation_response(public_remarks: str, private_agent_remarks: str):
    response = client.responses.create(
        prompt={
            "id": "pmpt_6908794dae1c8195a2902ca8e69120d609db2ac6e42d0716",
            "variables": {
                "public_remarks": public_remarks or "",
                "private_agent_remarks": private_agent_remarks or ""
            }
        }
    )

    json_content = response_parser(response.output_text)
    json_result = json_content['result']
    json_result['Remarks'] = json_result.pop('public_remarks', [])
    json_result['PrivateRemarks'] = json_result.pop('private_agent_remarks', [])
    json_result['Total_tokens'] = response.usage.total_tokens

    return json_result
