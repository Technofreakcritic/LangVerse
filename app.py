import streamlit as st
import requests
import json
import openai
import time
import tempfile
import os
import zipfile

st.set_page_config(page_title="Webflow Content Manager", layout="wide")

def get_pages(site_id, api_key):
    """Get list of pages with their IDs"""
    url = f"https://api.webflow.com/v2/sites/{site_id}/pages"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    
    print(f"\n[DEBUG] Fetching pages from URL: {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        pages = response.json()["pages"]
        print(f"[DEBUG] Successfully fetched {len(pages)} pages")
        return pages
    except Exception as e:
        print(f"[DEBUG] Error fetching pages: {str(e)}")
        st.error(f"Error fetching pages: {str(e)}")
        return []

def get_site_locales(site_id, api_key):
    """Get list of locales with their IDs"""
    url = f"https://api.webflow.com/v2/sites/{site_id}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        locales = []
        # Add primary locale
        primary = data.get('locales', {}).get('primary', {})
        if primary:
            primary['type'] = 'Primary'
            locales.append(primary)
        
        # Add secondary locales
        secondary = data.get('locales', {}).get('secondary', [])
        for locale in secondary:
            locale['type'] = 'Secondary'
            locales.append(locale)
            
        return locales
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        st.error(f"Error fetching site locales: {str(e)}")
        return []

def get_page_content(page_id, api_key):
    """Get page content using DOM endpoint"""
    url = f"https://api.webflow.com/v2/pages/{page_id}/dom"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}",
        "accept-version": "1.0.0"
    }
    
    print("\n" + "="*50)
    print("API REQUEST - Get Page Content")
    print("="*50)
    print(f"URL: {url}")
    print("\nHeaders:")
    for key, value in headers.items():
        if key.lower() == 'authorization':
            print(f"{key}: Bearer ****{value[-4:]}")
        else:
            print(f"{key}: {value}")
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Print the complete API response
        print("\n" + "="*50)
        print("COMPLETE API RESPONSE")
        print("="*50)
        print(json.dumps(data, indent=2))
        
        return data
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        st.error(f"Error fetching page content: {str(e)}")
        return None

def validate_api_token(api_key):
    """Validate API token by making a test request"""
    url = "https://api.webflow.com/v2/sites"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            st.error("Invalid API token. Please check your token and ensure it has the required permissions (pages:read)")
        elif e.response.status_code == 403:
            st.error("API token doesn't have the required permissions. Please ensure it has 'pages:read' scope")
        else:
            st.error(f"API Error: {str(e)}")
        return False
    except Exception as e:
        st.error(f"Connection Error: {str(e)}")
        return False

def parse_page_content(content):
    """Parse page content and extract nodes with property overrides"""
    parsed_nodes = []
    
    for node in content.get('nodes', []):
        # Only process nodes that have propertyOverrides
        if node.get('propertyOverrides'):
            node_data = {
                "nodeId": node['id'],
                "propertyOverrides": []
            }
            
            # Extract property overrides that have text content
            for override in node['propertyOverrides']:
                if 'propertyId' in override and 'text' in override:
                    property_data = {
                        "propertyId": override['propertyId'],
                        "text": override['text'].get('text', '')  # Get the text value
                    }
                    node_data["propertyOverrides"].append(property_data)
            
            if node_data["propertyOverrides"]:  # Only add if there are property overrides
                parsed_nodes.append(node_data)
    
    return parsed_nodes

def display_curl_commands(page_id, locale_id, api_key, nodes):
    """Display curl commands for each node"""
    st.subheader("Generated CURL Commands")
    
    for node in nodes:
        for prop in node["propertyOverrides"]:
            curl_command = f"""curl -X POST "https://api.webflow.com/v2/pages/{page_id}/dom?localeId={locale_id}" \\
     -H "Authorization: Bearer {api_key}" \\
     -H "Content-Type: application/json" \\
     -d '{{
  "nodes": [
    {{
      "nodeId": "{node['nodeId']}",
      "propertyOverrides": [
        {{
          "propertyId": "{prop['propertyId']}",
          "text": "{prop['text']}"
        }}
      ]
    }}
  ]
}}'"""
            st.code(curl_command, language="bash")
            st.markdown("---")

