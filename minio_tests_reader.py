from os import environ
import requests
import zipfile
from traceback import format_exc

PROJECT_ID = environ.get('GALLOPER_PROJECT_ID')
URL = environ.get('GALLOPER_URL')
BUCKET = environ.get("TESTS_BUCKET")
TEST = environ.get("ARTIFACT")
TOKEN = environ.get("token")
PATH_TO_FILE = f'/tmp/{TEST}'
TESTS_PATH = environ.get("tests_path", '/')
REPORT_ID = environ.get('REPORT_ID')

if not all(a for a in [URL, BUCKET, TEST]):
    exit(0)

try:
    endpoint = f'/api/v1/artifacts/artifact/{PROJECT_ID}/{BUCKET}/{TEST}'
    headers = {'Authorization': f'bearer {TOKEN}'} if TOKEN else {}
    r = requests.get(f'{URL}/{endpoint}', allow_redirects=True, headers=headers)
    with open(PATH_TO_FILE, 'wb') as file_data:
        file_data.write(r.content)
    with zipfile.ZipFile(PATH_TO_FILE, 'r') as zip_ref:
        zip_ref.extractall(TESTS_PATH)

    headers = {'content-type': 'application/json', 'Authorization': f'bearer {TOKEN}'}
    url = f'{URL}/api/v1/ui_performance/report_status/{PROJECT_ID}/{REPORT_ID}'
    data = {"test_status": {"status": "In progress", "percentage": 10,
                            "description": "Test started."}}
    response = requests.put(url, json=data, headers=headers)
    try:
        print(response.json()["message"])
    except:
        print(response.text)
except Exception:
    print(format_exc())

