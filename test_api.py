
import requests
import json
import logging
from app.core.logger import setup_logger
# Setup test logger
test_logger = setup_logger('test.api', logging.INFO)
# URL of your locally running API
url = "http://127.0.0.1:8000/check_compliance"
data = {
  "AIViolationID": [
    {
      "ID": "COMP",
      "CheckColumns": "Remarks,PrivateRemarks"
    },
    {
      "ID": "FAIR",
      "CheckColumns": "Remarks"
    },
    {"ID": "PROMO",
      "CheckColumns": "Remarks,PrivateRemarks"
    }
  ],
  "Data": [
    {
      "mlsnum": "564564564OD",
      "mls_id": "TESTMLS",
      "Remarks": "Seller will consider offers.",
      "PrivateRemarks": "Agent will offer bonus if closed fast.",
      "Directions": "Take Main St. to 5th Ave."
    },
    {
      "mlsnum": "564554564OD",
      "mls_id": "TESTMLS",
      "Remarks": "contact agent on 704-555-1234 for more info.",
      "PrivateRemarks": "Seller is open to buyer concessions."
    }
  ]
}
def test_compliance_api():
    test_logger.info("Starting API compliance test")
    test_logger.debug(f"Sending request to {url}")
    
    try:
        response = requests.post(url, json=data)
        test_logger.info(f"Received response with status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            test_logger.info(f"Test passed! Processed {len(result['results'])} records")
            test_logger.info(f"Total tokens used: {result['total_tokens']}, Elapsed time: {result['elapsed_time']:.2f}s")
            
            with open("tests/test_results.json", "w") as f:
                json.dump(result, f, indent=4)
            test_logger.info("Results saved to tests/test_results.json")
            
            return True
        else:
            test_logger.error(f"Test failed! Status code: {response.status_code}")
            test_logger.error(f"Response: {response.text}")
            return False
    except Exception as e:
        test_logger.error(f"Error during test: {str(e)}", exc_info=True)
        return False
if __name__ == "__main__":
    test_compliance_api()
