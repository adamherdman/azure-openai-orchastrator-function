#Prod_Test
import logging
import azure.functions as func
import os
import json
import requests
import openai
import re

# Global configurations
openai.api_type = "azure"
openai.api_version = "2023-08-01-preview"
openai.api_base = "https://openai-nwicb-innovation.openai.azure.com/"
openai.api_key = os.environ.get('OPENAI_API_KEY')
deployment_id = "gpt-35-turbo-test"

# Azure Cognitive Search configurations
search_endpoint = "https://cogsearch-nwicb-innovation.search.windows.net"
search_key = os.environ.get('SEARCH_API_KEY')
search_index_name = "cogsearch-nwicb-innovation-index"

# Environment variable configurations
AZURE_SEARCH_CONTENT_COLUMNS = os.environ.get("AZURE_SEARCH_CONTENT_COLUMNS")
AZURE_SEARCH_FILENAME_COLUMN = os.environ.get("AZURE_SEARCH_FILENAME_COLUMN")
AZURE_SEARCH_TITLE_COLUMN = os.environ.get("AZURE_SEARCH_TITLE_COLUMN")
AZURE_SEARCH_URL_COLUMN = os.environ.get("AZURE_SEARCH_URL_COLUMN")
AZURE_SEARCH_VECTOR_COLUMNS = os.environ.get("AZURE_SEARCH_VECTOR_COLUMNS")
AZURE_SEARCH_TOP_K = os.environ.get("AZURE_SEARCH_TOP_K", 3)
AZURE_SEARCH_QUERY_TYPE = os.environ.get("AZURE_SEARCH_QUERY_TYPE")
AZURE_SEARCH_STRICTNESS = os.environ.get("AZURE_SEARCH_STRICTNESS", 3)
AZURE_SEARCH_ENABLE_IN_DOMAIN = os.environ.get("AZURE_SEARCH_ENABLE_IN_DOMAIN", "true")
AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG = os.environ.get("AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG", "default")


AZURE_OPENAI_SYSTEM_MESSAGE = os.environ.get("AZURE_OPENAI_SYSTEM_MESSAGE", "You are an AI assistant that helps people find information.")
AZURE_OPENAI_TOP_P = os.environ.get("AZURE_OPENAI_TOP_P", 1.0)
AZURE_OPENAI_MAX_TOKENS = os.environ.get("AZURE_OPENAI_MAX_TOKENS", 1000)
AZURE_OPENAI_TEMPERATURE = os.environ.get("AZURE_OPENAI_TEMPERATURE", 0)


def prepare_body_headers_with_data(question: str) -> tuple:
    # Set query type
    query_type = "simple"

    # Set filter
    filter = None

    # Prepare the body for the request to OpenAI
    body = {
        "messages": [{"role": "user", "content": question}],
        "temperature": float(AZURE_OPENAI_TEMPERATURE),
        "max_tokens": int(AZURE_OPENAI_MAX_TOKENS),
        "top_p": float(AZURE_OPENAI_TOP_P),

        "dataSources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": search_endpoint,
                    "key": search_key,
                    "indexName": search_index_name,
                    "fieldsMapping": {
                        "contentFields": AZURE_SEARCH_CONTENT_COLUMNS.split("|") if AZURE_SEARCH_CONTENT_COLUMNS else [],
                        "titleField": AZURE_SEARCH_TITLE_COLUMN if AZURE_SEARCH_TITLE_COLUMN else None,
                        "urlField": AZURE_SEARCH_URL_COLUMN if AZURE_SEARCH_URL_COLUMN else None,
                        "filepathField": AZURE_SEARCH_FILENAME_COLUMN if AZURE_SEARCH_FILENAME_COLUMN else None,
                        "vectorFields": AZURE_SEARCH_VECTOR_COLUMNS.split("|") if AZURE_SEARCH_VECTOR_COLUMNS else []
                    },
                    "inScope": True if AZURE_SEARCH_ENABLE_IN_DOMAIN.lower() == "true" else False,
                    "topNDocuments": AZURE_SEARCH_TOP_K,
                    "queryType": query_type,
                    "semanticConfiguration": AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG if AZURE_SEARCH_SEMANTIC_SEARCH_CONFIG else "",
                    "roleInformation": AZURE_OPENAI_SYSTEM_MESSAGE,
                    "filter": filter,
                    "strictness": int(AZURE_SEARCH_STRICTNESS)
                }
            }
        ]
    }

    headers = {
        'Content-Type': 'application/json',
        'api-key': openai.api_key,
        "x-ms-useragent": "GitHubSampleWebApp/PublicAPI/2.0.0"
    }

    return body, headers

def handle_request_logic(body, headers, deployment_id):
    try:
        # Construct the URL to interact with a specific deployment and extension
        url = f"{openai.api_base}openai/deployments/{deployment_id}/extensions/chat/completions?api-version={openai.api_version}"
        
        # Make API call to OpenAI
        response = requests.post(
            url=url,
            headers=headers,
            json=body
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        if response is not None:
            logging.error(f"Response Status Code: {response.status_code}")
            logging.error(f"Response Text: {response.text}")
        return None  # or however you want to handle failures

    # Parse the response
    response_data = response.json()
    logging.info(f"Response Data: {response_data}")
    # Extracting answer from response data (assuming it's structured in a certain way)
    answer = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

    
    
    # Extract file paths from the response
    filepaths_pattern = r'"filepath": "([^"]+)"'
    
    # Extract file paths from the response
    filepaths_pattern = r'"filepath": "([^"]+)"'
    filepaths = re.findall(filepaths_pattern, str(response_data))

    original_answer = answer  # Store the original answer for fallback

    # Replace placeholders with corresponding URLs
    for i, filepath in enumerate(filepaths):
        placeholder = f"[doc{i+1}]"
        answer = answer.replace(placeholder, "<a href=\"" + filepath + "\">doc" + str(i + 1) + "</a> ")

    # If answer is empty or has remaining placeholders, use the original answer
    if not answer or re.search(r'\[doc\d+\]', answer):
        answer = original_answer

    return {
        'answer': answer,
    }


    # Replace placeholders with corresponding URLs
    for i, filepath in enumerate(filepaths):
        placeholder = f"[doc{i+1}]"
        answer = answer.replace(placeholder, "<a href=\"" + filepath + "\">doc" + str(i + 1) + "</a> ")

    return {
        'answer': answer,
    }

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # Extract question from query parameters
    question = req.params.get('question')
    if not question:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            question = req_body.get('question')

    if not question or not isinstance(question, str):
        return func.HttpResponse(
            body=json.dumps({"error": "Missing or invalid question parameter"}),
            mimetype="application/json",
            status_code=400
        )

    try:  # This try block should be indented to be inside the main function
        body, headers = prepare_body_headers_with_data(question)

        # Assuming you have a function to handle the logic and get the response
        response_data = handle_request_logic(body, headers, deployment_id)  # You need to define handle_request_logic
        if response_data is None:
            return func.HttpResponse(
                body=json.dumps({"error": "Failed to get a response from OpenAI"}),
                mimetype="application/json",
                status_code=500
            )
        # Prepare response based on Swagger spec
        response_body = {
            "answer": response_data.get('answer', ''),
        }


        return func.HttpResponse(
            body=json.dumps(response_body),
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f'Exception: {e}')
        return func.HttpResponse(
            body=json.dumps({"error": f"An error occurred: {e}"}),
            mimetype="application/json",
            status_code=500
        )
