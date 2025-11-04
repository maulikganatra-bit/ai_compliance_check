import requests
import json
import pandas as pd


# URL of your locally running API
url = "http://127.0.0.1:8000/check_compliance"
# url = "http://TMDWEBLA01/check_compliance"

# test_data = pd.read_csv("experiment_result_data/combined_compensation_violation_all_mls_gpt4o_judge_definate_labels.csv")
# test_data = test_data.dropna(subset=['CaseOpenRemarks',"PrivateRemarks"]).reset_index(drop=True)
# test_data = test_data.iloc[:1000]  # Testing with first 1000 rows
# test_data =test_data.rename(columns={"CaseOpenRemarks":"public","PrivateRemarks":"private"})
# data = test_data[['public','private']].to_dict(orient='records')
# Example data (you can add more pairs)
data = {
  "AIViolationID": [
    {
      "ID": "COMP",
      "CheckColumns": "Remarks, PrivateRemarks"
    },
    {
      "ID": "FAIR",
      "CheckColumns": "Remarks"
    }
  ],
  "Data": [
    {
      "mlsnum": "564564564OD",
      "Remarks": "Seller will consider offers.",
      "PrivateRemarks": "Agent will offer bonus if closed fast."
    },
    {
      "mlsnum": "564554564OD",
      "Remarks": "Buyer must verify all information.",
      "PrivateRemarks": "Seller is open to buyer concessions."
    }
  ]
}

# Make POST request
response = requests.post(url, json=data)
print(response.json())

# Print results
# if response.status_code == 200:
#     result = response.json()
#     with open("experiment_result_data/api_test_results.json", "w") as f:
#         json.dump(result, f, indent=4)
# else:
#     print(f"Error {response.status_code}: {response.text}")
