from util import is_threshold_failed, get_aggregated_value

from os import environ, listdir
from traceback import format_exc
import requests
from json import loads
from datetime import datetime
import pytz
import sys

PROJECT_ID = environ.get('GALLOPER_PROJECT_ID')
URL = environ.get('GALLOPER_URL')
REPORT_ID = environ.get('REPORT_ID')
BUCKET = environ.get("TESTS_BUCKET")
REPORTS_BUCKET = environ.get("REPORTS_BUCKET")
TEST = environ.get("ARTIFACT")
TOKEN = environ.get("token")
PATH_TO_FILE = f'/tmp/{TEST}'
TESTS_PATH = environ.get("tests_path", '/')
TEST_NAME = environ.get("JOB_NAME")

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

    # Read results json file
    results_path = f"/browsertime/browsertime-results/{sys.argv[2]}/"
    dir_name = listdir(results_path)
    json_path = f"{results_path}{dir_name[0]}/browsertime.json"
    with open(json_path, "r") as f:
        json_data = loads(f.read())

        all_results = {"total": [], "speed_index": [], "time_to_first_byte": [], "time_to_first_paint": [],
                       "dom_content_loading": [], "dom_processing": [], "first_contentful_paint": [],
                       "largest_contentful_paint": [], "cumulative_layout_shift": [], "total_blocking_time": [],
                       "first_visual_change": [], "last_visual_change": []}
        test_thresholds_total = 0
        test_thresholds_failed = 0
        for page in json_data:
            page_thresholds_total = 0
            page_thresholds_failed = 0
            file_name = ""
            page_result = {"total": [each for each in page["fullyLoaded"]],
                           "speed_index": [each["SpeedIndex"] for each in page["visualMetrics"]],
                           "time_to_first_byte": [each["timings"]["ttfb"] for each in page["browserScripts"]],
                           "time_to_first_paint": [each["timings"]["firstPaint"] for each in page["browserScripts"]],
                           "dom_content_loading": [each["timings"]["navigationTiming"]["domContentLoadedEventEnd"]
                                                   for each in page["browserScripts"]],
                           "dom_processing": [each["timings"]["navigationTiming"]["domComplete"]
                                              for each in page["browserScripts"]],
                           "first_contentful_paint": [each["firstContentfulPaint"] for each in page["googleWebVitals"]],
                           "largest_contentful_paint": [each["largestContentfulPaint"] for each in
                                                        page["googleWebVitals"]],
                           "cumulative_layout_shift": [round(float(each["cumulativeLayoutShift"])) for each in
                                                       page["googleWebVitals"]],
                           "total_blocking_time": [each["totalBlockingTime"] for each in page["googleWebVitals"]],
                           "first_visual_change": [each["FirstVisualChange"] for each in page["visualMetrics"]],
                           "last_visual_change": [each["LastVisualChange"] for each in page["visualMetrics"]]}

            # Add page results to the summary dict
            for metric in list(all_results.keys()):
                all_results[metric].extend(page_result[metric])

            # aggregate page results
            aggregated_result = {"requests": len(page_result["total"]), "domains": 1, "time_to_interactive": 0} # there is no TTI in browsertime json
            for metric in list(page_result.keys()):
                aggregated_result[metric] = get_aggregated_value(sys.argv[3], page_result[metric])

            # Process thresholds with scope = every
            for th in every_thresholds:
                test_thresholds_total += 1
                page_thresholds_total += 1
                if not is_threshold_failed(aggregated_result.get(th["target"]), th["comparison"], th["metric"]):
                    print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                          f" comply with rule {th['comparison']} {th['metric']} [PASSED]")
                else:
                    test_thresholds_failed += 1
                    page_thresholds_failed += 1
                    print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                          f" violates rule {th['comparison']} {th['metric']} [FAILED]")

            # Process thresholds for current page
            for th in page_thresholds:
                if th["scope"] == f'{page["info"]["url"]}@open':
                    test_thresholds_total += 1
                    page_thresholds_total += 1
                    if not is_threshold_failed(aggregated_result.get(th["target"]), th["comparison"], th["metric"]):
                        print(f"Threshold: {th['name']} {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                              f" comply with rule {th['comparison']} {th['metric']} [PASSED]")
                    else:
                        test_thresholds_failed += 1
                        page_thresholds_failed += 1
                        print(f"Threshold: {th['name']} {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                              f" violates rule {th['comparison']} {th['metric']} [FAILED]")

            # Update report with page results
            data = {
                "name": page["info"]["url"],
                "type": "page",
                "identifier": f"{page['info']['url']}@open",
                "metrics": aggregated_result,
                "bucket_name": "reports",
                "file_name": file_name,
                "resolution": "auto",
                "browser_version": "chrome",
                "thresholds_total": page_thresholds_total,
                "thresholds_failed": page_thresholds_failed,
                "locators": [],
                "session_id": "session_id"
            }

            try:
                requests.post(f"{URL}/api/v1/observer/{PROJECT_ID}/{REPORT_ID}", json=data,
                              headers={'Authorization': f"Bearer {TOKEN}"})
            except Exception:
                print(format_exc())

    # Process thresholds with scope = all
    for th in all_thresholds:
        test_thresholds_total += 1
        if not is_threshold_failed(get_aggregated_value(th["aggregation"], all_results.get(th["target"])),
                                   th["comparison"], th["metric"]):
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                  f" comply with rule {th['comparison']} {th['metric']} [PASSED]")
        else:
            test_thresholds_failed += 1
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                  f" violates rule {th['comparison']} {th['metric']} [FAILED]")

    # Finalize report
    time = datetime.now(tz=pytz.timezone("UTC"))
    exception_message = ""
    if test_thresholds_total:
        violated = round(float(test_thresholds_failed / test_thresholds_total) * 100, 2)
        print(f"Failed thresholds: {violated}")
        if violated > 30:
            exception_message = f"Failed thresholds rate more then {violated}%"
    report_data = {
        "report_id": REPORT_ID,
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "status": "Finished",
        "thresholds_total": test_thresholds_total,
        "thresholds_failed": test_thresholds_failed,
        "exception": exception_message
    }

    try:
        requests.put(f"{URL}/api/v1/observer/{PROJECT_ID}", json=report_data,
                     headers={'Authorization': f"Bearer {TOKEN}"})
    except Exception:
        print(format_exc())

    # Email notification
    if len(sys.argv) > 4 and "email" in sys.argv[4].split(";"):
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