def translate_content_with_openai(parsed_nodes, target_language, api_key):
    """Translate content using OpenAI while preserving JSON structure"""
    try:
        # First verify we have valid inputs
        if not parsed_nodes:
            return None, "No content to translate"
        if not target_language:
            return None, "No target language specified"
        if not api_key:
            return None, "OpenAI API key is missing"
            
        client = openai.OpenAI(api_key=api_key)
        
        # Print debug information
        print("\n" + "="*50)
        print("TRANSLATION REQUEST")
        print("="*50)
        print(f"Target Language: {target_language}")
        print("Content to translate:")
        print(json.dumps(parsed_nodes, indent=2))
        
        # Prepare the system message explaining what we want
        system_message = f"""You are a professional translator. 
        Translate only the "text" values in the JSON to {target_language}. 
        Keep all other JSON structure and values exactly the same.
        Return only the JSON, no explanations."""
        
        # Prepare the JSON for translation
        user_message = f"Translate this JSON content. Original JSON:\n{json.dumps(parsed_nodes, indent=2)}"
        
        # Make the API call with new syntax
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3
            )
            
            # Print the raw response for debugging
            print("\nOpenAI Response:")
            print(response)
            
            # Extract and validate the response content
            response_content = response.choices[0].message.content
            if not response_content:
                return None, "Empty response from OpenAI"
                
            # Try to parse the JSON response
            try:
                translated_json = json.loads(response_content)
                return translated_json, None
            except json.JSONDecodeError as e:
                print(f"JSON Parse Error: {str(e)}")
                print("Raw response content:")
                print(response_content)
                return None, f"Failed to parse OpenAI response as JSON: {str(e)}"
                
        except Exception as e:
            print(f"OpenAI API Error: {str(e)}")
            return None, f"OpenAI API Error: {str(e)}"
            
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        return None, f"Translation error: {str(e)}"

