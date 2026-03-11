
import requests
import json
import logging
from app.core.logger import setup_logger
# Setup test logger
test_logger = setup_logger('test.api', logging.INFO)
# URL of your locally running API
url = "http://127.0.0.1:8000/check_compliance"
# url = "http://tmcailinux03.vesta.themls.com:8000/check_compliance"monitoring/
# url = "http://tmqailinux01.qa.themls.com:8000/check_compliance"

# with open("./test_data/large_payload.json", "r") as f:
#     data = json.load(f)

data = {
  "AIViolationID": [
    {
      "ID": "COMP",
      "mlsId": "ARMls",
      "CheckColumns": "Remarks, Directions"
    },
    {
      "ID": "PROMO",
      "mlsId": "ARMls",
      "CheckColumns": "Remarks,Directions"
    }
    # {
    #   "ID": "PROMO",
    #   "mlsId": "ARMls",
    #   "CheckColumns": "Directions"
    # }
  ],
  "Data": [
    {
      "mlsnum": "6942376AR",
      "Remarks": "Owner Carry 15% down. Move IN READY-ALL INCLUSIVE.Fountain & Mountains-no one above no one below. Beautiful Townhome Open Concept travertine floors, Kit. granite countertops to include custom sitting bar.Upgraded stainless appliance package to include upgraded refrigerator-in home wash\/dryer included.Shutters. Bath down has a collapsible accordion door - everything upgraded and beautiful. Kit. has a extra 15 ft of upper and lower cabinets.Elegant Stairs w\/travertine risers and solid wood leads to a nice size landing enough room for a desk. 2 bedrooms upstairs-Very large master has 2 closets one step in closet. Enclosed carport with storage and another refrigerator. Pool steps away and grass area. Super nice - 2nd BDR furniture will not stay.",
      "Directions": "GPS Saguaro Woods\r\nVRBO ready - furnished just bring your suitcase\r\n\r\nA\/C One year new - Furnished if they like !!\r\n\r\nOwner\/Agent",
      "ShowingInstructions": "",
      "PrivateRemarks": "",
      "mlsId": "ARMls"
    }
  ]
}
# # data = {
# #   "AIViolationID": [
# #     {
# #       "ID": "COMP",
# #       "CheckColumns": "Remarks,PrivateRemarks"
# #     },
# #     {
# #       "ID": "FAIR",
# #       "CheckColumns": "Remarks"
# #     },
# #     {"ID": "PROMO",
# #       "CheckColumns": "Remarks,PrivateRemarks"
# #     }
# #   ],
# #   "Data": [
# #     {
# #       "mlsnum": "564564564OD",
# #       "mlsId": "TESTMLS",
# #       "Remarks": "Seller will consider offers.",
# #       "PrivateRemarks": "Agent will offer bonus if closed fast.",
# #       "Directions": "Take Main St. to 5th Ave."
# #     },
# #     {
# #       "mlsnum": "564554564OD",
# #       "mlsId": "TESTMLS",
# #       "Remarks": "contact agent on 704-555-1234 for more info.",
# #       "PrivateRemarks": "Seller is open to buyer concessions."
# #     }
# #   ]
# # }

def test_compliance_api():
    test_logger.info("Starting API compliance test")
    test_logger.debug(f"Sending request to {url}")
    headers = {
    "Content-Type": "application/json",
    "X-API-Key": "7WrnLmLsXRepOo7f2CRwmcnQFSEo0e7e2DR7qZVId8Q"
}
    
    response = requests.post(url, json=data, headers=headers)
    test_logger.info(f"Received response with status code: {response.status_code}")

    # Assert status code is 200 for pytest compatibility
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"

    result = response.json()
    test_logger.info(f"Test passed! Processed {len(result['results'])} records")
    test_logger.info(f"Total tokens used: {result['total_tokens']}, Elapsed time: {result['elapsed_time']:.2f}s")

    # If the server returns the request ID only in the header, copy it into the
    # saved JSON so offline consumers can correlate results with server logs.
    
    if "request_id" not in result and "X-Request-ID" in response.headers:
      result["request_id"] = response.headers["X-Request-ID"]

    with open("tests/test_results.json", "w") as f:
      json.dump(result, f, indent=4)
    test_logger.info("Results saved to tests/test_results.json")

if __name__ == "__main__":
    test_compliance_api()
