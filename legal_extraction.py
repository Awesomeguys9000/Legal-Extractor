import os
import time
import argparse
import json
from google import genai
from google.genai import types

def extract_legal_data(pdf_path, model_name="gemini-3-flash-preview", api_key=None):
    """
    Uploads a PDF to Google Gemini and extracts legal data.
    
    Args:
        pdf_path: Path to the PDF file.
        model_name: Name of the Gemini model to use.
        api_key: Optional API key. If not provided, uses GEMINI_API_KEY env var.
        
    Returns:
        JSON string containing the extracted data.
    """
    # Try multiple sources for API key:
    # 1. Passed parameter (from app.py input field)
    # 2. Streamlit secrets (for Streamlit Cloud hosting)
    # 3. Environment variable (for local dev)
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except:
            pass
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No API key provided. Please enter your Gemini API key.")

    client = genai.Client(api_key=api_key)

    print(f"Uploading file: {pdf_path}...")
    print(f"Uploading file: {pdf_path}...")
    # Upload the file
    file_upload = client.files.upload(file=pdf_path)
    print(f"Uploaded file: {file_upload.name}")

    # Wait for the file to be processed
    print("Waiting for file processing...")
    while file_upload.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        file_upload = client.files.get(name=file_upload.name)
    print()

    if file_upload.state.name != "ACTIVE":
        raise RuntimeError(f"File processing failed. State: {file_upload.state.name}")

    print("File is ACTIVE. Generating content...")

    prompt = """
    You are a legal AI assistant. Extract each of the key dates in the provided file.
    Common fields include: Contract Date, Settlement Date, Finance Date, etc.
    
    3. **Date Calculation**:
       - If a date is relative (e.g., "3 days after Contract Date"), and the referenced date is available in the document, YOU MUST CALCULATE the actual date (DD-MM-YYYY) and return it as the "value".
       - If calculation is impossible (e.g., referenced date missing), return the relative description as the "value".
    
    Return a single JSON object where:
    - The keys are the descriptive names of the fields (e.g., "Contract Date").
    - The values are objects with THREE keys: 
        1. "value": The extracted date formatted as DD-MM-YYYY. If the date is relative, return the relative description. If null/not found, return null.
        2. "verbatim_quote": The exact substring from the text. Return null if not applicable.
        3. "page_number": The integer page number where this information is found. **You must provide a page number estimate even if the value is null or handwritten.**
    """

    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri=file_upload.uri,
                        mime_type=file_upload.mime_type,
                    ),
                    types.Part.from_text(text=prompt),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return response.text
    
def list_models():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    
    client = genai.Client(api_key=api_key)
    print("Listing available models...")
    for model in client.models.list():
        print(f"- {model.name}")
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract legal data from a PDF using Google Gemini.")
    parser.add_argument("pdf_path", nargs="?", help="Path to the PDF file")
    parser.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model to use (default: gemini-3-flash-preview)")
    parser.add_argument("--refresh-models", action="store_true", help="List available models")

    args = parser.parse_args()

    if args.refresh_models:
        list_models()
    elif args.pdf_path:
        if not os.path.exists(args.pdf_path):
            print(f"Error: File not found at {args.pdf_path}")
        else:
            result = extract_legal_data(args.pdf_path, args.model)
            if result:
                print("\nMetadata Verification:")
                # Pretty print the JSON to verify it parses
                try:
                    parsed = json.loads(result)
                    print(json.dumps(parsed, indent=2))
                except json.JSONDecodeError:
                    print("Raw Output (Not valid JSON):")
                    print(result)
    else:
        parser.print_help()
