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
YEMOT_USERNAME = os.environ.get("YEMOT_USERNAME")
YEMOT_PASSWORD = os.environ.get("YEMOT_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GMAIL_CREDENTIALS_JSON = os.environ.get("GMAIL_CREDENTIALS_JSON", "{}")
GMAIL_TOKEN_JSON = os.environ.get("GMAIL_TOKEN_JSON", "{}")
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "{}")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

# --- הגדרות מערכת ---
YEMOT_API_URL = "https://www.call2all.co.il/ym/api"
RECORDING_PATH = "ivr2:/6/001.wav"
TTS_DESTINATION_PATH = "ivr2:/7/001.tts"

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

def execute_shell_command(command: str) -> str:
    """Executes a shell command. DANGEROUS: Use with extreme caution."""
    print(f"--- TOOL: execute_shell_command(command='{command}') ---")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
        return json.dumps({"status": "success", "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

def get_web_page_content(url: str) -> str:
    """Fetches the text content of a given web URL."""
    print(f"--- TOOL: get_web_page_content(url='{url}') ---")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return json.dumps({"status": "success", "content": response.text[:4000]})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

def execute_python_code(code: str) -> str:
    """Executes a string of Python code and returns its output."""
    print(f"--- TOOL: execute_python_code(code='{code[:50]}...') ---")
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(code, {})
        return json.dumps({"status": "success", "output": buffer.getvalue()})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

def list_repo_contents(repo_name: str, path: str = "") -> str:
    """Lists the files and directories in a given path of a GitHub repository."""
    print(f"--- TOOL: list_repo_contents(repo_name='{repo_name}', path='{path}') ---")
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(path)
        file_list = [{"name": item.name, "type": item.type} for item in contents]
        return json.dumps(file_list)
    except Exception as e:
        return json.dumps({"error": str(e)})

def read_file_from_repo(repo_name: str, file_path: str) -> str:
    """Reads the content of a specific file from a GitHub repository."""
    print(f"--- TOOL: read_file_from_repo(repo_name='{repo_name}', file_path='{file_path}') ---")
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_name)
        file_content = repo.get_contents(file_path)
        return json.dumps({"path": file_path, "content": base64.b64decode(file_content.content).decode('utf-8')})
    except Exception as e:
        return json.dumps({"error": str(e)})

def create_or_update_file_in_repo(repo_name: str, file_path: str, content: str, commit_message: str) -> str:
    """Creates a new file or updates an existing file in a GitHub repository."""
    print(f"--- TOOL: create_or_update_file_in_repo(repo_name='{repo_name}', file_path='{file_path}') ---")
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_name)
        try:
            file = repo.get_contents(file_path)
            repo.update_file(file_path, commit_message, content, file.sha)
            return json.dumps({"status": "updated", "path": file_path})
        except UnknownObjectException:
            repo.create_file(file_path, commit_message, content)
            return json.dumps({"status": "created", "path": file_path})
    except Exception as e:
        return json.dumps({"error": str(e)})

