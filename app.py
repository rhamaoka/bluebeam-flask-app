from flask import Flask, request, jsonify
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = 'credentials.json'
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

@app.route('/')
def home():
    return "Hello, Bluebeam Flask App!"

@app.route('/upload', methods=['POST'])
def upload_files():
    debug_info = []  # Create a list to store debug messages clearly

    data = request.json
    session_id = data.get('sessionId')
    bluebeam_access_token = data.get('bluebeamAccessToken')
    drive_folder_id = data.get('driveFolderId')

    debug_info.append(f"Received sessionId: {session_id}")
    debug_info.append(f"Received driveFolderId: {drive_folder_id}")

    if not session_id or not bluebeam_access_token or not drive_folder_id:
        debug_info.append("Error: Missing parameters")
        return jsonify({"error": "Missing parameters", "debug": debug_info}), 400

    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=credentials)
        debug_info.append("Successfully authenticated with Google Drive.")
    except Exception as e:
        debug_info.append(f"Google Drive authentication error: {str(e)}")
        return jsonify({"error": "Google authentication failed", "debug": debug_info}), 500

    try:
        files = drive_service.files().list(
    q=f"'{drive_folder_id}' in parents",
    fields="files(id, name, mimeType)").execute().get('files', [])
        debug_info.append(f"Found {len(files)} PDF files in Google Drive folder.")
    except Exception as e:
        debug_info.append(f"Error fetching files from Google Drive: {str(e)}")
        return jsonify({"error": "Fetching files failed", "debug": debug_info}), 500

    results = []
    for file in files:
        file_name = file['name']
        debug_info.append(f"Processing file: {file_name}")

        try:
            file_data = drive_service.files().get_media(fileId=file['id']).execute()
            debug_info.append(f"Downloaded file '{file_name}' from Google Drive.")
        except Exception as e:
            debug_info.append(f"Error downloading '{file_name}': {str(e)}")
            results.append({"file": file_name, "status": "download failed"})
            continue  # Move to next file

        try:
            metadata_resp = requests.post(
                f"https://studioapi.bluebeam.com/publicapi/v1/sessions/{session_id}/files",
                json={"Name": file_name},
                headers={"Authorization": f"Bearer {bluebeam_access_token}"}
            )
            metadata_resp.raise_for_status()
            metadata = metadata_resp.json()
            upload_url = metadata['UploadUrl']
            file_id = metadata['Id']

            upload_resp = requests.put(upload_url, data=file_data, headers={
                'Content-Type': 'application/pdf',
                'x-amz-server-side-encryption': 'AES256'
            })
            upload_resp.raise_for_status()

            confirm_resp = requests.post(
                f"https://studioapi.bluebeam.com/publicapi/v1/sessions/{session_id}/files/{file_id}/confirm-upload",
                headers={"Authorization": f"Bearer {bluebeam_access_token}"}
            )
            confirm_resp.raise_for_status()

            debug_info.append(f"Uploaded and confirmed '{file_name}' successfully.")
            results.append({"file": file_name, "status": "success"})

        except Exception as e:
            debug_info.append(f"Error uploading '{file_name}' to Bluebeam: {str(e)}")
            results.append({"file": file_name, "status": "upload failed"})
            continue

    return jsonify({"uploaded_files": results, "debug": debug_info}), 200

if __name__ == '__main__':
    app.run(debug=True)