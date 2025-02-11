import streamlit as st
import requests
import json
import openai
import time
import tempfile
import os
import zipfile

# Hide the default menu
st.set_page_config(
    page_title="Webflow Content Manager", 
    layout="wide"
)



# Initialize session state
if 'site_id' not in st.session_state:
    st.session_state.site_id = ''
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
if 'openai_key' not in st.session_state:
    st.session_state.openai_key = ''
if 'components' not in st.session_state:
    st.session_state.components = []
if 'current_component_content' not in st.session_state:
    st.session_state.current_component_content = None
if 'parsed_nodes' not in st.session_state:
    st.session_state.parsed_nodes = None
if 'selected_component' not in st.session_state:
    st.session_state.selected_component = None
if 'translated_content' not in st.session_state:
    st.session_state.translated_content = None
if 'translation_requested' not in st.session_state:
    st.session_state.translation_requested = False
if 'target_language' not in st.session_state:
    st.session_state.target_language = None
if 'translation_started' not in st.session_state:
    st.session_state.translation_started = False
if 'selected_languages' not in st.session_state:
    st.session_state.selected_languages = []
if 'translation_progress' not in st.session_state:
    st.session_state.translation_progress = 0

# Add sidebar configuration
with st.sidebar:
    st.title("Navigation")
    
    # Navigation with radio buttons
    page = st.radio(
        "Select Page",  # Added proper label
        ["Page Content", "Static Elements"],
        index=1,  # Default to Static Elements
        key="navigation"
    )
    
    if page == "Page Content":
        st.switch_page("app.py")  # Make sure this path is correct
    
    st.divider()
    
    # OpenAI Configuration
    st.subheader("OpenAI Configuration")
    openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=st.session_state.openai_key,
        help="Your OpenAI API key for translations"
    )
    if openai_key:
        st.session_state.openai_key = openai_key

def get_site_components(site_id, api_key):
    """Get list of components from the site"""
    url = f"https://api.webflow.com/v2/sites/{site_id}/components"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    
    print(f"\n[DEBUG] Fetching components from URL: {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        components = response.json()["components"]
        print(f"[DEBUG] Successfully fetched {len(components)} components")
        return components
    except Exception as e:
        print(f"[DEBUG] Error fetching components: {str(e)}")
        st.error(f"Error fetching components: {str(e)}")
        return []

def get_component_content(site_id, component_id, api_key):
    """Get component content using DOM endpoint"""
    url = f"https://api.webflow.com/v2/sites/{site_id}/components/{component_id}/dom"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}",
        "accept-version": "1.0.0"
    }
    
    print("\n" + "="*50)
    print("API REQUEST - Get Component Content")
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
        st.error(f"Error fetching component content: {str(e)}")
        return None

def parse_component_content(content):
    """Parse component content to extract node IDs and HTML"""
    parsed_nodes = []
    
    for node in content.get('nodes', []):
        # Only include nodes that have non-empty html
        if node.get('text', {}).get('html'):
            node_data = {
                "nodeId": node['id'],
                "text": node['text']['html']  # Getting HTML instead of plain text
            }
            parsed_nodes.append(node_data)
    
    return {"nodes": parsed_nodes}

