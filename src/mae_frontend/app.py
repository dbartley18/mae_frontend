import streamlit as st
import requests
import json
import time
import logging
import os
import pandas as pd
import altair as alt
from langchain.callbacks.streamlit import StreamlitCallbackHandler
from langchain.callbacks.base import BaseCallbackHandler
from dotenv import load_dotenv

# Force clear all Streamlit caches on startup
st.cache_data.clear()
st.cache_resource.clear()

# Page configuration
st.set_page_config(
    page_title="MAE Brand Namer",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "# MAE Brand Namer\nAI-powered brand name generator"
    }
)

# API configuration - Read environment variables fresh each time
def get_fresh_api_url():
    """Get a fresh API URL from environment, bypassing any caching"""
    # Load from .env file if present
    load_dotenv(override=True)  # Reload environment variables
    
    url = os.getenv("LANGGRAPH_STUDIO_URL", None)  # Get fresh value
    print(f"DEBUG: Fresh API URL read from env: {url}")
    if not url:
        st.error("Please set the LANGGRAPH_STUDIO_URL environment variable")
        st.stop()
    return url

API_URL = get_fresh_api_url()
print(f"DEBUG: Using API_URL: {API_URL}")

ASSISTANT_ID = os.getenv("LANGGRAPH_ASSISTANT_ID")
API_KEY = os.getenv("LANGGRAPH_API_KEY")

# Check if required environment variables are set
if not API_URL:
    st.error("Please set the LANGGRAPH_STUDIO_URL environment variable")
    st.stop()
if not ASSISTANT_ID:
    st.error("Please set the LANGGRAPH_ASSISTANT_ID environment variable")
    st.stop()
if not API_KEY:
    st.error("Please set the LANGGRAPH_API_KEY environment variable")
    st.stop()

print(f"DEBUG: Final API_URL being used: {API_URL}")  # Debug the final value

# Add file-based debug logging
logging.basicConfig(
    filename="debug_output.txt",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="w"  # Overwrite the file on each run
)

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []
if "favorite_names" not in st.session_state:
    st.session_state.favorite_names = []
if "current_thread_id" not in st.session_state:
    st.session_state.current_thread_id = None
if "generation_complete" not in st.session_state:
    st.session_state.generation_complete = False
if "langsmith_trace_ids" not in st.session_state:
    st.session_state.langsmith_trace_ids = set()

# Initialize session state for industry selection
if "industry_selection" not in st.session_state:
    st.session_state.industry_selection = {
        "industry": "",
        "sector": "",
        "subsector": ""
    }

# Example prompts
example_prompts = {
    "Industry Summit": "A premier global gathering, fostering the convergence of industry leaders, innovators, and visionaries to explore the future. This event serves as a platform for collaborative dialogue, cutting-edge insights, and transformative strategies, designed to empower participants to navigate the evolving landscape and drive meaningful change",
    "Professional Services": "A global management consulting firm specializing in digital transformation and operational excellence, delivering [Specific Outcome/Result] for [Target Client/Industry] through [Key Service/Approach]",
    "Financial Services": "A [Investment Entity Type, e.g., Institutional, Private, Specialized] investment management firm focusing on sustainable infrastructure investments, emphasizing [Specific Investment Strategy/Philosophy] and targeting [Specific Investor/Market Segment]. We aim to deliver [Specific Financial/Impact Outcome] through [Key Differentiator/Expertise]",
    "B2B HealthTech Company": "A pioneering healthcare technology company delivering intelligent, enterprise-grade solutions that optimize hospital resource management, driving efficiency, enhancing patient care, and empowering healthcare providers to navigate the complexities of modern hospital operations."
}

# Define industry hierarchy data structure
INDUSTRY_HIERARCHY = {
    "Consumer": {
        "Automotive": ["Automotive Manufacturing", "Auto Parts & Suppliers", "Dealerships", "Mobility Services"],
        "Consumer Products": ["Food and Beverage", "Apparel and Footwear", "Personal Care", "Household Products"],
        "Retail": ["Grocery", "Department Stores", "E-commerce", "Specialty Retail"],
        "Transportation, Hospitality & Services": ["Aviation", "Gaming", "Hotels", "Restaurants", "Logistics"]
    },
    "Energy, Resources & Industrials": {
        "Energy & Chemicals": ["Oil & Gas", "Chemicals"],
        "Power, Utilities & Renewables": ["Power Generation", "Utilities", "Renewable Energy"],
        "Industrial Products & Construction": ["Industrial Products Manufacturing", "Construction"],
        "Mining & Metals": ["Mining", "Metals Processing", "Materials"]
    },
    "Financial Services": {
        "Banking & Capital Markets": ["Retail Banking", "Commercial Banking", "Investment Banking", "Capital Markets"],
        "Insurance": ["Life Insurance", "Property & Casualty", "Reinsurance", "InsurTech"],
        "Investment Management & Private Equity": ["Asset Management", "Private Equity", "Hedge Funds", "Wealth Management"],
        "Real Estate": ["Commercial Real Estate", "Residential Real Estate", "REITs"]
    },
    "Government & Public Services": {
        "Central Government": ["Federal Agencies", "Defense", "Public Administration"],
        "Regional and Local Government": ["State Government", "Municipal Services", "Local Administration"],
        "Defense, Security & Justice": ["Defense", "Security", "Justice"],
        "Health & Human Services": ["Public Health", "Social Services", "Welfare"],
        "Infrastructure & Transport": ["Transportation Infrastructure", "Public Transportation"],
        "International Donor Organizations": ["NGOs", "Foundations", "Aid Organizations"]
    },
    "Life Sciences & Health Care": {
        "Health Care": ["Providers", "Payers", "Health Services"],
        "Life Sciences": ["Pharmaceutical", "Biotechnology", "Medical Devices", "Diagnostics"]
    },
    "Technology, Media & Telecommunications": {
        "Technology": ["Software", "Hardware", "Cloud Computing", "Cybersecurity", "Data Analytics"],
        "Media & Entertainment": ["Media", "Entertainment", "Sports", "Gaming"],
        "Telecommunications": ["Wireless Carriers", "Internet Service Providers", "Telecom Infrastructure"]
    },
    "Other": {
        "Other": ["Other"]
    }
}

