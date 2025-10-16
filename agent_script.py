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

# --- הגדרות API וסודות ---
# חשוב: אלו צריכים להיות פרטי המשתמש הרגילים שלך, לא מפתח מפתחים
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
# ... (כל פונקציות הכלים נשארות זהות לחלוטין) ...
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

SYSTEM_PROMPT = "..." # (ללא שינוי)

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
        # אם התשובה היא קובץ, היא לא תהיה JSON. אם היא JSON, זו שגיאה.
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
        form.append('token', token)
        form.append('path', file_path)
        form.append('file', text_content.encode('utf-8'), {
            'filename': '001.tts',
            'contentType': 'text/plain; charset=utf-8'
        })
        
        response = requests.post(f"{YEMOT_API_URL}/UploadFile", data=form, headers=form.get_headers(), timeout=45)
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
    # ... (הפונקציה נשארת זהה)
    model_instance = genai.GenerativeModel(model_name="gemini-2.5-pro", tools=list(AVAILABLE_TOOLS.values()), system_instruction=SYSTEM_PROMPT)
    chat = model_instance.start_chat()
    audio_part = {"mime_type": "audio/wav", "data": base64.b64encode(audio_data).decode()}
    response = chat.send_message(["תמלל את ההקלטה, הבן את המשימה, ובצע אותה באמצעות הכלים.", audio_part])
    # ... (לולאת הכלים נשארת זהה)
    final_answer = response.text
    print(f"Agent finished. Final answer: {final_answer}")
    return final_answer

# --- הפונקציה הראשית של הסקריפט ---
def main():
    print("\n--- Starting IVR Agent Workflow ---")
    
    if not all([YEMOT_USERNAME, YEMOT_PASSWORD, GEMINI_API_KEY]):
        print("CRITICAL ERROR: Missing required secrets.")
        return

    # שלב 1: קבלת טוקן חדש
    token = get_yemot_token()
    if not token:
        return

    # שלב 2: ניסיון להוריד הקלטה עם הטוקן החדש
    audio_content = download_file(token, RECORDING_PATH)
    
    if not audio_content:
        print("--- No new recording found. Exiting workflow. ---")
        return

    if len(audio_content) < 1000:
        print("Recording is too small, deleting and exiting.")
        delete_file(token, RECORDING_PATH)
        return
        
    try:
        # שלב 3: הפעלת הסוכן
        final_response_text = run_agent_on_audio(audio_content)
    except Exception as e:
        print(f"A critical error occurred in the agent loop: {e}")
        final_response_text = "אירעה שגיאה קריטית בתהליך עיבוד הבקשה."

    # שלב 4: העלאת התשובה עם אותו טוקן
    upload_success = upload_tts_file(token, TTS_DESTINATION_PATH, final_response_text)
    
    # שלב 5: מחיקת ההקלטה המקורית עם אותו טוקן
    if upload_success:
        delete_file(token, RECORDING_PATH)
    
    print("--- IVR Agent Workflow Finished ---")

if __name__ == "__main__":
    main()