def get_site_locales(site_id, api_key):
    """Get list of locales with their IDs"""
    url = f"https://api.webflow.com/v2/sites/{site_id}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}"
    }
    
    print(f"\n[DEBUG] Fetching site locales from URL: {url}")
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
            
        print(f"[DEBUG] Successfully fetched {len(locales)} locales")
        return locales
    except Exception as e:
        print(f"[DEBUG] Error fetching locales: {str(e)}")
        st.error(f"Error fetching site locales: {str(e)}")
        return []

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
        system_message = f"""You are a professional translator with 20 years of experience.  
        Translate only the "text" values in the JSON to {target_language}. 
        Follow these rules when translating:

        - When encountering the word "Deriv" and any succeeding word, analyze the context and based on it, keep it in English. For example, "Deriv Blog," "Deriv Life," "Deriv Bot," and "Deriv App" should be kept in English.
        - Keep product names such as P2P, MT5, Deriv X, Deriv cTrader, SmartTrader, Deriv Trader, Deriv GO, Deriv Bot, and Binary Bot in English.
        
        Keep all other JSON structure and values exactly the same.
        Return only the JSON, no explanations."""
        
        # Prepare the JSON for translation
        user_message = f"Translate this JSON content. Original JSON:\n{json.dumps(parsed_nodes, indent=2)}"
        
        # Make the API call
        try:
            response = client.chat.completions.create(
                model="gpt-4",
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

def update_component_content(site_id, component_id, locale_id, nodes, api_key):
    """Update component content with translated text"""
    # Updated URL structure to match the API specification
    url = f"https://api.webflow.com/v2/sites/{site_id}/components/{component_id}/dom?localeId={locale_id}"
    
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json"
    }
    
    payload = {
        "nodes": nodes
    }
    
    print("\n" + "="*50)
    print("UPDATE COMPONENT CONTENT REQUEST")
    print("="*50)
    print(f"URL: {url}")
    print(f"Locale ID: {locale_id}")
    print("\nHeaders:")
    for key, value in headers.items():
        if key.lower() == 'authorization':
            print(f"{key}: Bearer ****{value[-4:]}")
        else:
            print(f"{key}: {value}")
    print("\nPayload:")
    print(json.dumps(payload, indent=2))
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        print("\nResponse Status:", response.status_code)
        print("Response Body:", response.text)
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        error_msg = f"Error updating component content: {str(e)}"
        print(f"\nERROR: {error_msg}")
        return None, error_msg

