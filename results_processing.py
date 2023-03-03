from util import is_threshold_failed, get_aggregated_value, process_page_results, aggregate_results, get_record, \
    finalize_report, upload_distributed_report_files, upload_distributed_report, upload_static_files, update_test_results

import os
from traceback import format_exc
import requests
from json import loads
from datetime import datetime
import pytz
import sys
from engagement_reporter import EngagementReporter


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
ENV = os.environ.get("ENV")


try:
    # Get thresholds
    res = None
    try:
        res = requests.get(
            f"{URL}/api/v1/ui_performance/thresholds/{PROJECT_ID}?test={TEST_NAME}&env={ENV}&order=asc",
            headers={'Authorization': f"Bearer {TOKEN}"})
    except Exception:
        print(format_exc())

    if not res or res.status_code != 200:
        thresholds = []

    try:
        thresholds = res.json()
    except ValueError:
        thresholds = []

    records = []

    failed_thresholds = []
    all_thresholds: list = list(filter(lambda _th: _th['scope'] == 'all', thresholds))
    every_thresholds: list = list(filter(lambda _th: _th['scope'] == 'every', thresholds))
    page_thresholds: list = list(filter(lambda _th: _th['scope'] != 'every' and _th['scope'] != 'all', thresholds))
    test_thresholds_total = 0
    test_thresholds_failed = 0

    format_str = "%d%b%Y_%H:%M:%S"
    timestamp = datetime.now().strftime(format_str)
    upload_distributed_report(timestamp, URL, PROJECT_ID, TOKEN)
    script_path_split = sys.argv[2].split('/')[-1]
    results_path = f"/sitespeed.io/sitespeed-result/{script_path_split.replace('.', '_')}/"
    dir_name = os.listdir(results_path)
    upload_static_files(f"{results_path}{dir_name[0]}/", URL, PROJECT_ID, TOKEN)
    upload_distributed_report_files(f"{results_path}{dir_name[0]}/", timestamp, URL, PROJECT_ID, TOKEN, int(sys.argv[3]))
    results_path = f"{results_path}{dir_name[0]}/pages/"
    dir_names = os.listdir(results_path)
    all_results = {"load_time": [], "speed_index": [], "time_to_first_byte": [], "time_to_first_paint": [],
                   "dom_content_loading": [], "dom_processing": [], "first_contentful_paint": [],
                   "largest_contentful_paint": [], "cumulative_layout_shift": [], "total_blocking_time": [],
                   "first_visual_change": [], "last_visual_change": [], "time_to_interactive": []}
    
    sub_dir_names = []
    for each in dir_names:
        _sub_dirs = os.listdir(f"{results_path}{each}/")
        for _ in _sub_dirs:
            if "index.html" in os.listdir(f"{results_path}{each}/{_}"):
                _sub_dirs = [os.path.join(f"{results_path}{each}/", f"{_}/")]
            else:
                _sub_dirs = [os.path.join(f"{results_path}{each}/{_}", f"{f}/") for f in os.listdir(f"{results_path}{each}/{_}")]
            sub_dir_names.extend(_sub_dirs)

    sub_dir_names.sort(key=lambda x: os.path.getmtime(x))
    for sub_dir_path in sub_dir_names:
        sub_dir = sub_dir_path.split("/")[-2]
        if "index.html" in os.listdir(sub_dir_path):
            page_result = process_page_results(sub_dir, sub_dir_path, URL, PROJECT_ID, TOKEN, timestamp,
                                               prefix="../../../", loops=int(sys.argv[3]))
            # Add page results to the summary dict
            for metric in list(all_results.keys()):
                try:
                    all_results[metric].extend(page_result[metric])
                except:
                    ...
            for i in range(len(page_result["load_time"])):
                records.append(get_record(sub_dir, page_result, timestamp, i))
            aggregated_result = aggregate_results(page_result)
            records.append(get_record(sub_dir, aggregated_result, timestamp, -1))
        else:
            for sub_sub_dir in os.listdir(sub_dir_path):
                page_result = process_page_results(sub_sub_dir, f"{sub_dir_path}{sub_sub_dir}/", URL, PROJECT_ID,
                                                   TOKEN, timestamp, prefix="../../../../", loops=int(sys.argv[3]))
                # Add page results to the summary dict
                for metric in list(all_results.keys()):
                    all_results[metric].extend(page_result[metric])
                for i in range(len(page_result["load_time"])):
                    records.append(get_record(sub_dir, page_result, timestamp, i))
                aggregated_result = aggregate_results(page_result)
                records.append(get_record(sub_dir, aggregated_result, timestamp, 0))


        # Process thresholds with scope = every
        for th in every_thresholds:
            test_thresholds_total += 1
            if not is_threshold_failed(aggregated_result.get(th["target"]), th["comparison"], th["value"]):
                print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                      f" comply with rule {th['comparison']} {th['value']} [PASSED]")
            else:
                test_thresholds_failed += 1
                threshold = dict(**th)
                threshold['actual_value'] = aggregated_result.get(th["target"])
                threshold['page'] = sub_dir
                failed_thresholds.append(threshold)
                print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                      f" violates rule {th['comparison']} {th['value']} [FAILED]")

        # Process thresholds for current page
        for th in page_thresholds:
            if th["scope"] == f'{sub_dir}':
                test_thresholds_total += 1
                if not is_threshold_failed(aggregated_result.get(th["target"]), th["comparison"], th["value"]):
                    print(
                        f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                        f" comply with rule {th['comparison']} {th['value']} [PASSED]")
                else:
                    test_thresholds_failed += 1
                    threshold = dict(**th)
                    threshold['actual_value'] = aggregated_result.get(th["target"])
                    failed_thresholds.append(threshold)
                    print(
                        f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {aggregated_result.get(th['target'])}"
                        f" violates rule {th['comparison']} {th['value']} [FAILED]")

    update_test_results(TEST_NAME, URL, PROJECT_ID, TOKEN, REPORT_ID, records)

    # Process thresholds with scope = all
    for th in all_thresholds:
        test_thresholds_total += 1
        actual_value = get_aggregated_value(th["aggregation"], all_results.get(th["target"]))
        if not is_threshold_failed(actual_value, th["comparison"], th["value"]):
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {all_results.get(th['target'])}"
                  f" comply with rule {th['comparison']} {th['value']} [PASSED]")
        else:
            test_thresholds_failed += 1
            threshold = dict(actual_value=actual_value, **th)
            failed_thresholds.append(threshold)
            print(f"Threshold: {th['scope']} {th['target']} {th['aggregation']} value {all_results.get(th['target'])}"
                  f" violates rule {th['comparison']} {th['value']} [FAILED]")

    finalize_report(URL, PROJECT_ID, TOKEN, REPORT_ID, test_thresholds_total, test_thresholds_failed, all_results)

    # Email notification
    try:
        integrations = loads(os.environ.get("integrations"))
    except:
        integrations = None

    if integrations and integrations.get("reporters") and "reporter_email" in integrations["reporters"].keys():
        email_notification_id = integrations["reporters"]["reporter_email"].get("task_id")
        if email_notification_id:
            emails = integrations["reporters"]["reporter_email"].get("recipients", [])
            if emails:
                task_url = f"{URL}/api/v1/tasks/run_task/{PROJECT_ID}/{email_notification_id}"

                event = {
                    "notification_type": "ui",
                    "smtp_host": integrations["reporters"]["reporter_email"]["integration_settings"]["host"],
                    "smtp_port": integrations["reporters"]["reporter_email"]["integration_settings"]["port"],
                    "smtp_user": integrations["reporters"]["reporter_email"]["integration_settings"]["user"],
                    "smtp_sender": integrations["reporters"]["reporter_email"]["integration_settings"]["sender"],
                    "smtp_password": integrations["reporters"]["reporter_email"]["integration_settings"]["passwd"],
                    "user_list": emails,
                    "test_id": sys.argv[1],
                    "report_id": REPORT_ID
                }
                if integrations.get("processing") and "quality_gate" in integrations["processing"].keys():
                    quality_gate_config = integrations['processing']['quality_gate']
                else:
                    quality_gate_config = {}
                if quality_gate_config.get('check_performance_degradation') and \
                        quality_gate_config['check_performance_degradation'] != -1:
                    event["performance_degradation_rate"] = quality_gate_config['performance_degradation_rate']
                if quality_gate_config.get('check_missed_thresholds') and \
                        quality_gate_config['check_missed_thresholds'] != -1:
                    event["missed_thresholds"] = quality_gate_config['missed_thresholds_rate']

                res = requests.post(task_url, json=event, headers={'Authorization': f'bearer {TOKEN}',
                                                                   'Content-type': 'application/json'})
                print(res)


    engagement_reporter = None
    if integrations and integrations.get("reporters") and "reporter_engagement" in integrations['reporters'].keys():
        if URL and TOKEN and PROJECT_ID and failed_thresholds:
            payload = integrations['reporters']['reporter_engagement']
            args = {
                'thresholds_failed': test_thresholds_failed,
                'thresholds_total': test_thresholds_total,
                'test_name': TEST_NAME,
                'env': ENV,
                'report_id': REPORT_ID,
            }
            reporter_url = URL + payload['report_url'] + '/' + PROJECT_ID
            query_url = URL + payload['query_url'] + '/' + PROJECT_ID
            reporter = EngagementReporter(
                reporter_url, query_url,
                TOKEN, payload['id'],
                args
            )
            reporter.report_findings(failed_thresholds)
        

except Exception:
    print(format_exc())