def upload_to_drive(file_name: str, file_content: str) -> str:
    """Creates a text file with given content and uploads it to Google Drive."""
    print(f"--- TOOL: upload_to_drive(file_name='{file_name}') ---")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        if GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON == "{}":
            return json.dumps({"error": "Google Drive credentials are not configured."})
        creds = service_account.Credentials.from_service_account_info(json.loads(GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON))
        service = build("drive", "v3", credentials=creds)
        metadata = {"name": file_name, "parents": [GOOGLE_DRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(io.BytesIO(file_content.encode()), mimetype='text/plain')
        file = service.files().create(body=metadata, media_body=media, fields='id, webViewLink').execute()
        return json.dumps({"message": "File uploaded successfully!", "link": file.get('webViewLink')})
    except Exception as e:
        return json.dumps({"error": str(e)})

def _get_gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    if GMAIL_CREDENTIALS_JSON == "{}" or GMAIL_TOKEN_JSON == "{}":
        raise Exception("Gmail credentials are not configured.")
    creds_info = json.loads(GMAIL_TOKEN_JSON)
    creds = Credentials.from_authorized_user_info(creds_info)
    return build('gmail', 'v1', credentials=creds)

def read_emails_gmail_api(limit: int = 5) -> str:
    """Reads the most recent unread emails from the inbox using the Gmail API."""
    print(f"--- TOOL: read_emails_gmail_api(limit={limit}) ---")
    try:
        service = _get_gmail_service()
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=limit).execute()
        messages = results.get('messages', [])
        if not messages:
            return json.dumps({"message": "No unread emails found."})
        emails = []
        for msg_info in messages:
            msg = service.users().messages().get(userId='me', id=msg_info['id']).execute()
            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
            emails.append({"from": headers.get("From"), "subject": headers.get("Subject"), "snippet": msg.get("snippet")})
        return json.dumps(emails)
    except Exception as e:
        return json.dumps({"error": str(e)})

def send_email_gmail_api(recipient: str, subject: str, body: str) -> str:
    """Sends an email to a specified recipient using the Gmail API."""
    print(f"--- TOOL: send_email_gmail_api(recipient='{recipient}', subject='{subject}') ---")
    try:
        from email.mime.text import MIMEText
        service = _get_gmail_service()
        message = MIMEText(body)
        message['to'] = recipient
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': raw_message}
        service.users().messages().send(userId="me", body=create_message).execute()
        return json.dumps({"status": "success", "message": f"Email sent to {recipient}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

AVAILABLE_TOOLS = {
    "google_search": google_search,
    "get_web_page_content": get_web_page_content,
    "execute_python_code": execute_python_code,
    "execute_shell_command": execute_shell_command,
    "list_repo_contents": list_repo_contents,
    "read_file_from_repo": read_file_from_repo,
    "create_or_update_file_in_repo": create_or_update_file_in_repo,
    "upload_to_drive": upload_to_drive,
    "read_emails_gmail_api": read_emails_gmail_api,
    "send_email_gmail_api": send_email_gmail_api,
}

SYSTEM_PROMPT = """
You are an autonomous agent. Your goal is to fulfill the user's request which will be provided as an audio recording.
First, understand the task from the recording. Then, create a plan and execute it using the available tools.
You MUST use the tools to perform actions. Do not provide answers based on your internal knowledge if the task requires real-world data.
Your final output must be a concise summary in Hebrew of the action you took and its result.
"""

# --- פונקציות לתקשורת עם ימות המשיח ---
def test_login():
    """
    מבצעת קריאת Login רק כדי לוודא שהפרטים נכונים והחיבור תקין.
    """
    print("--- Step 1: Testing Yemot connection... ---")
    try:
        response = requests.post(f"{YEMOT_API_URL}/Login", data={'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD}, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get('responseStatus') == 'OK':
            print(">>> Yemot connection successful! <<<")
            requests.post(f"{YEMOT_API_URL}/Logout", data={'token': data.get('token')})
            return True
        else:
            print(f"CRITICAL ERROR: Yemot login failed: {data.get('message', 'No message')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"CRITICAL ERROR: Network error during login test: {e}")
        return False

def download_file(file_path):
    print(f"--- Step 2: Attempting to download file: {file_path}... ---")
    try:
        params = {'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD, 'path': file_path}
        response = requests.post(f"{YEMOT_API_URL}/DownloadFile", data=params, timeout=30)
        response.raise_for_status()
        try:
            error_data = response.json()
            if error_data.get('responseStatus') == 'ERROR':
                print(f"API Message: {error_data.get('message')}")
                return None
        except json.JSONDecodeError:
            print(">>> File downloaded successfully. <<<")
            return response.content
    except requests.exceptions.RequestException as e:
        print(f"Network error during download: {e}")
        return None

def upload_tts_file(file_path, text_content):
    print(f"--- Step 4: Uploading TTS content to {file_path}... ---")
    try:
        payload = {'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD, 'path': file_path, 'convertAudio': '1'}
        files = {'file': ('001.tts', text_content.encode('utf-8'), 'text/plain; charset=utf-8')}
        response = requests.post(f"{YEMOT_API_URL}/UploadFile", data=payload, files=files, timeout=45)
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

def delete_file(file_path):
    print(f"--- Step 5: Deleting file: {file_path}... ---")
    try:
        params = {'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD, 'path': file_path}
        response = requests.post(f"{YEMOT_API_URL}/RemoveFile", data=params, timeout=30)
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
    model_instance = genai.GenerativeModel(model_name="gemini-2.5-pro", tools=list(AVAILABLE_TOOLS.values()), system_instruction=SYSTEM_PROMPT)
    chat = model_instance.start_chat()
    audio_part = {"mime_type": "audio/wav", "data": base64.b64encode(audio_data).decode()}
    response = chat.send_message(["תמלל את ההקלטה, הבן את המשימה, ובצע אותה באמצעות הכלים.", audio_part])
    for _ in range(10):
        try:
            part = response.candidates[0].content.parts[0]
            if not hasattr(part, 'function_call'): break
            function_call = part.function_call
        except (IndexError, AttributeError): break
        tool_name = function_call.name
        tool_args = {key: value for key, value in function_call.args.items()}
        print(f"--- Executing tool: {tool_name} with args: {tool_args} ---")
        function_to_call = AVAILABLE_TOOLS.get(tool_name)
        if not function_to_call: observation = f"Error: Tool '{tool_name}' not found."
        else:
            try: observation = function_to_call(**tool_args)
            except Exception as e: observation = json.dumps({"error": f"Error executing tool {tool_name}: {e}"})
        print(f"--- Observation: {str(observation)[:300]}... ---")
        time.sleep(2)
        response = chat.send_message(genai.protos.Part(function_response=genai.protos.FunctionResponse(name=tool_name, response={"result": observation})))
    final_answer = response.text
    print(f"Agent finished. Final answer: {final_answer}")
    return final_answer

# --- הפונקציה הראשית של הסקריפט ---
def main():
    print("\n--- Starting IVR Agent Workflow ---")
    
    if not all([YEMOT_USERNAME, YEMOT_PASSWORD, GEMINI_API_KEY]):
        print("CRITICAL ERROR: Missing required secrets.")
        return

    if not test_login():
        return

    audio_content = download_file(RECORDING_PATH)
    
    if not audio_content:
        print("--- No new recording found. Exiting workflow. ---")
        return

    if len(audio_content) < 1000:
        print("Recording is too small, likely empty. Deleting and exiting.")
        delete_file(RECORDING_PATH)
        return
        
    try:
        final_response_text = run_agent_on_audio(audio_content)
    except Exception as e:
        print(f"A critical error occurred in the agent loop: {e}")
        final_response_text = "אירעה שגיאה קריטית בתהליך עיבוד הבקשה."

    upload_success = upload_tts_file(TTS_DESTINATION_PATH, final_response_text)
    
    if upload_success:
        delete_file(RECORDING_PATH)
    
    print("--- IVR Agent Workflow Finished ---")

if __name__ == "__main__":
    main()
