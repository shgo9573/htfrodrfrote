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

# --- הגדרות API וסודות (ייטענו מ-GitHub Secrets) ---
YEMOT_USERNAME = os.environ.get("YEMOT_USERNAME")
YEMOT_PASSWORD = os.environ.get("YEMOT_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GIT_TOKEN = os.environ.get("GIT_TOKEN")
GMAIL_CREDENTIALS_JSON = os.environ.get("GMAIL_CREDENTIALS_JSON", "{}")
GMAIL_TOKEN_JSON = os.environ.get("GMAIL_TOKEN_JSON", "{}")
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "{}")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
GITHUB_REPO_FOR_CONVOS = "shgo9573/my-agent-chats" # Changed to hardcoded value

# --- הגדרות מערכת ---
YEMOT_API_URL = "https://www.call2all.co.il/ym/api"
RECORDING_PATH = "ivr/6/001.wav"  # הקלטה משלוחה 6
TTS_DESTINATION_PATH = "ivr/7/001.tts" # תשובה לשלוחה 7

# --- הגדרת Gemini ---
genai.configure(api_key=GEMINI_API_KEY)

# ==============================================================================
# --- כל הכלים שהסוכן יכול להשתמש בהם (הגרסה המלאה) ---
# ==============================================================================

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
        return json.dumps({"status": "success", "content": response.text[:4000]})\n    except Exception as e:\n        return json.dumps({"status": "error", "error": str(e)})\n\ndef execute_python_code(code: str) -> str:\n    """Executes a string of Python code and returns its output."""
    print(f"--- TOOL: execute_python_code(code='{code[:50]}...') ---")
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(code, {})
        return json.dumps({"status": "success", "output": buffer.getvalue()})
    except Exception as e:\n        return json.dumps({"status": "error", "error": str(e)})\n