# Cached API functions
@st.cache_data(ttl=3600)
def fetch_assistants():
    """Fetch available assistants from the API"""
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(
            f"{API_URL}/assistants/search",
            headers=headers,
            json={"graph_id": "brand_naming"}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching assistants: {str(e)}")
        return []

@st.cache_data(ttl=60)
def get_thread_history(thread_id: str):
    """Get the history of a thread"""
    if not thread_id:
        print("DEBUG: No thread_id provided to get_thread_history")
        return []
        
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        print(f"DEBUG: Fetching thread history for {thread_id}")
        response = requests.post(
            f"{API_URL}/threads/{thread_id}/history",
            headers=headers,
            json={}  # Send empty JSON payload for POST request
        )
        
        # Check if the response was successful
        if response.status_code == 200:
            history_data = response.json()
            print(f"DEBUG: Successfully fetched thread history. Data type: {type(history_data)}")
            return history_data
        else:
            print(f"DEBUG: Error fetching thread history: HTTP {response.status_code} - {response.text}")
            st.error(f"Error fetching thread history: HTTP {response.status_code}")
            return []
            
    except Exception as e:
        print(f"DEBUG: Exception in get_thread_history: {str(e)}")
        st.error(f"Error fetching thread history: {str(e)}")
        return []

@st.cache_data(ttl=60)
def get_thread_details(thread_id: str):
    """Get detailed information about a thread"""
    if not thread_id:
        print("DEBUG: No thread_id provided to get_thread_details")
        return None
        
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        print(f"DEBUG: Fetching thread details for {thread_id}")
        response = requests.get(
            f"{API_URL}/threads/{thread_id}",
            headers=headers
        )
        
        # Check if the response was successful
        if response.status_code == 200:
            thread_data = response.json()
            print(f"DEBUG: Successfully fetched thread details. Data keys: {list(thread_data.keys()) if isinstance(thread_data, dict) else 'Not a dict'}")
            return thread_data
        else:
            print(f"DEBUG: Error fetching thread details: HTTP {response.status_code} - {response.text}")
            st.error(f"Error fetching thread details: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"DEBUG: Exception in get_thread_details: {str(e)}")
        st.error(f"Error fetching thread details: {str(e)}")
        return None

@st.cache_data(ttl=60)
def get_thread_runs(thread_id: str):
    """Get all runs for a thread"""
    if not thread_id:
        print("DEBUG: No thread_id provided to get_thread_runs")
        return None
        
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        print(f"DEBUG: Fetching thread runs for {thread_id}")
        response = requests.get(
            f"{API_URL}/threads/{thread_id}/runs",
            headers=headers
        )
        
        # Check if the response was successful
        if response.status_code == 200:
            runs_data = response.json()
            print(f"DEBUG: Successfully fetched thread runs. Found {len(runs_data) if isinstance(runs_data, list) else '0'} runs.")
            return runs_data
        else:
            print(f"DEBUG: Error fetching thread runs: HTTP {response.status_code} - {response.text}")
            st.error(f"Error fetching thread runs: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"DEBUG: Exception in get_thread_runs: {str(e)}")
        st.error(f"Error fetching thread runs: {str(e)}")
        return None

@st.cache_data(ttl=60)
def get_run_details(thread_id: str, run_id: str):
    """Get detailed information about a specific run"""
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.get(
            f"{API_URL}/threads/{thread_id}/runs/{run_id}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching run details: {str(e)}")
        return None

@st.cache_data(ttl=300)
def fetch_all_threads():
    """Fetch all threads from the LangGraph API"""
    headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
    try:
        # Debug logging
        print(f"DEBUG: API_URL at fetch time: {API_URL}")
        request_url = f"{API_URL}/threads/search"
        print(f"DEBUG: Full request URL: {request_url}")
        print(f"DEBUG: Headers: {headers}")
        
        # Use the threads/search endpoint to get all threads
        response = requests.post(
            request_url,
            headers=headers,
            json={
                "limit": 50,  # Fetch up to 50 threads
                "order": "desc",  # Most recent first
                "order_by": "created_at"
            }
        )
        # Debug logging
        print(f"DEBUG: Response status: {response.status_code}")
        print(f"DEBUG: Request URL after response: {response.url}")  # Show final URL after any redirects
        print(f"DEBUG: Response text: {response.text[:200]}...")  # First 200 chars
        
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching threads: {str(e)}")
        return []

def build_complete_prompt(base_prompt, industry_info, target_audience, geographic_scope, name_style):
    """Build a complete prompt with additional context"""
    prompt_parts = [base_prompt.strip()]
    
    additional_details = []
    
    # Extract industry information
    industry = industry_info.get("industry", "")
    sector = industry_info.get("sector", "")
    subsector = industry_info.get("subsector", "")
    
    # Add industry details if available and explicitly selected
    if industry and industry != "Other" and industry != "":
        industry_text = f"The company is in the {industry} industry"
        if sector and sector != "Other" and sector != "":
            industry_text += f", specifically in the {sector} sector"
            if subsector and subsector != "Other" and subsector != "":
                industry_text += f", focusing on {subsector}"
        industry_text += "."
        additional_details.append(industry_text)
    
    # Only include target audience if explicitly provided
    if target_audience and target_audience.strip():
        additional_details.append(f"The target audience is {target_audience}.")
        
    # Only include geographic scope if explicitly selected
    if geographic_scope and geographic_scope.strip():
        additional_details.append(f"The brand will operate at a {geographic_scope.lower()} level.")
        
    # Only include name style if explicitly selected
    if name_style and len(name_style) > 0:
        additional_details.append(f"The name should have a {', '.join(name_style).lower()} feel.")
    
    if additional_details:
        prompt_parts.append("Additional context: " + " ".join(additional_details))
    
    return " ".join(prompt_parts)

def add_to_favorites(name):
    """Add a name to favorites"""
    if name not in st.session_state.favorite_names:
        st.session_state.favorite_names.append(name)
        return True
    return False

def remove_from_favorites(name):
    """Remove a name from favorites"""
    if name in st.session_state.favorite_names:
        st.session_state.favorite_names.remove(name)
        return True
    return False

def process_raw_stream_json(raw_data):
    """Extract and merge new data without duplication"""
    # Initialize latest_data if not already in session state
    if "latest_data" not in st.session_state:
        st.session_state.latest_data = {}
    
    # Initialize displayed sections if not already in session state
    if "displayed_sections" not in st.session_state:
        st.session_state.displayed_sections = set()
    
    # Start with current state
    result = st.session_state.latest_data.copy()
    
    # Update with new data
    for key, value in raw_data.items():
        # Skip system keys or empty values
        if key.startswith("_") or not value:
            continue
            
        # Special handling for generated_names to avoid duplication
        if key == "generated_names" and key in result:
            # Only add new names not already in the list
            existing_names = {str(name) if not isinstance(name, dict) 
                             else name.get("brand_name", "") 
                             for name in result[key]}
            
            for name in value:
                name_key = str(name) if not isinstance(name, dict) else name.get("brand_name", "")
                if name_key and name_key not in existing_names:
                    result[key].append(name)
        else:
            # For other fields, just update with latest value
            result[key] = value
    
    # Store the updated state
    st.session_state.latest_data = result
    return result

def display_structured_results(data, container):
    """Display structured results with tabs for different sections"""
    # Determine which sections are available in the data
    has_brand_context = any(k in data for k in [
        "brand_identity_brief", "brand_promise", "brand_values", 
        "brand_purpose", "brand_mission", "brand_personality",
        "brand_tone_of_voice"
    ])
    
    has_names = "generated_names" in data and data["generated_names"]
    has_analysis = any(k in data for k in [
        "linguistic_analysis_results", "semantic_analysis_results",
        "cultural_analysis_results", "evaluation_results"
    ])
    
    # Create list of available tabs
    available_tabs = []
    if has_brand_context:
        available_tabs.append("Brand Context")
    if has_names:
        available_tabs.append("Generated Names")
    if has_analysis:
        available_tabs.append("Analysis")
    
    # Only proceed if we have tabs to show
    if not available_tabs:
        container.info("Processing data... no results available yet.")
        return
    
    # Create tabs and display content
    tabs = container.tabs(available_tabs)
    
    # Fill tab content
    tab_index = 0
    
    # Brand Context tab
    if has_brand_context:
        with tabs[tab_index]:
            st.subheader("Brand Identity")
            
            # Display brand context fields
            for field, title in [
                ("brand_identity_brief", "Brand Identity Brief"),
                ("brand_promise", "Brand Promise"),
                ("brand_values", "Brand Values"),
                ("brand_purpose", "Brand Purpose"),
                ("brand_mission", "Brand Mission"),
                ("brand_personality", "Brand Personality"),
                ("brand_tone_of_voice", "Tone of Voice")
            ]:
                if field in data and data[field]:
                    st.write(f"**{title}:**")
                    if isinstance(data[field], list):
                        for item in data[field]:
                            st.write(f"- {item}")
                    else:
                        st.write(data[field])
                    st.markdown("---")
        tab_index += 1
    
    # Generated Names tab
    if has_names:
        with tabs[tab_index]:
            st.subheader("Generated Brand Names")
            
            # Display each name
            for name in data["generated_names"]:
                if isinstance(name, dict):
                    name_text = name.get("brand_name", "") or name.get("name", "")
                    if name_text:
                        with st.expander(name_text, expanded=True):
                            # Show additional info if available
                            if "naming_category" in name:
                                st.write(f"**Category:** {name['naming_category']}")
                            if "rationale" in name:
                                st.write(f"**Rationale:** {name['rationale']}")
                            elif "name_generation_methodology" in name:
                                st.write(f"**Methodology:** {name['name_generation_methodology']}")
                else:
                    st.markdown(f"### {name}")
        tab_index += 1
    
    # Analysis tab
    if has_analysis:
        with tabs[tab_index]:
            st.subheader("Name Analysis")
            
            # Display analysis results
            analysis_types = {
                "linguistic_analysis_results": "Linguistic Analysis",
                "semantic_analysis_results": "Semantic Analysis",
                "cultural_analysis_results": "Cultural Analysis",
                "evaluation_results": "Evaluation Results"
            }
            
            for key, title in analysis_types.items():
                if key in data and data[key]:
                    st.write(f"**{title}:**")
                    st.json(data[key])
                    st.markdown("---")
        tab_index += 1

def process_stream_data(stream, container, status_container, progress_bar):
    """Process streaming data from the API"""
    generated_names = []
    evaluations = {}
    
    # Reset latest data and displayed sections for a fresh run
    st.session_state.latest_data = {}
    st.session_state.displayed_sections = set()
    
    # Track run metrics
    token_counts = {"total": 0, "prompt": 0, "completion": 0}
    run_metadata = {"start_time": time.time(), "steps_completed": 0}
    
    # Create containers for metrics and progress
    metrics_container = status_container.container()
    with metrics_container:
        st.subheader("Generation Progress")
        
        # Create multi-column layout for metrics
        metrics_cols = st.columns(4)
        with metrics_cols[0]:
            agent_display = st.empty()
        with metrics_cols[1]:
            steps_display = st.empty()
        with metrics_cols[2]:
            tokens_display = st.empty()
        with metrics_cols[3]:
            time_display = st.empty()
            
        # Progress indicators
        current_step_display = st.empty()
        status_message = st.empty()
    
    # Create separate containers for different types of information
    steps_container = status_container.container()
    
    # Initialize debug data list in session state if not already there
    if "raw_debug_data" not in st.session_state:
        st.session_state.raw_debug_data = []
    else:
        # Clear existing debug data for new run
        st.session_state.raw_debug_data = []
    
    # Also track raw stream data before JSON processing
    if "raw_stream_lines" not in st.session_state:
        st.session_state.raw_stream_lines = []
    else:
        st.session_state.raw_stream_lines = []
    
    # Set up counters and trackers
    line_count = 0
    
    # Clear the results container initially
    container.empty()
    results_display = container.container()
    
    # Process stream data
    for line in stream:
        if not line:
            continue
            
        line_count += 1
        line_str = line.decode("utf-8")
        
        # Store the raw line before any processing
        st.session_state.raw_stream_lines.append(line_str)
        
        # Skip empty lines
        if not line_str.strip():
            continue
        
        # Update progress information
        progress_bar.progress((line_count % 100) / 100)
        elapsed_time = time.time() - run_metadata["start_time"]
        time_display.metric("Time", f"{elapsed_time:.1f}s")
            
        # Handle Server-Sent Events (SSE) format
        if line_str.startswith("event:") or line_str.startswith(":"):
            # This is an SSE event marker or comment, not JSON data
            if line_str.startswith(":"):
                # This is a comment/heartbeat
                status_message.info("Server heartbeat")
                continue
                
            # Extract event type for debugging
            event_type = line_str.replace("event:", "").strip()
            status_message.info(f"Event stream: {event_type}")
            continue
            
        # Process JSON data
        data = None
        json_str = None
            
        # Look for data payload in SSE format
        if line_str.startswith("data:"):
            # Extract the JSON data after "data:"
            json_str = line_str[5:].strip()
            
            # Skip empty data
            if not json_str:
                continue
        else:
            # Try to parse as raw JSON (fallback for non-SSE format)
            json_str = line_str
        
        # Try to parse the JSON data
        try:
            data = json.loads(json_str)
            
            # Store raw data for debugging
            st.session_state.raw_debug_data.append(data)
            print(f"DEBUG: Received data: {data.get('type', 'unknown')}")
        except json.JSONDecodeError as json_err:
            # Log the error and the problematic data
            print(f"Error parsing JSON: {str(json_err)}")
            print(f"Problematic data: '{json_str}'")
            status_message.warning(f"Received non-JSON data (length: {len(json_str)})")
            
            # Store as raw text for debugging
            st.session_state.raw_debug_data.append({"type": "raw_text", "content": json_str})
            continue  # Skip to next line
            
        # If we have valid data, process it
        if data:
            try:
                # Extract event type and metadata
                event_type = data.get("type", "unknown")
                metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
                
                # Handle status message
                if event_type == "status" and "message" in data:
                    status_message.info(data["message"])
                    
                    # Extract step info if available
                    if "langgraph_step" in metadata:
                        steps_display.metric("Steps", metadata["langgraph_step"])
                    
                    # Extract node name if available
                    if "langgraph_node" in metadata:
                        current_node = metadata["langgraph_node"]
                        current_step_display.info(f"Processing node: {current_node}")
                
                # Process structured data - check multiple possible locations
                structured_data = None
                
                # Try to extract structured data from various possible locations
                if "data" in data and isinstance(data["data"], dict):
                    structured_data = data["data"]
                elif "result" in data and isinstance(data["result"], dict):
                    structured_data = data["result"]
                elif "output" in data and isinstance(data["output"], dict):
                    structured_data = data["output"]
                elif event_type == "unknown":
                    # For unknown types, check if this is direct state data
                    # by looking for key fields that would indicate state data
                    state_data_indicators = ["generated_names", "brand_identity_brief", "brand_promise"]
                    if any(indicator in data for indicator in state_data_indicators):
                        structured_data = data
                
                # If we found structured data, process and display it
                if structured_data:
                    # Process raw stream data to avoid duplication
                    processed_data = process_raw_stream_json(structured_data)
                    
                    # Extract names for return value
                    if "generated_names" in processed_data:
                        generated_names = processed_data["generated_names"]
                    
                    # Extract evaluations for return value
                    if "evaluation_results" in processed_data:
                        evaluations = processed_data["evaluation_results"]
                    
                    # Display the updated structured results
                    display_structured_results(processed_data, results_display)
            except Exception as e:
                # Log any errors in processing
                print(f"Error processing data: {str(e)}")
                status_message.error(f"Error: {str(e)}")
        else:
            print(f"No valid data after parsing: {json_str}")
    
    # Final update to progress indicators
    progress_bar.progress(100)
    run_metadata["end_time"] = time.time()
    elapsed_time = run_metadata["end_time"] - run_metadata["start_time"]
    time_display.metric("Time", f"{elapsed_time:.1f}s (Completed)")
    current_step_display.success("Generation completed")
    
    # Mark completion in session state
    st.session_state.generation_complete = True
    
    return generated_names, evaluations

def display_results(generated_names, evaluations, container):
    """
    Legacy function for displaying results.
    Now just a wrapper around display_structured_results.
    """
    data = {
        "generated_names": generated_names
    }
    if evaluations:
        data["evaluation_results"] = evaluations
        
    display_structured_results(data, container)

def display_run_details(thread_id, run_id):
    """Display detailed information about a run in a structured way"""
    run_data = get_run_details(thread_id, run_id)
    
    if not run_data:
        st.warning("Could not fetch run details")
        return
    
    # Display basic run info
    st.subheader(f"Run Details: {run_id[:8]}...")
    
    # Split info into columns
    info_cols = st.columns(3)
    with info_cols[0]:
        st.metric("Status", run_data.get("status", "Unknown"))
    with info_cols[1]:
        created_at = run_data.get("created_at", "")
        if created_at:
            st.metric("Created", created_at.split("T")[0])
    with info_cols[2]:
        start_time = run_data.get("start_time")
        end_time = run_data.get("end_time")
        if start_time and end_time:
            try:
                # Convert to datetime and calculate duration
                from datetime import datetime
                start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration = (end - start).total_seconds()
                st.metric("Duration", f"{duration:.2f}s")
            except:
                st.metric("Duration", "Unknown")
    
    # Display run input/output
    with st.expander("Run Input/Output", expanded=False):
        # Input
        if "input" in run_data:
            st.markdown("##### Input")
            st.json(run_data["input"])
        
        # Output
        if "output" in run_data:
            st.markdown("##### Output")
            st.json(run_data["output"])
    
    # Display any errors
    if "error" in run_data and run_data["error"]:
        st.error(f"Run Error: {run_data['error']}")

def display_thread_history(thread_id):
    """Display comprehensive thread history with visualizations"""
    history_data = get_thread_history(thread_id)
    thread_details = get_thread_details(thread_id)
    thread_runs = get_thread_runs(thread_id)
    
    if not history_data:
        st.warning("No history data available")
        return
        
    # Display thread details
    st.markdown("#### Thread Information")
    
    # Show thread metadata
    if thread_details:
        meta_cols = st.columns(3)
        with meta_cols[0]:
            st.metric("Thread ID", thread_id[:8] + "...")
        with meta_cols[1]:
            created_at = thread_details.get("created_at", "").split("T")[0]
            st.metric("Created", created_at)
        with meta_cols[2]:
            st.metric("Run Count", len(thread_runs) if thread_runs else 0)
    
    # Display runs
    if thread_runs:
        st.markdown("#### Thread Runs")
        for i, run in enumerate(thread_runs):
            run_id = run.get("run_id")
            status = run.get("status", "Unknown")
            
            status_emoji = "🟢" if status == "completed" else "🔴" if status == "failed" else "🟡"
            
            with st.expander(f"{status_emoji} Run {i+1}: {run_id[:8]}... ({status})", expanded=i==0):
                display_run_details(thread_id, run_id)
    
    # Display message history
    if history_data:
        st.markdown("#### Message History")
        
        # Create a more structured view of messages
        for i, message in enumerate(history_data):
            # Determine message role
            role = message.get("role", "Unknown")
            role_emoji = "👤" if role == "user" else "🤖" if role == "assistant" else "🔄"
            
            # Format the message
            with st.container():
                st.markdown(f"##### {role_emoji} {role.title()} Message")
                
                # Content
                if "content" in message and message["content"]:
                    st.markdown(message["content"])
                
                # Handle structured data
                if "data" in message and message["data"]:
                    with st.expander("Message Data", expanded=False):
                        st.json(message["data"])

def find_value_in_data(data, field_names, max_depth=10, current_depth=0):
    """
    Recursively search through a data structure to find values matching any of the given field names.
    
    Args:
        data: The data structure to search (can be dict, list, or scalar)
        field_names: List of field names to search for
        max_depth: Maximum recursion depth to prevent stack overflow
        current_depth: Current recursion depth (used internally)
        
    Returns:
        The first matching value found, or None if no match is found
    """
    # Prevent excessive recursion
    if current_depth > max_depth:
        return None
        
    # If data is None, return None
    if data is None:
        return None
        
    # If data is a dictionary
    if isinstance(data, dict):
        # First check if any of our field names are direct keys
        for field_name in field_names:
            if field_name in data:
                return data[field_name]
        
        # If not found, recursively check all values
        for value in data.values():
            result = find_value_in_data(value, field_names, max_depth, current_depth + 1)
            if result is not None:
                return result
    
    # If data is a list
    elif isinstance(data, list):
        # Check each item in the list
        for item in data:
            result = find_value_in_data(item, field_names, max_depth, current_depth + 1)
            if result is not None:
                return result
    
    # If we get here, we didn't find anything
    return None

def _render_survey_persona(persona):
    """
    Helper function to render a survey persona's responses in a structured format.
    
    Args:
        persona: Dictionary containing the persona's survey response data matching SurveyDetails schema
    """
    # Create main tabs for different sections
    persona_tabs = st.tabs([
        "Company Info",
        "Professional Profile",
        "Brand Perception",
        "Decision Making",
        "Behavioral Profile",
        "Feedback & Relationships"
    ])
    
    # Company Info tab
    with persona_tabs[0]:
        st.write("**Company Information**")
        st.write("Company:", persona.get("company_name", "N/A"))
        st.write("Industry:", persona.get("industry", "N/A"))
        st.write("Company Size:", persona.get("company_size_employees", "N/A"))
        
        # Handle company_revenue with type checking
        revenue = persona.get("company_revenue")
        if revenue is not None:
            try:
                if isinstance(revenue, (int, float)):
                    formatted_revenue = f"${revenue:,.2f}"
                elif isinstance(revenue, str):
                    # Try to convert string to float if it's numeric
                    try:
                        revenue_float = float(revenue.replace('$', '').replace(',', ''))
                        formatted_revenue = f"${revenue_float:,.2f}"
                    except ValueError:
                        formatted_revenue = revenue
                else:
                    formatted_revenue = str(revenue)
                st.write("Annual Revenue:", formatted_revenue)
            except Exception:
                st.write("Annual Revenue:", str(revenue))
        else:
            st.write("Annual Revenue:", "N/A")
    
    # Professional Profile tab
    with persona_tabs[1]:
        st.write("**Professional Profile**")
        st.write("Job Title:", persona.get("job_title", "N/A"))
        st.write("Department:", persona.get("department", "N/A"))
        st.write("Seniority:", persona.get("seniority", "N/A"))
        st.write("Education:", persona.get("education_level", "N/A"))
        if "years_of_experience" in persona:
            st.write("Experience:", f"{persona['years_of_experience']} years" if persona['years_of_experience'] else "N/A")
    
    # Brand Perception tab
    with persona_tabs[2]:
        st.write("**Brand Perception Scores**")
        score_cols = st.columns(3)
        scores = {
            "Personality Fit": persona.get("personality_fit_score"),
            "Competitor Benchmarking": persona.get("competitor_benchmarking_score"),
            "Brand Promise Perception": persona.get("brand_promise_perception_score"),
            "Market Adoption": persona.get("simulated_market_adoption_score"),
            "Competitive Differentiation": persona.get("competitive_differentiation_score")
        }
        
        for i, (metric, value) in enumerate(scores.items()):
            with score_cols[i % 3]:
                if value is not None:
                    st.write(f"**{metric}:** {value}/10")
    
    # Decision Making tab
    with persona_tabs[3]:
        st.write("**Decision Making Profile**")
        decision_cols = st.columns(2)
        with decision_cols[0]:
            st.write("**Decision Making Style:**", persona.get("decision_making_style", "N/A"))
            st.write("**Information Sources:**", persona.get("information_sources", "N/A"))
            st.write("**Risk Attitude:**", persona.get("attitude_towards_risk", "N/A"))
            st.write("**Decision Maker:**", "Yes" if persona.get("decision_maker") else "No")
            st.write("**Budget Authority:**", persona.get("budget_authority", "N/A"))
        with decision_cols[1]:
            st.write("**Pain Points:**", persona.get("pain_points", "N/A"))
            st.write("**Reports To:**", persona.get("reports_to", "N/A"))
            st.write("**Buying Group:**", persona.get("buying_group_structure", "N/A"))
            st.write("**Success Metrics:**", persona.get("success_metrics_product_service", "N/A"))
    
    # Behavioral Profile tab
    with persona_tabs[4]:
        behavior_subtabs = st.tabs(["Purchasing & Online", "Brand Interaction", "Professional Network"])
        
        with behavior_subtabs[0]:
            st.write("**Purchasing Behavior:**", persona.get("purchasing_behavior", "N/A"))
            st.write("**Online Behavior:**", persona.get("online_behavior", "N/A"))
            st.write("**Content Consumption:**", persona.get("content_consumption_habits", "N/A"))
        
        with behavior_subtabs[1]:
            st.write("**Brand Interaction:**", persona.get("interaction_with_brand", "N/A"))
            st.write("**Vendor Preferences:**", persona.get("vendor_relationship_preferences", "N/A"))
            st.write("**Channel Preferences:**", persona.get("channel_preferences_brand_interaction", "N/A"))
            st.write("**Social Media Usage:**", persona.get("social_media_usage", "N/A"))
        
        with behavior_subtabs[2]:
            st.write("**Professional Associations:**", persona.get("professional_associations", "N/A"))
            st.write("**Influence Level:**", persona.get("influence_within_company", "N/A"))
    
    # Feedback & Relationships tab
    with persona_tabs[5]:
        feedback_subtabs = st.tabs(["Qualitative Feedback", "Brand Relationships", "Demographics"])
        
        with feedback_subtabs[0]:
            st.write("**Emotional Association:**", persona.get("emotional_association", "N/A"))
            st.write("**Qualitative Feedback Summary:**", persona.get("qualitative_feedback_summary", "N/A"))
            
            # Display raw qualitative feedback if available
            raw_feedback = persona.get("raw_qualitative_feedback")
            if raw_feedback:
                st.write("##### Detailed Qualitative Feedback")
                try:
                    # If it's a string, try to parse it as JSON
                    if isinstance(raw_feedback, str):
                        raw_feedback = json.loads(raw_feedback)
                    
                    # Now handle the parsed dictionary
                    if isinstance(raw_feedback, dict):
                        cols = st.columns(2)
                        for i, (aspect, feedback) in enumerate(raw_feedback.items()):
                            with cols[i % 2]:
                                st.write(f"**{aspect}:**\n\"{feedback}\"")
                    else:
                        # If it's not a dictionary after parsing, display directly
                        st.markdown(raw_feedback)
                except json.JSONDecodeError:
                    # If JSON parsing fails, display as raw text
                    st.markdown(raw_feedback)
        
        with feedback_subtabs[1]:
            # Display brand relationships if available
            brand_relationships = persona.get("current_brand_relationships")
            if brand_relationships:
                # Handle both string and dictionary formats
                if isinstance(brand_relationships, str):
                    try:
                        # Try to parse as JSON if it's a string
                        brand_relationships = json.loads(brand_relationships)
                    except json.JSONDecodeError:
                        # If parsing fails, display as raw text
                        st.write(brand_relationships)
                        brand_relationships = None
                
                if isinstance(brand_relationships, dict):
                    # Create two columns for brand relationships
                    cols = st.columns(2)
                    for i, (brand, relationship) in enumerate(brand_relationships.items()):
                        with cols[i % 2]:
                            st.markdown(f"**{brand}:**\n\"{relationship}\"")
                elif isinstance(brand_relationships, list):
                    # Handle list format if present
                    for relationship in brand_relationships:
                        if isinstance(relationship, dict):
                            brand = relationship.get("brand", "")
                            description = relationship.get("relationship", "")
                            if brand and description:
                                st.markdown(f"**{brand}:**\n\"{description}\"")
                        else:
                            st.write(relationship)
            else:
                st.info("No brand relationships data available")
        
        with feedback_subtabs[2]:
            st.write("**Generation/Age Range:**", persona.get("generation_age_range", "N/A"))
            st.write("**Persona Archetype:**", persona.get("persona_archetype_type", "N/A"))
    
    # Final Recommendation (outside tabs, always visible)
    st.write("**Final Recommendation**")
    st.write(persona.get("final_survey_recommendation", "No recommendation provided"))
    

def _render_domain_analysis(analysis):
    """
    Helper function to render domain analysis results in a structured format.
    
    Args:
        analysis: Dictionary containing domain analysis data matching DomainDetails schema
    """
    # Display basic domain information
    st.write("**Brand Name:**", analysis.get("brand_name", "N/A"))
    st.write("**Notes:**", analysis.get("notes", ""))
    
    # Display metrics in columns
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Exact Match Domain:**", "✅ Available" if analysis.get("domain_exact_match") else "❌ Not Available")
        st.write("**Acquisition Cost:**", analysis.get("acquisition_cost", "N/A"))
    with col2:
        st.write("**Contains Hyphens/Numbers:**", "Yes" if analysis.get("hyphens_numbers_present") else "No")
        st.write("**Brand Name Clarity in URL:**", analysis.get("brand_name_clarity_in_url", "N/A"))
    
    # Display detailed analysis in tabs
    analysis_tabs = st.tabs(["Domain Options", "Social Media Availability", "Technical Analysis", "Future Considerations"])
    
    # Domain Options tab
    with analysis_tabs[0]:
        st.write("**Alternative TLDs**")
        alternative_tlds = analysis.get("alternative_tlds", [])
        if alternative_tlds:
            # Split TLDs into two columns
            col1, col2 = st.columns(2)
            mid_point = len(alternative_tlds) // 2
            with col1:
                for tld in alternative_tlds[:mid_point]:
                    st.write(f"- {tld}")
            with col2:
                for tld in alternative_tlds[mid_point:]:
                    st.write(f"- {tld}")
        else:
            st.write("No alternative TLDs available")
    
    # Social Media Availability tab
    with analysis_tabs[1]:
        social_handles = analysis.get("social_media_availability", [])
        if social_handles:
            for handle in social_handles:
                st.write(f"- {handle}")
        else:
            st.write("No social media handles available")
    
    # Technical Analysis tab
    with analysis_tabs[2]:
        st.write("**Domain Length & Readability:**", analysis.get("domain_length_readability", ""))
        st.write("**Misspellings/Variations Available:**", "Yes" if analysis.get("misspellings_variations_available") else "No")
        
        # Display technical notes if available
        if analysis.get("notes"):
            st.write("**Notes**")
            st.write(analysis["notes"])
    
    # Future Considerations tab
    with analysis_tabs[3]:
        st.write("**Scalability Analysis**")
        st.write(analysis.get("scalability_future_proofing", "No information available"))
        
        # Additional considerations if available
        if analysis.get("notes"):
            st.write("**Additional Considerations**")
            st.write(analysis["notes"])

def render_thread_data(thread_data):
    """
    Renders thread data in a structured format with tabs for different sections.
    
    Args:
        thread_data: A dictionary containing thread data from the LangSmith API
    """
    if not thread_data:
        st.error("No thread data available. Please check the thread ID and try again.")
        return
        
    # Create main tabs for different sections in the specified order
    tabs = st.tabs([
        "Brand Context",
        "Name Generation",
        "Name Analysis",
        "Name Evaluation",
        "Translation Analysis",
        "Domain Analysis",
        "Research",
        "Downloadable Report"
    ])

    def _render_translation_analysis(analysis):
        """Helper function to render translation analysis consistently"""
        # Create tabs for different aspects of translation analysis
        translation_tabs = st.tabs([
            "Translation Overview",
            "Cultural Impact",
            "Adaptation Details",
            "Additional Notes"
        ])
        
        # Translation Overview tab
        with translation_tabs[0]:
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Direct Translation:**", analysis.get("direct_translation", ""))
                st.write("**Semantic Shift:**", analysis.get("semantic_shift", ""))
                st.write("**Pronunciation Difficulty:**", analysis.get("pronunciation_difficulty", ""))
            with col2:
                st.write("**Phonetic Retention:**", analysis.get("phonetic_retention", ""))
                st.write("**Brand Essence Preserved:**", analysis.get("brand_essence_preserved", ""))
                if analysis.get("rank"):
                    st.write("**Translation Viability Score:**", analysis.get("rank"))
        
        # Cultural Impact tab
        with translation_tabs[1]:
            st.write("**Cultural Acceptability:**", analysis.get("cultural_acceptability", ""))
            st.write("**Global vs Local Balance:**", analysis.get("global_consistency_vs_localization", ""))
            if analysis.get("phonetic_similarity_undesirable"):
                st.warning("⚠️ Potential undesirable phonetic similarity detected")
        
        # Adaptation Details tab
        with translation_tabs[2]:
            st.write("**Adaptation Needed:**", "Yes" if analysis.get("adaptation_needed") else "No")
            if analysis.get("adaptation_needed"):
                st.write("**Proposed Adaptation:**", analysis.get("proposed_adaptation", ""))
        
        # Additional Notes tab
        with translation_tabs[3]:
            if analysis.get("pronunciation_guide"):
                st.write("**Pronunciation Guide:**", analysis.get("pronunciation_guide"))
            
            if analysis.get("technical_considerations"):
                st.write(analysis.get("technical_considerations"))
            
            if analysis.get("phonetic_analysis"):
                st.write(analysis.get("phonetic_analysis"))
            
            if analysis.get("notes"):
                st.write(analysis.get("notes"))

    # 1. Brand Context
    with tabs[0]:
        st.markdown("**Detailed Brand Identity Results**")
        st.write("*The following sections provide a comprehensive overview of the brand context, including core identity, brand voice, market position, and industry context. All of this information was extracted and generated based on the single prompt provided by the user.*")
        brand_context = {}
        
        # Create tabs for different aspects of brand context
        context_tabs = st.tabs([
            "Core Identity",
            "Brand Voice",
            "Market Position",
            "Industry Context"
        ])
        
        # Core Identity tab
        with context_tabs[0]:
            for field in [
                ("Brand Identity Brief", "brand_identity_brief"),
                ("Brand Promise", "brand_promise"),
                ("Brand Values", "brand_values"),
                ("Brand Purpose", "brand_purpose"),
                ("Brand Mission", "brand_mission")
            ]:
                display_name, field_name = field
                value = find_value_in_data(thread_data, [field_name])
                if value:
                    with st.expander(display_name, expanded=True):
                        if isinstance(value, str):
                            st.write(value)
                        elif isinstance(value, list):
                            for item in value:
                                st.write(f"- {item}")
                        elif isinstance(value, dict):
                            _render_analysis_section(value, display_name.lower())
        
        # Brand Voice tab
        with context_tabs[1]:
            for field in [
                ("Brand Personality", "brand_personality"),
                ("Brand Tone of Voice", "brand_tone_of_voice")
            ]:
                display_name, field_name = field
                value = find_value_in_data(thread_data, [field_name])
                if value:
                    with st.expander(display_name, expanded=True):
                        if isinstance(value, str):
                            st.write(value)
                        elif isinstance(value, list):
                            for item in value:
                                st.write(f"- {item}")
                        elif isinstance(value, dict):
                            _render_analysis_section(value, display_name.lower())
        
        # Market Position tab
        with context_tabs[2]:
            for field in [
                ("Target Audience", "target_audience"),
                ("Customer Needs", "customer_needs"),
                ("Market Positioning", "market_positioning"),
                ("Competitive Landscape", "competitive_landscape")
            ]:
                display_name, field_name = field
                value = find_value_in_data(thread_data, [field_name])
                if value:
                    with st.expander(display_name, expanded=True):
                        if isinstance(value, str):
                            st.write(value)
                        elif isinstance(value, list):
                            for item in value:
                                st.write(f"- {item}")
                        elif isinstance(value, dict):
                            _render_analysis_section(value, display_name.lower())
        
        # Industry Context tab
        with context_tabs[3]:
            for field in [
                ("Industry Focus", "industry_focus"),
                ("Industry Trends", "industry_trends")
            ]:
                display_name, field_name = field
                value = find_value_in_data(thread_data, [field_name])
                if value:
                    with st.expander(display_name, expanded=True):
                        if isinstance(value, str):
                            st.write(value)
                        elif isinstance(value, list):
                            for item in value:
                                st.write(f"- {item}")
                        elif isinstance(value, dict):
                            _render_analysis_section(value, display_name.lower())
    
    # 2. Name Generation
    with tabs[1]:
        st.markdown("**Preliminary Brand Name Generation Results**")
        st.write("*The following brand names were generated using Alina Wheeler's brand name methodology based on the context provided within the generated Brand Context results.*")
        generated_names = find_value_in_data(thread_data, ["generated_names"])
        
        if generated_names:
            # Convert to list if it's not already
            if not isinstance(generated_names, list):
                if isinstance(generated_names, dict) and "names" in generated_names:
                    generated_names = generated_names.get("names", [])
                else:
                    generated_names = [generated_names]
            
            # Sort names by rank if available
            sorted_names = []
            for name_data in generated_names:
                if isinstance(name_data, dict):
                    rank = name_data.get("rank", 999)
                    sorted_names.append((rank, name_data))
            
            sorted_names.sort(key=lambda x: x[0])
            
            # Display each name with its details
            for rank, name_data in sorted_names:
                brand_name = name_data.get("brand_name", "") or name_data.get("name", "")
                if brand_name:
                    with st.expander(f"{brand_name}", expanded=True):
                        # Create tabs for different aspects of the name
                        name_tabs = st.tabs([
                            "Core Details",
                            "Brand Alignment",
                            "Methodology"
                        ])
                        
                        # Core Details tab
                        with name_tabs[0]:
                            col1, col2 = st.columns(2)
                            with col1:
                                if rank != 999:
                                    st.write("**Rank:**", rank)
                                st.write("**Category:**", name_data.get("naming_category", ""))
                            with col2:
                                st.write("**Market Differentiation:**", name_data.get("market_differentiation", ""))
                                st.write("**Target Audience Relevance:**", name_data.get("target_audience_relevance", ""))
                        
                        # Brand Alignment tab
                        with name_tabs[1]:
                            st.write("**Brand Personality Alignment:**", name_data.get("brand_personality_alignment", ""))
                            st.write("**Brand Promise Alignment:**", name_data.get("brand_promise_alignment", ""))
                        
                        # Methodology tab
                        with name_tabs[2]:
                            rationale = name_data.get("rationale", "") or name_data.get("name_generation_methodology", "")
                            if rationale:
                                st.write(rationale)
                            else:
                                st.info("No rationale provided")
        else:
            st.info("No generated names found in the thread data.")
    
    # 3. Pre Analyses with child tabs
    with tabs[2]:
        st.markdown("**Generated Brand Name Analysis**")
        st.write("*Each brand name is analyzed for linguistic, semantic, and cultural sensitivity*")
        pre_analysis_tabs = st.tabs(["Linguistic Analysis", "Semantic Analysis", "Cultural Sensitivity"])
        
        # Linguistic Analysis
        with pre_analysis_tabs[0]:
            st.markdown("**Linguistic Analysis**")
            linguistic_analysis = find_value_in_data(thread_data, ["linguistic_analysis_results"])
            if linguistic_analysis:
                if isinstance(linguistic_analysis, dict):
                    for name, analysis in linguistic_analysis.items():
                        with st.expander(f"Analysis for: {name}", expanded=True):
                            cols = st.columns(2)
                            with cols[0]:
                                st.write("**Pronunciation Ease:**", analysis.get("pronunciation_ease"))
                                st.write("**Sound Symbolism:**", analysis.get("sound_symbolism"))
                                st.write("**Overall Readability:**", analysis.get("overall_readability_score"))
                                st.write("**Rank:**", analysis.get("rank"))
                            with cols[1]:
                                st.write("**Euphony vs Cacophony:**", analysis.get("euphony_vs_cacophony"))
                                st.write("**Rhythm and Meter:**", analysis.get("rhythm_and_meter"))
                                st.write("**Word Class:**", analysis.get("word_class"))
                            
                            st.write("**Notes:**", analysis.get("notes"))
                            
                            if analysis.get("homophones_homographs"):
                                st.warning("⚠️ This name has similar sounding or looking words")
            else:
                st.info("No linguistic analysis data found.")
        
        # Semantic Analysis
        with pre_analysis_tabs[1]:
            st.markdown("**Semantic Analysis**")
            semantic_analysis = find_value_in_data(thread_data, ["semantic_analysis_results"])
            if semantic_analysis and isinstance(semantic_analysis, list):
                for analysis in semantic_analysis:
                    if isinstance(analysis, dict):
                        name = analysis.get("brand_name", "")
                        with st.expander(f"Analysis for: {name}", expanded=True):
                            cols = st.columns(2)
                            with cols[0]:
                                st.write("**Denotative Meaning:**", analysis.get("denotative_meaning"))
                                st.write("**Etymology:**", analysis.get("etymology"))
                                st.write("**Descriptiveness:**", analysis.get("descriptiveness"))
                                st.write("**Concreteness:**", analysis.get("concreteness"))
                            with cols[1]:
                                st.write("**Brand Name Type:**", analysis.get("brand_name_type"))
                                st.write("**Emotional Valence:**", analysis.get("emotional_valence"))
                                st.write("**Sensory Associations:**", analysis.get("sensory_associations"))
                                st.write("**Brand Fit/Relevance:**", analysis.get("brand_fit_relevance"))
                            
                            # Additional semantic details
                            st.write("**Figurative Language:**", analysis.get("figurative_language"))
                            if analysis.get("irony_or_paradox"):
                                st.info("Contains irony or paradox")
                            if analysis.get("humor_playfulness"):
                                st.info("Contains humor/playfulness")
                            st.write("**Memorability Score:**", analysis.get("memorability_score"))
            else:
                st.info("No semantic analysis data found.")
        
        # Cultural Sensitivity Analysis
        with pre_analysis_tabs[2]:
            st.markdown("**Cultural Sensitivity Analysis**")
            cultural_analysis = find_value_in_data(thread_data, ["cultural_analysis_results"])
            if cultural_analysis:
                if isinstance(cultural_analysis, dict):
                    for name, analysis in cultural_analysis.items():
                        with st.expander(f"Analysis for: {name}", expanded=True):
                            cols = st.columns(2)
                            with cols[0]:
                                st.write("**Cultural Connotations:**", analysis.get("cultural_connotations"))
                                st.write("**Symbolic Meanings:**", analysis.get("symbolic_meanings"))
                                st.write("**Overall Risk Rating:**", analysis.get("overall_risk_rating"))
                                st.write("**Rank:**", analysis.get("rank"))
                            with cols[1]:
                                st.write("**Religious Sensitivities:**", analysis.get("religious_sensitivities"))
                                st.write("**Social/Political Taboos:**", analysis.get("social_political_taboos"))
                                if analysis.get("body_part_bodily_function_connotations"):
                                    st.warning("⚠️ Contains potentially sensitive anatomical/physiological references")
                            
                            st.write("**Notes:**", analysis.get("notes"))
            else:
                st.info("No cultural sensitivity analysis data found.")
    
    # 4. Name Evaluation
    with tabs[3]:
        st.markdown("**Name Evaluation Results**")
        st.write("*Name Evaluation Results are based on a comprehensive evaluation of each name against the brand context, semantic, cultural, and linguistic analyses*")
        evaluation_results = find_value_in_data(thread_data, ["evaluation_results"])
        if evaluation_results:
            if isinstance(evaluation_results, dict):
                # Sort evaluations to show shortlisted names first
                sorted_evaluations = sorted(
                    evaluation_results.items(),
                    key=lambda x: (x[1].get("shortlist_status") != "Yes", x[0])  # Sort by shortlist status first, then name
                )
                
                for name, eval_data in sorted_evaluations:
                    with st.expander(f"Evaluation for: {name}", expanded=True):
                        # Show shortlist status first
                        if eval_data.get("shortlist_status") == "Yes":
                            st.success("✅ Selected for shortlist")
                        
                        # Create tabs for different aspects of evaluation
                        eval_tabs = st.tabs([
                            "Core Metrics",
                            "Brand Alignment",
                            "Evaluation Details"
                        ])
                        
                        # Core Metrics tab
                        with eval_tabs[0]:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**Overall Score:**", eval_data.get("overall_score"))
                                st.write("**Memorability:**", eval_data.get("memorability_score"))
                                st.write("**Pronounceability:**", eval_data.get("pronounceability_score"))
                            with col2:
                                st.write("**Domain Viability:**", eval_data.get("domain_viability_score"))
                                st.write("**Positioning Strength:**", eval_data.get("positioning_strength"))
                        
                        # Brand Alignment tab
                        with eval_tabs[1]:
                            st.write("**Brand Fit:**", eval_data.get("brand_fit_score"))
                            st.write("**Strategic Alignment:**", eval_data.get("strategic_alignment_score"))
                            st.write("**Visual Branding Potential:**", eval_data.get("visual_branding_potential"))
                            st.write("**Storytelling Potential:**", eval_data.get("storytelling_potential"))
                        
                        # Evaluation Details tab
                        with eval_tabs[2]:
                            st.write("**Evaluation Comments:**", eval_data.get("evaluation_comments"))
        else:
            st.info("No evaluation results found.")
    
    # 5. Translation Analysis (now a parent tab)
    with tabs[4]:
        st.markdown("**Translation Analysis Results**")
        st.write("*Shotlisted Brand Names are translated against the top six (6) global languages to ensure global market accessibility*")
        translation_analysis = find_value_in_data(thread_data, ["translation_analysis_results"])
        if translation_analysis:
            # Handle both list and dictionary formats
            if isinstance(translation_analysis, dict):
                # If it's already organized by brand name and language
                for brand_name, languages in translation_analysis.items():
                    st.caption(f"{brand_name}")
                    for lang, analysis in languages.items():
                        with st.expander(f"{lang} Analysis", expanded=True):
                            _render_translation_analysis(analysis)
            elif isinstance(translation_analysis, list):
                # Organize list data by brand name and language
                organized_data = {}
                for analysis in translation_analysis:
                    if isinstance(analysis, dict):
                        brand_name = analysis.get("brand_name", "Unknown Brand")
                        target_lang = analysis.get("target_language", "Unknown Language")
                        
                        if brand_name not in organized_data:
                            organized_data[brand_name] = {}
                        organized_data[brand_name][target_lang] = analysis
                
                # Display organized data
                for brand_name, languages in organized_data.items():
                    st.caption(f"{brand_name}")
                    for lang, analysis in languages.items():
                        with st.expander(f"{lang} Analysis", expanded=True):
                            _render_translation_analysis(analysis)
        else:
            st.info("No translation analysis data found.")

    # 6. Domain Analysis (now a parent tab)
    with tabs[5]:
        st.markdown("**Domain Analysis Results**")
        st.write("*Shortlisted Brand Names are analyzed for domain availability and social media potential*")
        domain_analysis = find_value_in_data(thread_data, ["domain_analysis_results"])
        if domain_analysis:
            if isinstance(domain_analysis, dict):
                # Handle dictionary format
                for name, analysis in domain_analysis.items():
                    with st.expander(f"Analysis for: {name}", expanded=True):
                        _render_domain_analysis(analysis)
            elif isinstance(domain_analysis, list):
                # Handle list format
                for analysis in domain_analysis:
                    if isinstance(analysis, dict):
                        name = analysis.get("brand_name", "") or analysis.get("name", "Unknown")
                        with st.expander(f"Analysis for: {name}", expanded=True):
                            _render_domain_analysis(analysis)
        else:
            st.info("No domain analysis data found.")
    
    # 7. Research with child tabs
    with tabs[6]:
        st.markdown("**Market Research**")
        st.write("*In depth market research is conducted to understand the market size, growth rate, customer needs, SEO potential, and competitive landscape. Along with this research a survey is conducted, utilizing synthetic persona data, to understand the customer preferences.*")
        research_tabs = st.tabs([
            "Market Research",
            "SEO Analysis",
            "Survey Results",
            "Competitor Analysis"
        ])
        
        # Market Research
        with research_tabs[0]:
            market_research = find_value_in_data(thread_data, ["market_research_results"])
            if market_research:
                if isinstance(market_research, dict):
                    # Handle dictionary format
                    for name, analysis in market_research.items():
                        with st.expander(f"Market Analysis for: {name}", expanded=False):
                            _render_market_research(analysis)
                elif isinstance(market_research, list):
                    # Handle list format
                    for analysis in market_research:
                        if isinstance(analysis, dict):
                            name = analysis.get("brand_name", "") or analysis.get("name", "Unknown")
                            with st.expander(f"Market Analysis for: {name}", expanded=False):
                                _render_market_research(analysis)
            else:
                st.info("No market research data found.")

        # SEO Analysis
        with research_tabs[1]:
            seo_analysis = find_value_in_data(thread_data, ["seo_analysis_results"])
            if seo_analysis:
                # Handle both list and dictionary formats
                if isinstance(seo_analysis, list):
                    # Process each brand's SEO analysis
                    for brand_analysis in seo_analysis:
                        brand_name = brand_analysis.get("brand_name", "Unknown Brand")
                        st.caption(f"{brand_name}")
                        
                        with st.expander("SEO Analysis Details", expanded=True):
                            # Overview metrics in columns
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**Keyword Alignment:**", brand_analysis.get("keyword_alignment"))
                                st.write("**Search Volume:**", brand_analysis.get("search_volume"))
                                st.write("**Keyword Competition:**", brand_analysis.get("keyword_competition"))
                                st.write("**Branded Keyword Potential:**", brand_analysis.get("branded_keyword_potential"))
                                st.write("**Non-Branded Keyword Potential:**", brand_analysis.get("non_branded_keyword_potential"))
                                st.write("**Exact Match Search Results:**", brand_analysis.get("exact_match_search_results"))
                            with col2:
                                st.write("**Social Media Availability:**", brand_analysis.get("social_media_availability"))
                                st.write("**Social Media Discoverability:**", brand_analysis.get("social_media_discoverability"))
                                st.write("**Name Length Searchability:**", brand_analysis.get("name_length_searchability"))
                                st.write("**Unusual Spelling Impact:**", brand_analysis.get("unusual_spelling_impact"))
                                st.write("**SEO Viability Score:**", brand_analysis.get("seo_viability_score"))
                            
                            # Create detail tabs
                            detail_tabs = st.tabs([
                                "Content Strategy",
                                "Technical Analysis",
                                "Recommendations"
                            ])
                            
                            # Content Strategy tab
                            with detail_tabs[0]:
                                st.write("**Content Marketing Opportunities:**", brand_analysis.get("content_marketing_opportunities"))
                                st.write("**Negative Keyword Associations:**", brand_analysis.get("negative_keyword_associations"))
                                st.write("**Negative Search Results:**", brand_analysis.get("negative_search_results"))
                            
                            # Technical Analysis tab
                            with detail_tabs[1]:
                                st.write("**Competitor Domain Strength:**", brand_analysis.get("competitor_domain_strength"))
                                st.write("**Domain Status:**", brand_analysis.get("domain_status"))
                                st.write("**Technical Issues:**", brand_analysis.get("technical_issues"))
                            
                            # Recommendations tab
                            with detail_tabs[2]:
                                seo_recs = brand_analysis.get("seo_recommendations", [])
                                if seo_recs:
                                    if isinstance(seo_recs, list):
                                        for rec in seo_recs:
                                            st.write(f"- {rec}")
                                    elif isinstance(seo_recs, dict):
                                        for key, rec in seo_recs.items():
                                            st.write(f"- **{key}:** {rec}")
                                    else:
                                        st.write(seo_recs)
                        st.divider()
                elif isinstance(seo_analysis, dict):
                    # Handle dictionary format (single brand or name-keyed analyses)
                    for name, analysis in seo_analysis.items():
                        st.caption(f"{name}")
                        
                        with st.expander("SEO Analysis Details", expanded=True):
                            # Overview metrics in columns
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**Keyword Alignment:**", analysis.get("keyword_alignment"))
                                st.write("**Search Volume:**", analysis.get("search_volume"))
                                st.write("**Keyword Competition:**", analysis.get("keyword_competition"))
                                st.write("**Branded Keyword Potential:**", analysis.get("branded_keyword_potential"))
                                st.write("**Non-Branded Keyword Potential:**", analysis.get("non_branded_keyword_potential"))
                                st.write("**Exact Match Search Results:**", analysis.get("exact_match_search_results"))
                            with col2:
                                st.write("**Social Media Availability:**", analysis.get("social_media_availability"))
                                st.write("**Social Media Discoverability:**", analysis.get("social_media_discoverability"))
                                st.write("**Name Length Searchability:**", analysis.get("name_length_searchability"))
                                st.write("**Unusual Spelling Impact:**", analysis.get("unusual_spelling_impact"))
                                st.write("**SEO Viability Score:**", analysis.get("seo_viability_score"))
                            
                            # Create detail tabs
                            detail_tabs = st.tabs([
                                "Content Strategy",
                                "Technical Analysis",
                                "Recommendations"
                            ])
                            
                            # Content Strategy tab
                            with detail_tabs[0]:
                                st.write("**Content Marketing Opportunities:**", analysis.get("content_marketing_opportunities"))
                                st.write("**Negative Keyword Associations:**", analysis.get("negative_keyword_associations"))
                                st.write("**Negative Search Results:**", analysis.get("negative_search_results"))
                            
                            # Technical Analysis tab
                            with detail_tabs[1]:
                                st.write("**Competitor Domain Strength:**", analysis.get("competitor_domain_strength"))
                                st.write("**Domain Status:**", analysis.get("domain_status"))
                                st.write("**Technical Issues:**", analysis.get("technical_issues"))
                            
                            # Recommendations tab
                            with detail_tabs[2]:
                                seo_recs = analysis.get("seo_recommendations", [])
                                if seo_recs:
                                    if isinstance(seo_recs, list):
                                        for rec in seo_recs:
                                            st.write(f"- {rec}")
                                    elif isinstance(seo_recs, dict):
                                        for key, rec in seo_recs.items():
                                            st.write(f"- **{key}:** {rec}")
                                    else:
                                        st.write(seo_recs)
                        st.divider()
            else:
                st.info("No SEO analysis data found.")

        # Survey Results
        with research_tabs[2]:
            survey_results = find_value_in_data(thread_data, ["survey_simulation_results"])
            if survey_results:
                # Handle both list and dictionary formats
                if isinstance(survey_results, list):
                    # Process each brand's survey results
                    for brand_survey in survey_results:
                        brand_name = brand_survey.get("brand_name", "Unknown Brand")
                        st.caption(f"{brand_name}")
                        
                        individual_personas = brand_survey.get("individual_personas", [])
                        if individual_personas:
                            st.write("**Individual Persona Responses**")
                            for persona in individual_personas:
                                company_name = persona.get('company_name', 'Unknown Company')
                                job_title = persona.get('job_title', 'Unknown Role')
                                persona_title = f"Persona: {job_title} at {company_name}"
                                with st.expander(persona_title, expanded=True):
                                    _render_survey_persona(persona)
                        else:
                            st.info(f"No survey responses found for {brand_name}")
                        st.markdown("---")
                else:
                    # Handle single brand survey results
                    individual_personas = survey_results.get("individual_personas", [])
                    if individual_personas:
                        st.write("**Individual Persona Responses**")
                        for persona in individual_personas:
                            company_name = persona.get('company_name', 'Unknown Company')
                            job_title = persona.get('job_title', 'Unknown Role')
                            persona_title = f"Persona: {job_title} at {company_name}"
                            with st.expander(persona_title, expanded=True):
                                _render_survey_persona(persona)
                    else:
                        st.info("No survey responses found.")
            else:
                st.info("No survey simulation results found.")

        # Competitor Analysis
        with research_tabs[3]:
            competitor_analysis = find_value_in_data(thread_data, ["competitor_analysis_results"])
            if competitor_analysis:
                if isinstance(competitor_analysis, list):
                    for brand_analysis in competitor_analysis:
                        brand_name = brand_analysis.get("brand_name", "Unknown Brand")
                        competitors = brand_analysis.get("competitors", [])
                        
                        st.caption(f"{brand_name}")
                        if competitors:
                            for competitor in competitors:
                                with st.expander(f"Analysis for: {competitor.get('competitor_name', 'Unknown Competitor')}", expanded=True):
                                    # Overview metrics in three columns
                                    col1, col2, col3 = st.columns(3)
                                    
                                    with col1:
                                        st.write("**Risk of Confusion:**", competitor.get("risk_of_confusion", 0))
                                        st.write("**Differentiation Score:**", competitor.get("differentiation_score", 0))
                                    
                                    with col2:
                                        st.write("**Competitor Name:**", competitor.get("competitor_name", ""))
                                        st.write("**Naming Style:**", competitor.get("competitor_naming_style", ""))
                                        st.write("**Keywords:**", competitor.get("competitor_keywords", ""))
                                    
                                    with col3:
                                        st.write("**Trademark Risk:**", competitor.get("trademark_conflict_risk", ""))
                                        st.write("**Target Audience:**", competitor.get("target_audience_perception", ""))
                                    
                                    # Create detail tabs for organized information
                                    detail_tabs = st.tabs([
                                        "Market Position",
                                        "Strengths & Weaknesses",
                                        "Differentiation Strategy"
                                    ])
                                    
                                    # Market Position tab
                                    with detail_tabs[0]:
                                        st.write("**Market Positioning:**", competitor.get("competitor_positioning", ""))
                                        st.write("**Target Audience Perception:**", competitor.get("target_audience_perception", ""))
                                        st.write("**Competitive Advantage Notes:**", competitor.get("competitive_advantage_notes", ""))
                                    
                                    # Strengths & Weaknesses tab
                                    with detail_tabs[1]:
                                        st.write("**Strengths:**", competitor.get("competitor_strengths", ""))
                                        st.write("**Weaknesses:**", competitor.get("competitor_weaknesses", ""))
                                    
                                    # Differentiation Strategy tab
                                    with detail_tabs[2]:
                                        st.write("**Differentiation Opportunities:**", competitor.get("competitor_differentiation_opportunity", ""))
                                        st.write("**Trademark Conflict Risk:**", competitor.get("trademark_conflict_risk", ""))
                                    
                                    st.divider()
                        else:
                            st.info(f"No competitor analysis data found for {brand_name}")
            else:
                st.info("No competitor analysis data found.")
    
    # 8. Report Details
    with tabs[7]:
        
        # Display input prompt
        user_prompt = find_value_in_data(thread_data, ["user_prompt"])
        if user_prompt:
            st.markdown("**Brand Prompt**")
            st.write(user_prompt)
        
        # Display creation date
        created_at = find_value_in_data(thread_data, ["created_at"])
        if created_at:
            st.markdown("**Date Generated**")
            # Remove time component from ISO date
            if isinstance(created_at, str) and "T" in created_at:
                created_at = created_at.split("T")[0]
            st.write(created_at)
        
        # Display shortlisted names
        shortlisted_names = find_value_in_data(thread_data, ["shortlisted_names"])
        if shortlisted_names:
            st.markdown("**Shortlisted Names**")
            if isinstance(shortlisted_names, list):
                for name in shortlisted_names:
                    st.write(f"- {name}")
            elif isinstance(shortlisted_names, dict):
                for name, details in shortlisted_names.items():
                    with st.expander(name):
                        st.write(details)
        
        # Display report download and file size
        report_url = find_value_in_data(thread_data, ["report_url"])
        file_size_kb = find_value_in_data(thread_data, ["file_size_kb"])
        
        if report_url:
            st.markdown("**Report Download**")
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"[Download Report]({report_url})",
                    unsafe_allow_html=True
                )
            with col2:
                if file_size_kb:
                    # Convert KB to MB with one decimal place
                    file_size_mb = round(float(file_size_kb) / 1024, 1)
                    st.caption(f"Size: {file_size_mb} MB")

    # 5. Downloadable Report
    with tabs[4]:
        st.markdown("**Available Reports**")
        
        reports = find_value_in_data(thread_data, ["reports"])
        if reports and isinstance(reports, list):
            for report in reports:
                if isinstance(report, dict):
                    with st.container():
                        cols = st.columns([4, 1])
                        with cols[0]:
                            st.markdown(f"#### {report.get('name', 'Report')}")
                            if report.get('size'):
                                st.caption(f"{report.get('size')} KB")
                        with cols[1]:
                            if report.get('content'):
                                st.download_button(
                                    "📥 Download",
                                    report['content'],
                                    file_name=report.get('name', 'report.txt'),
                                    mime='text/plain',
                                    use_container_width=True,
                                )
                    st.divider()
        else:
            st.info("No reports available for download.")

def _render_market_research(analysis):
    """
    Helper function to render market research results in a structured format.
    
    Args:
        analysis: Dictionary containing market research data matching MarketResearchDetails schema
    """
    # Display basic market information
    st.write("**Brand Name:**", analysis.get("brand_name", "N/A"))
    st.write("**Industry:**", analysis.get("industry_name", "N/A"))
    
    # Market metrics in columns
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Market Size:**", analysis.get("market_size", "N/A"))
        st.write("**Market Growth Rate:**", analysis.get("market_growth_rate", "N/A"))
        st.write("**Market Viability:**", analysis.get("market_viability", "N/A"))
    with col2:
        st.write("**Target Audience Fit:**", analysis.get("target_audience_fit", "N/A"))
        st.write("**Market Opportunity:**", analysis.get("market_opportunity", "N/A"))
    
    # Create tabs for detailed analysis
    market_tabs = st.tabs(["Trends & Competition", "Risks & Barriers", "Customer Analysis", "Recommendations"])
    
    # Trends & Competition tab
    with market_tabs[0]:
        st.write("**Emerging Trends**")
        st.write(analysis.get("emerging_trends", "No trend data available"))
        
        st.write("**Key Competitors**")
        competitors = analysis.get("key_competitors", [])
        if competitors:
            # Handle both string and list formats
            if isinstance(competitors, str):
                # Split by newlines if it's a string with multiple competitors
                competitor_list = [comp.strip() for comp in competitors.split('\n') if comp.strip()]
            else:
                competitor_list = competitors
                
            for competitor in competitor_list:
                st.markdown(f"- {competitor}")
        else:
            st.write("No competitor data available")
            
        st.write("**Competitive Analysis**")
        st.write(analysis.get("competitive_analysis", "No competitive analysis available"))
    
    # Risks & Barriers tab
    with market_tabs[1]:
        st.write("**Potential Risks**")
        st.write(analysis.get("potential_risks", "No risk data available"))
        
        st.write("**Market Entry Barriers**")
        st.write(analysis.get("market_entry_barriers", "No barrier data available"))
    
    # Customer Analysis tab
    with market_tabs[2]:
        st.write("**Customer Pain Points**")
        pain_points = analysis.get("customer_pain_points", [])
        if pain_points:
            # Handle both string and list formats
            if isinstance(pain_points, str):
                # Split by newlines if it's a string with multiple points
                points = [point.strip() for point in pain_points.split('\n') if point.strip()]
            else:
                points = pain_points
                
            for point in points:
                st.markdown(f"- {point}")
        else:
            st.write("No customer pain points identified")
    
    # Recommendations tab
    with market_tabs[3]:
        st.write("**Strategic Recommendations**")
        st.write(analysis.get("recommendations", "No recommendations available"))

# Main application layout
st.title("MAE Brand Namer")
st.caption("AI-driven brand naming and strategic analysis, powered by Alina Wheeler's methodology. Provides comprehensive insights: linguistic, semantic, cultural, SEO, domain, market research, targeted persona surveys (derived from AI generated synthetic personas), and competitive intelligence. For efficient, data-backed brand decisions.")

# Sidebar for inputs
with st.sidebar:
    st.subheader("Brand Requirements")
    
    # Example templates
    st.caption("Quick Templates (click to use)")
    template_cols = st.columns(2)
    
    for i, (name, prompt) in enumerate(example_prompts.items()):
        with template_cols[i % 2]:
            if st.button(name, help=prompt):
                st.session_state.user_input = prompt
                st.rerun()
    
    st.markdown("---")
    
    # Main input
    user_input = st.text_area(
        "Brand Description",
        key="user_input",
        placeholder="Example: A global enterprise software company specializing in supply chain optimization",
        height=120
    )
    
    # Create callback functions to maintain hierarchy
    def on_industry_change():
        """Reset sector and subsector when industry changes"""
        st.session_state.industry_selection["sector"] = ""
        st.session_state.industry_selection["subsector"] = ""

    def on_sector_change():
        """Reset subsector when sector changes"""
        st.session_state.industry_selection["subsector"] = ""

    # Advanced parameters in expander
    with st.expander("Additional Parameters", expanded=False):
        # Industry selection with 3-level hierarchy
        st.markdown("#### Industry Classification")
        
        # Industry dropdown (top level)
        industry = st.selectbox(
            "Industry",
            options=[""] + list(INDUSTRY_HIERARCHY.keys()),
            key="industry_dropdown",
            index=0,  # Start with empty selection
            on_change=on_industry_change,
            format_func=lambda x: x if x else "Select Industry (Optional)"
        )
        
        # Store in session state
        st.session_state.industry_selection["industry"] = industry
        
        # Sector dropdown (dependent on industry)
        if industry:
            sector_options = [""] + list(INDUSTRY_HIERARCHY.get(industry, {}).keys())
            sector = st.selectbox(
                "Sector",
                options=sector_options,
                key="sector_dropdown",
                index=0,  # Start with empty selection
                on_change=on_sector_change,
                format_func=lambda x: x if x else "Select Sector (Optional)"
            )
            # Store in session state
            st.session_state.industry_selection["sector"] = sector
            
            # Subsector dropdown (dependent on industry and sector)
            if sector:
                subsector_options = [""] + INDUSTRY_HIERARCHY.get(industry, {}).get(sector, [])
                subsector = st.selectbox(
                    "Subsector",
                    options=subsector_options,
                    key="subsector_dropdown",
                    index=0,  # Start with empty selection
                    format_func=lambda x: x if x else "Select Subsector (Optional)"
                )
                # Store in session state
                st.session_state.industry_selection["subsector"] = subsector
        
        # Create an industry info dictionary to pass to the prompt builder
        industry_info = {
            "industry": st.session_state.industry_selection["industry"],
            "sector": st.session_state.industry_selection["sector"],
            "subsector": st.session_state.industry_selection["subsector"]
        }
        
        st.markdown("#### Additional Brand Context")
        target_audience = st.text_input(
            "Target Market",
            placeholder="e.g., Enterprise manufacturing companies"
        )
        
        geographic_scope = st.selectbox(
            "Market Scope",
            ["", "Global Enterprise", "Regional", "National", "Local"]
        )
        
        name_style = st.multiselect(
            "Brand Positioning",
            ["Enterprise", "Technical", "Professional", "Innovative", "Traditional"]
        )
        
        # Build complete prompt with additional requirements
        complete_prompt = build_complete_prompt(
            user_input,
            industry_info,
            target_audience,
            geographic_scope,
            name_style
        )
    
    # Generate button
    generate_button = st.button("Generate Brand Names", type="primary", use_container_width=True)
    
    # Display favorites
    if st.session_state.favorite_names:
        st.markdown("---")
        st.subheader("Favorite Names")
        for name in st.session_state.favorite_names:
            cols = st.columns([4, 1])
            with cols[0]:
                st.markdown(f"**{name}**")
            with cols[1]:
                if st.button("✖️", key=f"remove_{name}"):
                    remove_from_favorites(name)
                    st.rerun()

# Main content area with tabs
tab1, tab2 = st.tabs(["Generator", "History"])

with tab1:
    # Message area
    if not user_input.strip():
        st.info("Enter your brand requirements in the sidebar to get started.")
    
    # Results area - modify the order and structure
    main_content = st.container()
    with main_content:
        results_container = st.container()
    
    # Debug section needs to be created BEFORE generation starts
    debug_header = st.container()
    with debug_header:
        st.markdown("---")
        st.subheader("Name Generation Flow")
        st.caption("This section shows detailed information about each step in the graph execution pipeline.")
    
    # Create a container for Streamlit callback and place it before the progress indicators
    st_callback_container = st.container()
    # Initialize LangChain callback handler for Streamlit
    st_callback = StreamlitCallbackHandler(st_callback_container, expand_new_thoughts=False, max_thought_containers=10)

    # Progress indicators
    progress_bar = st.progress(0)
    status_container = st.container()
    
    # Show persisted debug data if we have it (from previous runs/tab switches)
    debug_container = st.container()
    with debug_container:
        if "generation_complete" in st.session_state and st.session_state.generation_complete:
            if "raw_debug_data" in st.session_state and len(st.session_state.raw_debug_data) > 0:
                st.write(f"Debug data available: {len(st.session_state.raw_debug_data)} events")
                
                # Extract LangGraph-specific events
                langgraph_events = [
                    event for event in st.session_state.raw_debug_data 
                    if (event.get("type") == "status" and 
                        "metadata" in event and 
                        "langgraph_node" in event.get("metadata", {}))
                ]
                
                # Extract streaming deltas and unknown events
                delta_events = [
                    event for event in st.session_state.raw_debug_data
                    if "delta" in event and isinstance(event["delta"], dict)
                ]
                
                unknown_events = [
                    event for event in st.session_state.raw_debug_data
                    if event.get("type", "unknown") == "unknown"
                ]
                
                # Display LangGraph execution events
                if langgraph_events:
                    st.subheader("LangGraph Execution Path")
                    for i, event in enumerate(langgraph_events):
                        metadata = event.get("metadata", {})
                        node_name = metadata.get("langgraph_node", "Unknown")
                        step = metadata.get("langgraph_step", "?")
                        
                        with st.expander(f"Step {step}: {node_name}", expanded=i==0):
                            # Show additional metadata if available
                            col1, col2 = st.columns(2)
                            with col1:
                                if "ls_model_name" in metadata:
                                    st.markdown(f"**Model:** {metadata.get('ls_model_name')}")
                                if "prompt_tokens" in metadata:
                                    st.markdown(f"**Tokens:** {metadata.get('prompt_tokens')}")
                            with col2:
                                if "ls_provider" in metadata:
                                    st.markdown(f"**Provider:** {metadata.get('ls_provider')}")
                
                # Display streaming completion events
                if delta_events:
                    st.subheader("Streaming Completion Events")
                    for i, event in enumerate(delta_events[:10]):  # Limit to 10 for performance
                        delta = event.get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            with st.expander(f"Delta {i+1}: {content[:30]}...", expanded=False):
                                st.text(content)
                
                # Display unknown events
                if unknown_events:
                    st.subheader("Unrecognized Event Types")
                    st.caption("These events don't have a standard type field and may contain important metadata")
                    
                    for i, event in enumerate(unknown_events[:5]):  # Limit to 5 for UI clarity
                        event_keys = list(event.keys())
                        if "content" in event:
                            title = f"Content Chunk: {event.get('content')[:20]}..."
                        else:
                            title = f"Unknown Event {i+1}: Keys={', '.join(event_keys[:3])}..."
                        
                        with st.expander(title, expanded=i==0):
                            # Show a formatted version of the event
                            st.json(event)
                
                # Still show raw data for complete visibility
                with st.expander("View Raw Event Data", expanded=False):
                    st.json(st.session_state.raw_debug_data[:10])

    # Process generation
    if generate_button:
        if not user_input.strip():
            st.error("Please provide a description of your brand requirements.")
            st.stop()
            
        # Clear debug data from previous runs
        if "debug_data" not in st.session_state:
            st.session_state.debug_data = []
        else:
            st.session_state.debug_data = []
        
        if "raw_debug_data" not in st.session_state:
            st.session_state.raw_debug_data = []
        else:
            st.session_state.raw_debug_data = []
        
        # Display initial status
        status_container.info("Initializing generation process...")
        
        # Build complete prompt with additional requirements
        complete_prompt = build_complete_prompt(
            user_input,
            industry_info,
            target_audience,
            geographic_scope,
            name_style
        )
        
        # Store the current request in session state
        current_run = {
            "prompt": complete_prompt,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
            "results": None,
            "thread_id": None
        }
        st.session_state.history.append(current_run)
        current_index = len(st.session_state.history) - 1
        
        # Clear previous results - but only if we have new data
        with results_container:
            if not st.session_state.generation_complete:
                st.empty()
        
        try:
            # API headers
            headers = {
                "X-Api-Key": API_KEY,
                "Content-Type": "application/json"
            }
            
            # Create a new thread
            thread_response = requests.post(
                f"{API_URL}/threads",
                headers=headers,
                json={}
            )
            thread_response.raise_for_status()
            thread_id = thread_response.json()["thread_id"]
            
            # Save current thread ID to session state
            st.session_state.current_thread_id = thread_id
            current_run["thread_id"] = thread_id
            
            # Start a run with the user input
            run_response = requests.post(
                f"{API_URL}/threads/{thread_id}/runs/stream",
                headers=headers,
                json={
                    "assistant_id": ASSISTANT_ID,
                    "input": {
                        "user_prompt": complete_prompt
                    }
                },
                stream=True
            )
            run_response.raise_for_status()
            
            # Process the stream
            generated_names, evaluations = process_stream_data(
                run_response.iter_lines(),
                results_container,
                status_container,
                progress_bar
            )
            
            # If we didn't get LangGraph data, try to get it directly from LangSmith
            if not st.session_state.langsmith_trace_ids and thread_id:
                try:
                    # Get run details to extract LangSmith trace IDs
                    thread_runs = get_thread_runs(thread_id)
                    logging.debug(f"Retrieved {len(thread_runs) if thread_runs else 0} runs for thread {thread_id}")
                    
                    if thread_runs:
                        for run in thread_runs:
                            run_id = run.get("run_id")
                            if run_id:
                                # Add run ID to the trace IDs
                                st.session_state.langsmith_trace_ids.add(run_id)
                                logging.debug(f"Added run_id {run_id} from thread runs")
                                
                                # Get the detailed run info
                                run_details = get_run_details(thread_id, run_id)
                                if run_details and "metadata" in run_details:
                                    metadata = run_details.get("metadata", {})
                                    # Look for trace IDs in metadata
                                    if "ls_run_id" in metadata:
                                        st.session_state.langsmith_trace_ids.add(metadata["ls_run_id"])
                                        logging.debug(f"Added ls_run_id {metadata['ls_run_id']} from run metadata")
                                    if "ls_parent_run_id" in metadata:
                                        st.session_state.langsmith_trace_ids.add(metadata["ls_parent_run_id"])
                                        logging.debug(f"Added ls_parent_run_id {metadata['ls_parent_run_id']} from run metadata")
                except Exception as e:
                    logging.error(f"Error fetching additional trace info: {str(e)}")
            
            # Manual debug log if we didn't capture anything
            if len(st.session_state.raw_debug_data) == 0:
                logging.warning("No debug data was captured during processing. Creating synthetic debug data.")
                
                # Create synthetic debug data
                debug_entry = {
                    "type": "status",
                    "message": "Generation completed",
                    "metadata": {
                        "langgraph_node": "brand_generator",
                        "langgraph_step": "1",
                        "run_id": thread_id,
                        "thread_id": thread_id
                    }
                }
                
                # Add to our debug data
                st.session_state.raw_debug_data.append(debug_entry)
                
                # If we have at least one name, add it as result data
                if generated_names:
                    result_entry = {
                        "type": "result",
                        "data": {
                            "generated_names": generated_names,
                            "evaluations": evaluations
                        }
                    }
                    st.session_state.raw_debug_data.append(result_entry)
            
            # Update session state
            current_run["status"] = "completed"
            current_run["generated_names"] = generated_names
            current_run["evaluations"] = evaluations
            st.session_state.history[current_index] = current_run
            st.session_state.generation_complete = True

            # Log the final results
            logging.debug(f"Final generation results: {len(generated_names)} names")
            for name in generated_names:
                logging.debug(f"Generated name: {name}")

            # Ensure results are displayed clearly
            with results_container:
                st.markdown("## Final Results")
                if generated_names:
                    st.success(f"Successfully generated {len(generated_names)} brand names")
                    
                    # Check for report URL in debug data
                    report_url = None
                    for event in st.session_state.raw_debug_data:
                        # Look for events with report_url
                        if isinstance(event, dict):
                            # Check in different possible locations
                            if "report_url" in event:
                                report_url = event["report_url"]
                                break
                            elif "data" in event and isinstance(event["data"], dict) and "report_url" in event["data"]:
                                report_url = event["data"]["report_url"]
                                break
                            elif "output" in event and isinstance(event["output"], dict) and "report_url" in event["output"]:
                                report_url = event["output"]["report_url"]
                                break
                            elif "result" in event and isinstance(event["result"], dict) and "report_url" in event["result"]:
                                report_url = event["result"]["report_url"]
                                break
                    
                    # Display report URL if found
                    if report_url:
                        st.info("📄 Report generated!")
                        st.markdown(f"[Download the full brand analysis report]({report_url})")
                    
                    # Display each name with its evaluation
                    for name_data in generated_names:
                        # Extract the name string if it's a dictionary object
                        if isinstance(name_data, dict):
                            name = name_data.get("brand_name", "")
                        else:
                            name = str(name_data)
                            
                        if not name:  # Skip empty names
                            continue
                            
                        # Use more appropriate heading level
                        st.markdown(f"### {name}")
                        
                        # Add category as caption if available
                        if isinstance(name_data, dict) and "naming_category" in name_data:
                            st.caption(f"Category: {name_data['naming_category']}")
                        
                        if name in evaluations:
                            with st.expander("View analysis"):
                                col1, col2 = st.columns([3, 2])
                                with col1:
                                    st.markdown("#### Analysis")
                                    st.write(evaluations[name].get("analysis", "No analysis available"))
                                with col2:
                                    st.write("**Metrics:**")
                                    for key, value in evaluations[name].items():
                                        if key != "analysis" and value:
                                            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                        st.markdown("---")
                else:
                    st.warning("No names were generated. Please check the debug information below.")

            # Display debug data in case it wasn't shown
            with debug_container:
                st.write(f"Debug data count: {len(st.session_state.raw_debug_data)}")
                
                # Display LangSmith trace IDs if available
                if "langsmith_trace_ids" in st.session_state and st.session_state.langsmith_trace_ids:
                    st.subheader("LangSmith Traces")
                    valid_traces = []
                    
                    for trace_id in st.session_state.langsmith_trace_ids:
                        # Create LangSmith trace URL
                        langsmith_url = f"https://smith.langchain.com/traces/{trace_id}"
                        
                        # Add the trace link
                        with st.spinner(f"Validating trace {trace_id[:8]}..."):
                            is_valid = validate_langsmith_trace(trace_id)
                        
                        if is_valid:
                            st.markdown(f"✅ [View detailed trace on LangSmith]({langsmith_url})")
                            valid_traces.append(trace_id)
                        else:
                            st.markdown(f"❌ Trace {trace_id[:8]}... may not be available")
                    
                    if valid_traces:
                        st.info(f"LangSmith traces provide the most detailed view of your flow's execution. {len(valid_traces)} valid trace(s) found.")
                    else:
                        st.warning("No valid LangSmith traces were found. This might be due to API limitations or LangSmith configuration.")
                else:
                    st.info("No LangSmith traces were captured during execution. This may be due to the LangSmith tracing being disabled in your LangGraph flow.")
                    
                    # Offer a manual lookup option
                    run_id_manual = st.text_input("Enter a run ID manually to check LangSmith:")
                    if run_id_manual and st.button("Check Trace"):
                        with st.spinner("Validating trace ID..."):
                            is_valid = validate_langsmith_trace(run_id_manual)
                        
                        if is_valid:
                            langsmith_url = f"https://smith.langchain.com/traces/{run_id_manual}"
                            st.success(f"✅ Valid trace found! [View on LangSmith]({langsmith_url})")
                        else:
                            st.error("❌ No valid trace found with that ID")

            # Force refresh the history display
            st.rerun()

        except requests.RequestException as e:
            st.error(f"Error connecting to the API: {str(e)}")
            current_run["status"] = "failed"
            current_run["error"] = str(e)
            st.session_state.history[current_index] = current_run
            if st.checkbox("Show detailed error"):
                st.code(str(e))

# History tab
with tab2:
    st.subheader("Generation History")
    
    # Add refresh button
    if st.button("Refresh History"):
        # Clear the cache to force fresh data fetch
        st.cache_data.clear()
        st.toast("Refreshing data...")
        
        # Refresh the page to ensure all data is updated
        st.rerun()
        
        # Also check all runs for completion and update statuses
        for i, run in enumerate(st.session_state.history):
            if run["status"] == "running":
                # Check if there are results
                if run.get("generated_names"):
                    st.session_state.history[i]["status"] = "completed"
    
    # Create tabs for local and API history
    history_tabs = st.tabs(["Current Session", "All Brand Name Generations"])
    
    # Current session history
    with history_tabs[0]:
        if not st.session_state.history:
            st.info("No generations in current session. Generate some brand names first!")
        else:
            for i, run in enumerate(reversed(st.session_state.history)):
                with st.expander(f"Generation {len(st.session_state.history) - i} - {run['timestamp']}", expanded=i==0):
                    st.write(f"**Status:** {run['status'].title()}")
                    st.write(f"**Prompt:** {run['prompt']}")
                    
                    # Display generated names, even for runs in "running" state that have results
                    if (run['status'] == "completed" or run.get("generated_names")) and run.get("generated_names"):
                        st.write("**Generated Names:**")
                        for name in run.get("generated_names", []):
                            cols = st.columns([4, 1])
                            with cols[0]:
                                st.markdown(f"- **{name}**")
                            with cols[1]:
                                if name in st.session_state.favorite_names:
                                    if st.button("❤️", key=f"h_unfav_{i}_{name}"):
                                        remove_from_favorites(name)
                                else:
                                    if st.button("🤍", key=f"h_fav_{i}_{name}"):
                                        add_to_favorites(name)
                    
                    # For runs that are still "running" but have no results, show a spinner
                    elif run['status'] == "running":
                        st.info("Generation in progress... Refresh to check for updates.")
                    
                    if run.get("thread_id"):
                        if st.button("Load Full Results", key=f"load_{i}"):
                            thread_data = get_thread_history(run["thread_id"])
                            render_thread_data(thread_data)
    
    # All API history
    with history_tabs[1]:
        # Fetch all threads from API
        with st.spinner("Loading past generations..."):
            all_threads = fetch_all_threads()
        
        if not all_threads:
            st.info("No generation history found in the API")
        else:
            st.success(f"Found {len(all_threads)} past generations")
            
            # First, show a summary table
            thread_data = []
            for thread in all_threads:
                # Extract thread info
                thread_id = thread.get("thread_id", "N/A")
                created_at = thread.get("created_at", "Unknown")
                if isinstance(created_at, str) and "T" in created_at:
                    created_at = created_at.split("T")[0]
                
                # Add to table data
                thread_data.append({
                    "Thread ID": thread_id[:8] + "..." if len(thread_id) > 8 else thread_id,
                    "Created": created_at,
                    "Full Thread ID": thread_id  # For reference
                })
            
            # Display as dataframe
            df = pd.DataFrame(thread_data)
            
            # Add selection functionality
            selected_thread = st.selectbox(
                "Filter by thread id below:",
                options=df["Full Thread ID"].tolist(),
                format_func=lambda x: f"Thread {x[:8]}... - {df[df['Full Thread ID']==x]['Created'].iloc[0]}"
            )
            
            # Show thread details when selected
            if selected_thread:
                st.markdown("**Brand Name Generation Report Details:**")
                
                # Get thread history
                thread_history = get_thread_history(selected_thread)
                
                # Render thread data
                render_thread_data(thread_history)

# Footer
st.markdown("---")
st.caption("MAE Brand Namer | Powered by LangGraph AI") 