def update_page_content(page_id, locale_id, api_key, translated_content):
    """Update page content with translated text"""
    url = f"https://api.webflow.com/v2/pages/{page_id}/dom?localeId={locale_id}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json"
    }
    
    # Restructure the translated content to match API requirements
    request_body = {
        "nodes": []
    }
    
    # Convert translated content into the correct format
    for node in translated_content:
        node_data = {
            "nodeId": node["nodeId"]
        }
        
        if "propertyOverrides" in node:
            node_data["propertyOverrides"] = []
            for override in node["propertyOverrides"]:
                node_data["propertyOverrides"].append({
                    "propertyId": override["propertyId"],
                    "text": override["text"]
                })
        
        request_body["nodes"].append(node_data)
    
    print("\n" + "="*50)
    print("UPDATE PAGE CONTENT REQUEST")
    print("="*50)
    print(f"URL: {url}")
    print("\nHeaders:")
    for key, value in headers.items():
        if key.lower() == 'authorization':
            print(f"{key}: Bearer ****{value[-4:]}")
        else:
            print(f"{key}: {value}")
    
    print("\nPayload:")
    print(json.dumps(request_body, indent=2))
    
    try:
        response = requests.post(url, headers=headers, json=request_body)
        
        print("\n" + "="*50)
        print("API RESPONSE")
        print("="*50)
        print(f"Status Code: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except:
            print(response.text)
            
        response.raise_for_status()
        return True, None
    except Exception as e:
        error_message = str(e)
        print(f"\nERROR: {error_message}")
        return False, error_message

def main():
    st.title("Webflow Content Manager")
    
    # Initialize session state
    if 'site_id' not in st.session_state:
        st.session_state.site_id = ''
    if 'api_key' not in st.session_state:
        st.session_state.api_key = ''
    if 'pages' not in st.session_state:
        st.session_state.pages = []
    if 'locales' not in st.session_state:
        st.session_state.locales = []
    if 'openai_key' not in st.session_state:
        st.session_state.openai_key = ''
    if 'current_content' not in st.session_state:
        st.session_state.current_content = None
    if 'parsed_nodes' not in st.session_state:
        st.session_state.parsed_nodes = None
    
    # Print current session state
    print("\nCurrent Session State:")
    print(f"Has site_id: {bool(st.session_state.site_id)}")
    print(f"Has api_key: {bool(st.session_state.api_key)}")
    print(f"Number of pages: {len(st.session_state.pages)}")
    print(f"Number of locales: {len(st.session_state.locales)}")
    print(f"Has OpenAI key: {bool(st.session_state.openai_key)}")
    print(f"Has current content: {bool(st.session_state.current_content)}")
    
    # Add OpenAI API key input in sidebar
    with st.sidebar:
        st.subheader("OpenAI Configuration")
        openai_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.openai_key,
            help="Your OpenAI API key for translations"
        )
        if openai_key:
            st.session_state.openai_key = openai_key
    
    # Step 1: Get API Token and Site ID
    with st.form("credentials_form"):
        # Add help text for API token
        st.markdown("""
        ### API Token Requirements
        - Must be a valid Webflow API token
        - Requires `pages:read` scope
        - Format: Bearer token
        """)
        
        site_id = st.text_input(
            "Site ID", 
            value=st.session_state.site_id,
            help="The unique identifier for your Webflow site"
        )
        api_key = st.text_input(
            "API Key", 
            type="password", 
            value=st.session_state.api_key,
            help="Your Webflow API token with pages:read scope"
        )
        submit_button = st.form_submit_button("Validate & Fetch Site Data")
    
    if submit_button:
        # First validate the API token
        if validate_api_token(api_key):
            st.success("API token validated successfully!")
            st.session_state.site_id = site_id
            st.session_state.api_key = api_key
            
            # Step 2: Get Pages and Locales
            with st.spinner("Fetching site data..."):
                # Get and display locales
                locales = get_site_locales(site_id, api_key)
                if locales:
                    st.session_state.locales = locales
                    st.subheader("Available Locales")
                    locale_data = {
                        "Type": [locale.get('type', 'Unknown') for locale in locales],
                        "Display Name": [locale.get('displayName', 'Unnamed') for locale in locales],
                        "Locale ID": [locale.get('id', 'No ID') for locale in locales],
                        "Tag": [locale.get('tag', 'No tag') for locale in locales]
                    }
                    st.table(locale_data)
                
                # Get and display pages
                pages = get_pages(site_id, api_key)
                if pages:
                    st.session_state.pages = pages
                    st.subheader("Available Pages")
                    page_data = {
                        "Title": [page.get('title', 'Untitled') for page in pages],
                        "Page ID": [page['id'] for page in pages],
                        "Slug": [page.get('slug', 'No slug') for page in pages]
                    }
                    st.table(page_data)
    
    # Page selection and content viewing
    if st.session_state.pages:
        st.subheader("View Page Content")
        selected_page = st.selectbox(
            "Select a page",
            options=[f"{page.get('title', 'Untitled')} ({page['id']})" for page in st.session_state.pages],
            key="page_selector"
        )
        
        if selected_page:
            page_id = selected_page.split('(')[-1].strip(')')
            
            # View content button
            if st.button("View Content", key="view_content_button"):
                with st.spinner("Fetching page content..."):
                    content = get_page_content(page_id, st.session_state.api_key)
                    if content:
                        st.session_state.current_content = content
                        st.session_state.parsed_nodes = parse_page_content(content)
            
            # Display content if available
            if st.session_state.current_content:
                st.subheader("Raw Page Content")
                st.json(st.session_state.current_content)
                
                st.subheader("Parsed Nodes with Property Overrides")
                st.json(st.session_state.parsed_nodes)
                
                # Translation section
                if st.session_state.openai_key and st.session_state.locales:
                    st.subheader("Translate Content")
                    
                    # Create language selection with both tag and ID
                    locale_options = {
                        f"{locale.get('displayName', 'Unnamed')} ({locale.get('tag', 'No tag')})": {
                            'tag': locale.get('tag', 'unknown'),
                            'id': locale.get('id')
                        }
                        for locale in st.session_state.locales
                    }
                    
                    # Multi-select for languages
                    target_languages = st.multiselect(
                        "Select target languages",
                        options=list(locale_options.keys()),
                        key="translate_languages_select"
                    )
                    
                    if st.button("Translate to Selected Languages", key="translate_button"):
                        if not target_languages:
                            st.warning("Please select at least one language")
                            return
                            
                        print(f"\nTranslating to {len(target_languages)} languages")
                        
                        # Create a progress bar
                        progress_bar = st.progress(0)
                        translation_status = st.empty()
                        
                        # Process each language
                        for index, target_language in enumerate(target_languages):
                            translation_status.text(f"Processing {target_language} ({index + 1}/{len(target_languages)})")
                            print(f"\nProcessing language: {target_language}")
                            
                            with st.spinner(f"Translating to {target_language}..."):
                                # Use the language tag for translation
                                translated_content, error = translate_content_with_openai(
                                    st.session_state.parsed_nodes,
                                    locale_options[target_language]['tag'],
                                    st.session_state.openai_key
                                )
                                
                                if error:
                                    st.error(f"Error translating to {target_language}: {error}")
                                    continue
                                
                                # Get the locale ID for the API call
                                locale_id = locale_options[target_language]['id']
                                print(f"\nUsing locale ID: {locale_id}")
                                print(f"Language tag: {locale_options[target_language]['tag']}")
                                
                                # Create an expander for each language's details
                                with st.expander(f"Translation Details - {target_language}", expanded=False):
                                    st.subheader("Translated Content")
                                    st.json(translated_content)
                                
                                # Update the page content with translated text
                                print(f"\nUpdating page content for {target_language}...")
                                success, error = update_page_content(
                                    page_id=page_id,
                                    locale_id=locale_id,
                                    api_key=st.session_state.api_key,
                                    translated_content=translated_content
                                )
                                
                                if success:
                                    st.success(f"Successfully updated content for {target_language}")
                                else:
                                    st.error(f"Failed to update content for {target_language}: {error}")
                                
                                # Update progress
                                progress = (index + 1) / len(target_languages)
                                progress_bar.progress(progress)
                                
                                # Add a small delay between requests to avoid rate limits
                                time.sleep(1)
                        
                        translation_status.text("All translations completed!")
                        
                        # Create a zip file with all translations
                        if st.button("Download All Translations", key="download_all"):
                            with st.spinner("Preparing download..."):
                                # Create a temporary directory for the files
                                with tempfile.TemporaryDirectory() as temp_dir:
                                    # Save each translation to a file
                                    for target_language in target_languages:
                                        translated_content, _ = translate_content_with_openai(
                                            st.session_state.parsed_nodes,
                                            locale_options[target_language]['tag'],
                                            st.session_state.openai_key
                                        )
                                        
                                        if translated_content:
                                            file_path = os.path.join(
                                                temp_dir, 
                                                f"translation_{locale_options[target_language]['tag']}.json"
                                            )
                                            with open(file_path, 'w') as f:
                                                json.dump(translated_content, f, indent=2)
                                    
                                    # Create zip file
                                    zip_path = os.path.join(temp_dir, "translations.zip")
                                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                                        for file in os.listdir(temp_dir):
                                            if file.endswith('.json'):
                                                zipf.write(
                                                    os.path.join(temp_dir, file),
                                                    file
                                                )
                                    
                                    # Read the zip file for download
                                    with open(zip_path, 'rb') as f:
                                        st.download_button(
                                            label="Download Translations ZIP",
                                            data=f.read(),
                                            file_name="translations.zip",
                                            mime="application/zip"
                                        )
                else:
                    if not st.session_state.openai_key:
                        st.warning("Please add your OpenAI API key in the sidebar to enable translations")
                    if not st.session_state.locales:
                        st.warning("No locales available for translation")

if __name__ == "__main__":
    main()
