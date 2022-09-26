from util import is_threshold_failed, get_aggregated_value, process_page_results, aggregate_results, update_report, \
    finalize_report, upload_distributed_report_files, upload_distributed_report, upload_static_files

import os
from traceback import format_exc
import requests
from json import loads
from datetime import datetime
import pytz
import sys

PROJECT_ID = os.environ.get('GALLOPER_PROJECT_ID')
URL = os.environ.get('GALLOPER_URL')
REPORT_ID = os.environ.get('REPORT_ID')
BUCKET = os.environ.get("TESTS_BUCKET")
REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET")
TEST = os.environ.get("ARTIFACT")
TOKEN = os.environ.get("token")
PATH_TO_FILE = f'/tmp/{TEST}'
TESTS_PATH = os.environ.get("tests_path", '/')
TEST_NAME = os.environ.get("JOB_NAME")

try:
    # Get thresholds
    res = None
    try:
        res = requests.get(
            f"{URL}/api/v1/thresholds/{PROJECT_ID}/ui?name={TEST_NAME}&environment=Default&order=asc",
            headers={'Authorization': f"Bearer {TOKEN}"})
    except Exception:
        print(format_exc())

    if not res or res.status_code != 200:
        thresholds = []

    try:
        thresholds = res.json()
    except ValueError:
        thresholds = []

    all_thresholds: list = list(filter(lambda _th: _th['scope'] == 'all', thresholds))
    every_thresholds: list = list(filter(lambda _th: _th['scope'] == 'every', thresholds))
    page_thresholds: list = list(filter(lambda _th: _th['scope'] != 'every' and _th['scope'] != 'all', thresholds))

    format_str = "%d%b%Y_%H:%M:%S"
    timestamp = datetime.now().strftime(format_str)
    upload_distributed_report(timestamp, URL, PROJECT_ID, TOKEN)
    results_path = f"/sitespeed.io/sitespeed-result/{sys.argv[2].replace('.', '_')}/"
    dir_name = os.listdir(results_path)
    upload_static_files(f"{results_path}{dir_name[0]}/", URL, PROJECT_ID, TOKEN)
    upload_distributed_report_files(f"{results_path}{dir_name[0]}/", timestamp, URL, PROJECT_ID, TOKEN, int(sys.argv[3]))
    results_path = f"{results_path}{dir_name[0]}/pages/"
    dir_names = os.listdir(results_path)
    all_results = {"total": [], "speed_index": [], "time_to_first_byte": [], "time_to_first_paint": [],
                   "dom_content_loading": [], "dom_processing": [], "first_contentful_paint": [],
                   "largest_contentful_paint": [], "cumulative_layout_shift": [], "total_blocking_time": [],
                   "first_visual_change": [], "last_visual_change": []}
    test_thresholds_total = 0
    test_thresholds_failed = 0
    sub_dir_names = []
    for each in dir_names:
        _sub_dirs = os.listdir(f"{results_path}{each}/")
        for _ in _sub_dirs:
            if os.path.isdir(f"{results_path}{each}/{_}"):
                if "index.html" in os.listdir(f"{results_path}{each}/{_}"):
                    _sub_dirs = [os.path.join(f"{results_path}{each}/", f"{_}/")]
                else:
                    _sub_dirs = [os.path.join(f"{results_path}{each}/{_}", f"{f}/") for f in os.listdir(f"{results_path}{each}/{_}")]
                sub_dir_names.extend(_sub_dirs)
    sub_dir_names = [x for x in sub_dir_names if os.path.isdir(x)]
    sub_dir_names.sort(key=lambda x: os.path.getmtime(x))
    for sub_dir_path in sub_dir_names:
        sub_dir = sub_dir_path.split("/")[-2]
        if os.path.isdir(f"{sub_dir_path}"):
            if "index.html" in os.listdir(sub_dir_path):
                try:
                    page_result = process_page_results(sub_dir, sub_dir_path, URL, PROJECT_ID, TOKEN, timestamp,
                                                       prefix="../../../", loops=int(sys.argv[3]))
                    # Add page results to the summary dict
                    for metric in list(all_results.keys()):
                        all_results[metric].extend(page_result[metric])
                    aggregated_result = aggregate_results(page_result)
                    update_report(sub_dir, aggregated_result, URL, PROJECT_ID, TOKEN, REPORT_ID, timestamp)
                except:
                    ...
            else:
                try:
                    for sub_sub_dir in os.listdir(sub_dir_path):
                        page_result = process_page_results(sub_sub_dir, f"{sub_dir_path}{sub_sub_dir}/", URL, PROJECT_ID,
                                                           TOKEN, timestamp, prefix="../../../../", loops=int(sys.argv[3]))
                        # Add page results to the summary dict
                        for metric in list(all_results.keys()):
                            all_results[metric].extend(page_result[metric])
                        aggregated_result = aggregate_results(page_result)
                        update_report(sub_sub_dir, aggregated_result, URL, PROJECT_ID, TOKEN, REPORT_ID, timestamp)
                except:
                    ...

    finalize_report(URL, PROJECT_ID, TOKEN, REPORT_ID)

    # Email notification
    if len(sys.argv) > 5 and "email" in sys.argv[5].split(";"):
        secrets_url = f"{URL}/api/v1/secrets/{PROJECT_ID}/"
        try:
            email_notification_id = requests.get(secrets_url + "email_notification_id",
                                                 headers={'Authorization': f'bearer {TOKEN}',
                                                          'Content-type': 'application/json'}
                                                 ).json()["secret"]
        except:
            email_notification_id = ""

        if email_notification_id:
            task_url = f"{URL}/api/v1/task/{PROJECT_ID}/{email_notification_id}"

            event = {
                "notification_type": "ui",
                "test_id": sys.argv[1],
                "report_id": REPORT_ID
            }

            res = requests.post(task_url, json=event, headers={'Authorization': f'bearer {TOKEN}',
                                                               'Content-type': 'application/json'})
            print(f"Email notification {res.text}")

except Exception:
    print(format_exc())
