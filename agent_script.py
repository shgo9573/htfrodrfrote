# agent_script.py
import os
import requests
import google.generativeai as genai
import json
import base64
import time
import subprocess
import contextlib
import io
from github import Github, UnknownObjectException
from ddgs import DDGS
from formdata import FormData # ============================ התיקון נמצא כאן ============================

# --- הגדרות API וסודות ---
YEMOT_USERNAME = os.environ.get("YEMOT_USERNAME")
YEMOT_PASSWORD = os.environ.get("YEMOT_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
# ... הוסף כאן טעינה של שאר הסודות אם צריך ...

# --- הגדרות מערכת ---
YEMOT_API_URL = "https://www.call2all.co.il/ym/api"
RECORDING_PATH = "ivr/6/001.wav"
TTS_DESTINATION_PATH = "ivr/7/001.tts"

# --- הגדרת Gemini ---
genai.configure(api_key=GEMINI_API_KEY)

# --- כל הכלים שהסוכן יכול להשתמש בהם ---
def google_search(query: str) -> str:
    """Searches the web for up-to-date information on a given query."""
    print(f"--- TOOL: google_search(query='{query}') ---")
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
        return json.dumps(results) if results else json.dumps({"message": "No results found."})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ... (וכך הלאה עבור כל שאר הכלים)

AVAILABLE_TOOLS = {
    "google_search": google_search,
    # ... הוסף כאן את שאר הכלים שלך
}

SYSTEM_PROMPT = """
You are an autonomous agent. Your goal is to fulfill the user's request which will be provided as an audio recording.
First, understand the task from the recording. Then, create a plan and execute it using the available tools.
You MUST use the tools to perform actions. Do not provide answers based on your internal knowledge if the task requires real-world data.
Your final output must be a concise summary in Hebrew of the action you took and its result.
"""

# --- פונקציות לתקשורת עם ימות המשיח (עם שימוש בטוקן) ---

def get_yemot_token():
    """
    מתחבר לימות המשיח ומחזיר טוקן זמני.
    """
    print("--- Step 1: Getting a fresh session token from Yemot... ---")
    try:
        response = requests.get(f"{YEMOT_API_URL}/Login", params={'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD}, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get('responseStatus') == 'OK':
            print(">>> Login successful! Token received. <<<")
            return data.get('token')
        else:
            print(f"CRITICAL ERROR: Yemot login failed: {data.get('message', 'No message')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"CRITICAL ERROR: Network error during login: {e}")
        return None

def download_file(token, file_path):
    print(f"--- Step 2: Attempting to download file: {file_path}... ---")
    try:
        params = {'token': token, 'path': file_path}
        response = requests.get(f"{YEMOT_API_URL}/DownloadFile", params=params, timeout=30)
        response.raise_for_status()
        if 'application/json' in response.headers.get('Content-Type', ''):
            error_data = response.json()
            print(f"API Error while downloading: {error_data.get('message')}")
            return None
        print(">>> File downloaded successfully. <<<")
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Network error during download: {e}")
        return None

def upload_tts_file(token, file_path, text_content):
    print(f"--- Step 4: Uploading TTS content to {file_path}... ---")
    try:
        form = FormData()
        form.add_field('token', token)
        form.add_field('path', file_path)
        form.add_field('file', text_content.encode('utf-8'), filename='001.tts', content_type='text/plain; charset=utf-8')
        
        response = requests.post(f"{YEMOT_API_URL}/UploadFile", data=form.to_bytes(), headers=form.get_headers(), timeout=45)
        response.raise_for_status()
        data = response.json()
        if data.get('responseStatus') == 'OK':
            print(">>> TTS file uploaded successfully! <<<")
            return True
        else:
            print(f"Upload failed: {data.get('message', 'No message')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error during upload: {e}")
        return False

def delete_file(token, file_path):
    print(f"--- Step 5: Deleting file: {file_path}... ---")
    try:
        params = {'token': token, 'path': file_path}
        response = requests.get(f"{YEMOT_API_URL}/RemoveFile", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get('responseStatus') == 'OK':
            print(">>> File deleted successfully. <<<")
            return True
        else:
            print(f"Deletion failed: {data.get('message', 'No message')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error during deletion: {e}")
        return False

# --- הלוגיקה המרכזית של הסוכן ---
def run_agent_on_audio(audio_data):
    print("--- Step 3: Starting agent process on audio data... ---")
    model_instance = genai.GenerativeModel(
        model_name="gemini-2.5-pro",
        tools=list(AVAILABLE_TOOLS.values()),
        system_instruction=SYSTEM_PROMPT
    )
    chat = model_instance.start_chat()
    audio_part = {"mime_type": "audio/wav", "data": base64.b64encode(audio_data).decode()}
    response = chat.send_message(["תמלל את ההקלטה, הבן את המשימה, ובצע אותה באמצעות הכלים.", audio_part])
    
    for _ in range(10):
        try:
            part = response.candidates[0].content.parts[0]
            if not hasattr(part, 'function_call'):
                break
            function_call = part.function_call
        except (IndexError, AttributeError):
            break

        tool_name = function_call.name
        tool_args = {key: value for key, value in function_call.args.items()}
        print(f"--- Executing tool: {tool_name} with args: {tool_args} ---")
        
        function_to_call = AVAILABLE_TOOLS.get(tool_name)
        if not function_to_call:
            observation = f"Error: Tool '{tool_name}' not found."
        else:
            try:
                observation = function_to_call(**tool_args)
            except Exception as e:
                observation = json.dumps({"error": f"Error executing tool {tool_name}: {e}"})
        
        print(f"--- Observation: {str(observation)[:300]}... ---")
        time.sleep(2)
        
        response = chat.send_message(
            genai.protos.Part(function_response=genai.protos.FunctionResponse(name=tool_name, response={"result": observation}))
        )

    final_answer = response.text
    print(f"Agent finished. Final answer: {final_answer}")
    return final_answer

# --- הפונקציה הראשית של הסקריפט ---
def main():
    print("\n--- Starting IVR Agent Workflow ---")
    
    if not all([YEMOT_USERNAME, YEMOT_PASSWORD, GEMINI_API_KEY]):
        print("CRITICAL ERROR: Missing required secrets.")
        return

    token = get_yemot_token()
    if not token:
        return

    audio_content = download_file(token, RECORDING_PATH)
    
    if not audio_content:
        print("--- No new recording found. Exiting workflow. ---")
        return

    if len(audio_content) < 1000:
        print("Recording is too small, deleting and exiting.")
        delete_file(token, RECORDING_PATH)
        return
        
    try:
        final_response_text = run_agent_on_audio(audio_content)
    except Exception as e:
        print(f"A critical error occurred in the agent loop: {e}")
        final_response_text = "אירעה שגיאה קריטית בתהליך עיבוד הבקשה."

    upload_success = upload_tts_file(token, TTS_DESTINATION_PATH, final_response_text)
    
    if upload_success:
        delete_file(token, RECORDING_PATH)
    
    print("--- IVR Agent Workflow Finished ---")

if __name__ == "__main__":
    main()
