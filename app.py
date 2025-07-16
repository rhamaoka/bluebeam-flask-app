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
    data = request.json
    session_id = data.get('sessionId')
    bluebeam_access_token = data.get('bluebeamAccessToken')
    drive_folder_id = data.get('driveFolderId')

    if not session_id or not bluebeam_access_token or not drive_folder_id:
        return jsonify({"error": "Missing parameters"}), 400

    files = drive_service.files().list(
        q=f"'{drive_folder_id}' in parents and mimeType='application/pdf'",
        fields="files(id, name)").execute().get('files', [])

    results = []
    for file in files:
        file_name = file['name']
        file_data = drive_service.files().get_media(fileId=file['id']).execute()

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

        results.append({"file": file_name, "status": "success"})

    return jsonify(results), 200

if __name__ == '__main__':
    app.run(debug=True)