def list_repo_contents(repo_name: str, path: str = "") -> str:
    """Lists the files and directories in a given path of a GitHub repository."""
    print(f"--- TOOL: list_repo_contents(repo_name='{repo_name}', path='{path}') ---")
    try:
        g = Github(GIT_TOKEN) # Changed GITHUB_TOKEN to GIT_TOKEN
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(path)
        file_list = [{"name": item.name, "type": item.type} for item in contents]
        return json.dumps(file_list)
    except Exception as e:
        return json.dumps({"error": str(e)})\n\ndef read_file_from_repo(repo_name: str, file_path: str) -> str:\n    """Reads the content of a specific file from a GitHub repository."""
    print(f"--- TOOL: read_file_from_repo(repo_name='{repo_name}', file_path='{file_path}') ---")
    try:
        g = Github(GIT_TOKEN) # Changed GITHUB_TOKEN to GIT_TOKEN
        repo = g.get_repo(repo_name)
        file_content = repo.get_contents(file_path)
        return json.dumps({"path": file_path, "content": base64.b64decode(file_content.content).decode('utf-8')})
    except Exception as e:\n        return json.dumps({"error": str(e)})\n\ndef create_or_update_file_in_repo(repo_name: str, file_path: str, content: str, commit_message: str) -> str:\n    """Creates a new file or updates an existing file in a GitHub repository."""
    print(f"--- TOOL: create_or_update_file_in_repo(repo_name='{repo_name}', file_path='{file_path}') ---")
    try:
        g = Github(GIT_TOKEN) # Changed GITHUB_TOKEN to GIT_TOKEN
        repo = g.get_repo(repo_name)
        try:
            file = repo.get_contents(file_path)
            repo.update_file(file_path, commit_message, content, file.sha)
            return json.dumps({"status": "updated", "path": file_path})\n        except UnknownObjectException:\n            repo.create_file(file_path, commit_message, content)\n            return json.dumps({"status": "created", "path": file_path})\n    except Exception as e:\n        return json.dumps({"error": str(e)})\n\ndef upload_to_drive(file_name: str, file_content: str) -> str:\n    """Creates a text file with given content and uploads it to Google Drive."""
    print(f"--- TOOL: upload_to_drive(file_name='{file_name}') ---")
    try:
        from google.oauth2 import service_account\n        from googleapiclient.discovery import build\n        from googleapiclient.http import MediaIoBaseUpload\n        if GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON == "{}":\n            return json.dumps({"error": "Google Drive credentials are not configured."})\n        creds = service_account.Credentials.from_service_account_info(json.loads(GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON))\n        service = build("drive", "v3", credentials=creds)\n        metadata = {"name": file_name, "parents": [GOOGLE_DRIVE_FOLDER_ID]}\n        media = MediaIoBaseUpload(io.BytesIO(file_content.encode()), mimetype='text/plain')\n        file = service.files().create(body=metadata, media_body=media, fields='id, webViewLink').execute()\n        return json.dumps({"message": "File uploaded successfully!", "link": file.get('webViewLink')})\n    except Exception as e:\n        return json.dumps({"error": str(e)})\n\ndef _get_gmail_service():\n    from google.oauth2.credentials import Credentials\n    from googleapiclient.discovery import build\n    if GMAIL_CREDENTIALS_JSON == "{}" or GMAIL_TOKEN_JSON == "{}":\n        raise Exception("Gmail credentials are not configured.")\n    creds_info = json.loads(GMAIL_TOKEN_JSON)\n    creds = Credentials.from_authorized_user_info(creds_info)\n    return build('gmail', 'v1', credentials=creds)\n\ndef read_emails_gmail_api(limit: int = 5) -> str:\n    """Reads the most recent unread emails from the inbox using the Gmail API."""
    print(f"--- TOOL: read_emails_gmail_api(limit={limit}) ---")
    try:\n        service = _get_gmail_service()\n        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=limit).execute()\n        messages = results.get('messages', [])\n        if not messages:\n            return json.dumps({"message": "No unread emails found."})
        emails = []\n        for msg_info in messages:\n            msg = service.users().messages().get(userId='me', id=msg_info['id']).execute()\n            headers = {h['name']: h['value'] for h in msg['payload']['headers']}\n            emails.append({"from": headers.get("From"), "subject": headers.get("Subject"), "snippet": msg.get("snippet")})\n        return json.dumps(emails)\n    except Exception as e:\n        return json.dumps({"error": str(e)})\n\ndef send_email_gmail_api(recipient: str, subject: str, body: str) -> str:\n    """Sends an email to a specified recipient using the Gmail API."""
    print(f"--- TOOL: send_email_gmail_api(recipient='{recipient}', subject='{subject}') ---")
    try:\n        from email.mime.text import MIMEText\n        service = _get_gmail_service()\n        message = MIMEText(body)\n        message['to'] = recipient\n        message['subject'] = subject\n        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()\n        create_message = {'raw': raw_message}\n        service.users().messages().send(userId="me", body=create_message).execute()\n        return json.dumps({"status": "success", "message": f"Email sent to {recipient}"})
    except Exception as e:\n        return json.dumps({"error": str(e)})\n\nAVAILABLE_TOOLS = {\n    "google_search": google_search,\n    "get_web_page_content": get_web_page_content,\n    "execute_python_code": execute_python_code,\n    "execute_shell_command": execute_shell_command,\n    "list_repo_contents": list_repo_contents,\n    "read_file_from_repo": read_file_from_repo,\n    "create_or_update_file_in_repo": create_or_update_file_in_repo,\n    "upload_to_drive": upload_to_drive,\n    "read_emails_gmail_api": read_emails_gmail_api,\n    "send_email_gmail_api": send_email_gmail_api,\n}\n\nSYSTEM_PROMPT = """\nYou are an autonomous agent. Your goal is to fulfill the user's request which will be provided as an audio recording.\nFirst, understand the task from the recording. Then, create a plan and execute it using the available tools.\nYou MUST use the tools to perform actions. Do not provide answers based on your internal knowledge if the task requires real-world data.\nYour final output must be a concise summary in Hebrew of the action you took and its result.\n"""\n\n# --- פונקציות לתקשורת עם ימות המשיח ---\ndef download_file(file_path):\n    print(f"Attempting to download file: {file_path}...")\n    try:\n        params = {'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD, 'path': file_path}\n        response = requests.post(f"{YEMOT_API_URL}/DownloadFile", data=params, timeout=30)\n        response.raise_for_status()\n        try:\n            error_data = response.json()\n            if error_data.get('responseStatus') == 'ERROR':\n                print(f"API Error while downloading: {error_data.get('message')}")\n                return None\n        except json.JSONDecodeError:\n            print("File downloaded successfully.")\n            return response.content\n    except requests.exceptions.HTTPError as e:\n        if e.response.status_code == 404:\n            print("File not found (404). This is normal if there's no new recording.")\n        else:\n            print(f"HTTP error during download: {e}")\n        return None\n    except requests.exceptions.RequestException as e:\n        print(f"Network error during download: {e}")\n        return None\n\ndef upload_tts_file(file_path, text_content):\n    print(f"Uploading TTS content to {file_path}...")\n    try:\n        payload = {'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD, 'path': file_path, 'convertAudio': '1'}\n        files = {'file': ('001.tts', text_content.encode('utf-8'), 'text/plain; charset=utf-8')}\n        response = requests.post(f"{YEMOT_API_URL}/UploadFile", data=payload, files=files, timeout=45)\n        response.raise_for_status()\n        data = response.json()\n        if data.get('responseStatus') == 'OK':\n            print("TTS file uploaded successfully!")\n            return True\n        else:\n            print(f"Upload failed: {data.get('message', 'No message')}")\n            return False\n    except requests.exceptions.RequestException as e:\n        print(f"Error during upload: {e}")\n        return False\n\ndef delete_file(file_path):\n    print(f"Deleting file: {file_path}...")\n    try:\n        params = {'username': YEMOT_USERNAME, 'password': YEMOT_PASSWORD, 'path': file_path}\n        response = requests.post(f"{YEMOT_API_URL}/RemoveFile", data=params, timeout=30)\n        response.raise_for_status()\n        data = response.json()\n        if data.get('responseStatus') == 'OK':\n            print("File deleted successfully.")\n            return True\n        else:\n            print(f"Deletion failed: {data.get('message', 'No message')}")\n            return False\n    except requests.exceptions.RequestException as e:\n        print(f"Error during deletion: {e}")\n        return False\n\n# --- הלוגיקה המרכזית של הסוכן ---\ndef run_agent_on_audio(audio_data):\n    print("Starting agent process on audio data...")\n    model_instance = genai.GenerativeModel(\n        model_name="gemini-2.5-pro",\n        tools=AVAILABLE_TOOLS.values(),\n        system_instruction=SYSTEM_PROMPT\n    )\n    chat = model_instance.start_chat()\n    \n    audio_part = {"mime_type": "audio/wav", "data": base64.b64encode(audio_data).decode()}\n    response = chat.send_message(["תמלל את ההקלטה, הבן את המשימה, ובצע אותה באמצעות הכלים.", audio_part])\n\n    for _ in range(10): # לולאת כלים מוגבלת ל-10 צעדים\n        try:\n            part = response.candidates[0].content.parts[0]\n            if not hasattr(part, 'function_call'):\n                break # אין קריאה לכלי, הגענו לתשובה סופית\n            function_call = part.function_call\n        except (IndexError, AttributeError):\n            break\n
        tool_name = function_call.name\n        tool_args = {key: value for key, value in function_call.args.items()}\n        print(f"--- Executing tool: {tool_name} with args: {tool_args} ---")\n        \n        function_to_call = AVAILABLE_TOOLS.get(tool_name)\n        if not function_to_call:\n            observation = f"Error: Tool '{tool_name}' not found."
        else:\n            try:\n                observation = function_to_call(**tool_args)\n            except Exception as e:\n                observation = json.dumps({"error": f"Error executing tool {tool_name}: {e}"})
        \n        print(f"--- Observation: {str(observation)[:300]}... ---")\n        time.sleep(2)\n        \n        response = chat.send_message(\n            genai.protos.Part(function_response=genai.protos.FunctionResponse(name=tool_name, response={"result": observation}))\n        )\n
    final_answer = response.text\n    print(f"Agent finished. Final answer: {final_answer}")\n    return final_answer\n