def main():
    st.title("Static Elements Manager")
    
    # 1. Credentials Form
    with st.form("credentials_form"):
        site_id = st.text_input(
            "Site ID", 
            value=st.session_state.site_id,
            help="The unique identifier for your Webflow site"
        )
        api_key = st.text_input(
            "API Key", 
            type="password", 
            value=st.session_state.api_key,
            help="Your Webflow API token"
        )
        submit_button = st.form_submit_button("Save Credentials")
    
    if submit_button:
        st.session_state.site_id = site_id
        st.session_state.api_key = api_key
        st.success("Credentials saved!")
    
    # Check if credentials are set
    if not st.session_state.api_key or not st.session_state.site_id:
        st.warning("Please set your Webflow API key and Site ID above")
        st.stop()
    
    # 2. Fetch and Display Locales
    if 'locales' not in st.session_state:
        with st.spinner("Fetching site locales..."):
            locales = get_site_locales(st.session_state.site_id, st.session_state.api_key)
            if locales:
                st.session_state.locales = locales
                st.success(f"Successfully fetched {len(locales)} locales!")
    
    if st.session_state.get('locales'):
        st.subheader("Available Locales")
        locale_data = {
            "Name": [locale.get('displayName', 'Unnamed') for locale in st.session_state.locales],
            "Tag": [locale.get('tag', 'No tag') for locale in st.session_state.locales],
            "Type": [locale.get('type', 'Unknown') for locale in st.session_state.locales]
        }
        st.table(locale_data)
    
    # 3. Fetch Components
    if st.button("Fetch Site Components", key="fetch_components"):
        with st.spinner("Fetching components..."):
            components = get_site_components(st.session_state.site_id, st.session_state.api_key)
            if components:
                st.session_state.components = components
                st.success(f"Successfully fetched {len(components)} components!")
    
    # 4. Display Components and Handle Selection
    if st.session_state.components:
        st.subheader("Available Components")
        
        # Create a table of components
        component_data = {
            "Name": [comp.get('name', 'Unnamed') for comp in st.session_state.components],
            "Component ID": [comp['id'] for comp in st.session_state.components],
            "Type": [comp.get('type', 'Unknown') for comp in st.session_state.components]
        }
        st.table(component_data)
        
        # 5. Component Selection and Content View
        selected_component = st.selectbox(
            "Select a component",
            options=[f"{comp.get('name', 'Unnamed')} ({comp['id']})" for comp in st.session_state.components],
            key="component_selector",
            index=0 if st.session_state.selected_component else 0
        )
        
        if selected_component:
            st.session_state.selected_component = selected_component
            component_id = selected_component.split('(')[-1].strip(')')
            
            # Initialize component content state if not present
            if 'current_component_content' not in st.session_state:
                st.session_state.current_component_content = None
            if 'parsed_nodes' not in st.session_state:
                st.session_state.parsed_nodes = None
            if 'translation_in_progress' not in st.session_state:
                st.session_state.translation_in_progress = False
            if 'current_translation_index' not in st.session_state:
                st.session_state.current_translation_index = 0
            if 'selected_languages' not in st.session_state:
                st.session_state.selected_languages = []
            
            # 6. View Content Button
            if (st.button("View Component Content", key="view_component_button") or 
                st.session_state.current_component_content is not None):
                
                # Only fetch content if we don't have it or if we're viewing a new component
                if (st.session_state.current_component_content is None or 
                    'last_viewed_component_id' not in st.session_state or 
                    st.session_state.last_viewed_component_id != component_id):
                    
                    with st.spinner("Fetching component content..."):
                        content = get_component_content(
                            site_id=st.session_state.site_id,
                            component_id=component_id,
                            api_key=st.session_state.api_key
                        )
                        if content:
                            st.session_state.current_component_content = content
                            st.session_state.parsed_nodes = parse_component_content(content)
                            st.session_state.last_viewed_component_id = component_id
                
                if st.session_state.parsed_nodes and st.session_state.parsed_nodes['nodes']:
                    st.subheader("Parsed Content")
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
                        if not st.session_state.translation_in_progress:
                            selected_languages = st.multiselect(
                                "Select target languages",
                                options=list(locale_options.keys()),
                                key="translate_languages_select",
                                default=st.session_state.selected_languages
                            )
                            
                            # Store selected languages in session state
                            if selected_languages != st.session_state.selected_languages:
                                st.session_state.selected_languages = selected_languages
                                
                            # Start translation button
                            if st.button("Start Translation", key="start_translation"):
                                if not st.session_state.selected_languages:
                                    st.warning("Please select at least one language")
                                else:
                                    st.session_state.translation_in_progress = True
                                    st.session_state.current_translation_index = 0
                                    st.rerun()
                        
                        # Handle ongoing translation
                        if st.session_state.translation_in_progress:
                            progress_bar = st.progress(st.session_state.current_translation_index / len(st.session_state.selected_languages))
                            current_language = st.session_state.selected_languages[st.session_state.current_translation_index]
                            
                            st.write(f"Translating {current_language} ({st.session_state.current_translation_index + 1}/{len(st.session_state.selected_languages)})")
                            
                            # Perform translation for current language
                            translated_content, error = translate_content_with_openai(
                                st.session_state.parsed_nodes,
                                locale_options[current_language]['tag'],
                                st.session_state.openai_key
                            )
                            
                            if error:
                                st.error(f"Error translating to {current_language}: {error}")
                                st.session_state.translation_in_progress = False
                            else:
                                # Get the locale ID for the API call
                                locale_id = locale_options[current_language]['id']
                                
                                # Create an expander for translation details
                                with st.expander(f"Translation Details - {current_language}", expanded=True):
                                    st.subheader("Translated Content")
                                    st.json(translated_content)
                                    
                                    # Update the component content
                                    result, error = update_component_content(
                                        site_id=st.session_state.site_id,
                                        component_id=component_id,
                                        locale_id=locale_id,
                                        nodes=translated_content['nodes'],
                                        api_key=st.session_state.api_key
                                    )
                                    
                                    if error:
                                        st.error(f"Failed to update content for {current_language}: {error}")
                                        st.session_state.translation_in_progress = False
                                    else:
                                        st.success(f"Successfully updated content for {current_language}")
                                        
                                        # Move to next language or finish
                                        st.session_state.current_translation_index += 1
                                        if st.session_state.current_translation_index >= len(st.session_state.selected_languages):
                                            st.session_state.translation_in_progress = False
                                            st.success("All translations completed!")
                                            if st.button("Start New Translation"):
                                                st.session_state.translation_in_progress = False
                                                st.session_state.current_translation_index = 0
                                                st.session_state.selected_languages = []
                                                st.rerun()
                                        else:
                                            time.sleep(1)  # Small delay between translations
                                            st.rerun()
                    else:
                        if not st.session_state.openai_key:
                            st.warning("Please add your OpenAI API key in the sidebar to enable translations")
                        if not st.session_state.locales:
                            st.warning("No locales available for translation")
                else:
                    st.info("No text content found in this component")

if __name__ == "__main__":
    main()