# --- הפונקציה הראשית של הסקריפט ---\ndef main():\n    print("--- Starting IVR Agent Workflow ---")\n    \n    if not all([YEMOT_USERNAME, YEMOT_PASSWORD, GEMINI_API_KEY]):\n        print("CRITICAL ERROR: Missing one or more required secrets (YEMOT_USERNAME, YEMOT_PASSWORD, GEMINI_API_KEY).")\n        return\n
    audio_content = download_file(RECORDING_PATH)\n    \n    if not audio_content:\n        print("--- No new recording found. Exiting workflow. ---")\n        return\n
    if len(audio_content) < 1000:\n        print("Recording is too small, likely empty. Deleting and exiting.")\n        delete_file(RECORDING_PATH)\n        return\n        \n    try:\n        final_response_text = run_agent_on_audio(audio_content)\n    except Exception as e:\n        print(f"A critical error occurred in the agent loop: {e}")\n        final_response_text = "אירעה שגיאה קריטית בתהליך עיבוד הבקשה."

    upload_success = upload_tts_file(TTS_DESTINATION_PATH, final_response_text)\n    \n    if upload_success:\n        delete_file(RECORDING_PATH)\n    \n    print("--- IVR Agent Workflow Finished ---")\n
if __name__ == "__main__":\n    main()\n