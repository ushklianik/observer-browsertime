import math
import requests
from traceback import format_exc
import os
from json import loads
import sys
from datetime import datetime
import pytz
import re
import shutil

QUALITY_GATE = int(os.environ.get("QUALITY_GATE", 20))


def is_threshold_failed(actual, comparison, expected):
    if comparison == 'gte':
        return actual >= expected
    elif comparison == 'lte':
        return actual <= expected
    elif comparison == 'gt':
        return actual > expected
    elif comparison == 'lt':
        return actual < expected
    elif comparison == 'eq':
        return actual == expected
    return False


def get_aggregated_value(aggregation, metrics):
    if aggregation == 'max':
        return max(metrics)
    elif aggregation == 'min':
        return min(metrics)
    elif aggregation == 'avg':
        return int(sum(metrics) / len(metrics))
    elif aggregation == 'pct95':
        return percentile(metrics, 95)
    elif aggregation == 'pct50':
        return percentile(metrics, 50)
    else:
        raise Exception(f"No such aggregation {aggregation}")


def percentile(data, percentile):
    size = len(data)
    return sorted(data)[int(math.ceil((size * percentile) / 100)) - 1]


def process_page_results(page_name, path, galloper_url, project_id, token, timestamp, prefix, loops):
    print(f"processing: {path}")
    report_bucket = f"{galloper_url}/api/v1/artifacts/artifact/{project_id}/reports"
    static_bucket = f"{galloper_url}/api/v1/artifacts/artifact/{project_id}/sitespeedstatic"
    # index.html
    with open(f"{path}index.html", "r", encoding='utf-8') as f:
        index_html = f.read()
    index_html = update_page_results_html(index_html, report_bucket, static_bucket, page_name, timestamp, loops, prefix)
    with open(f"/{page_name}_{timestamp}_index.html", 'w') as f:
        f.write(index_html)
    upload_file(f"{page_name}_{timestamp}_index.html", "/", galloper_url, project_id, token)
    # metrics.html
    with open(f"{path}metrics.html", "r", encoding='utf-8') as f:
        metrics_html = f.read()
    metrics_html = update_page_results_html(metrics_html, report_bucket, static_bucket, page_name, timestamp, loops,
                                            prefix)
    with open(f"/{page_name}_{timestamp}_metrics.html", 'w') as f:
        f.write(metrics_html)
    upload_file(f"{page_name}_{timestamp}_metrics.html", "/", galloper_url, project_id, token)

    # results.html
    for i in range(1, loops + 1):
        with open(f"{path}{i}.html", "r", encoding='utf-8') as f:
            results_html = f.read()
        results_html = update_page_results_html(results_html, report_bucket, static_bucket, page_name, timestamp, loops,
                                                prefix)
        with open(f"/{page_name}_{timestamp}_{i}.html", 'w') as f:
            f.write(results_html)
        upload_file(f"{page_name}_{timestamp}_{i}.html", "/", galloper_url, project_id, token)

    upload_page_results_data(path, page_name, timestamp, galloper_url, project_id, token, loops)

    page_results = get_page_results(path)
    return page_results


def get_page_results(path):
    json_file = f"{path}data/browsertime.pageSummary.json"
    with open(json_file, "r") as f:
        page = loads(f.read())
    page_result = {"timestamps": [each for each in page["timestamps"]],
                   "load_time": [each for each in page["fullyLoaded"]],
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
    return page_result


def get_record(page_name, page_results, timestamp, loop):
    if loop == -1:
        page_result = page_results
    else:
        page_result = {"time_to_interactive": 0}
        for metric in list(page_results.keys()):
            page_result[metric] = page_results[metric][loop]
    data = {
        "name": page_name,
        "type": "page",
        "loop": loop + 1,
        "identifier": page_name,
        "metrics": page_result,
        "bucket_name": "reports",
        "file_name": f"{page_name}_{timestamp}_index.html",
        "resolution": "auto",
        "browser_version": "chrome",
        "thresholds_total": 0,  # add thresholds
        "thresholds_failed": 0,
        "locators": [],
        "session_id": "session_id"
    }
    return data


def finalize_report(galloper_url, project_id, token, report_id, test_thresholds_total, test_thresholds_failed,
                    all_results):
    time = datetime.now(tz=pytz.timezone("UTC"))
    status = {"status": "Finished", "percentage": 100, "description": "Test is finished"}
    exception_message = ""
    if test_thresholds_total:
        violated = round(float(test_thresholds_failed / test_thresholds_total) * 100, 2)
        print(f"Failed thresholds: {violated}")
        if violated > QUALITY_GATE:
            exception_message = f"Failed thresholds rate more then {violated}%"
            status = {"status": "Failed", "percentage": 100, "description": f"Missed more then {violated}% thresholds"}
        else:
            status = {"status": "Success", "percentage": 100, "description": f"Successfully met more than "
                                                                             f"{100 - violated}% of thresholds"}
    report_data = {
        "report_id": report_id,
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "status": status,
        "results": all_results,
        "thresholds_total": test_thresholds_total,
        "thresholds_failed": test_thresholds_failed,
        "exception": exception_message
    }
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-type': 'application/json'
    }
    try:
        requests.put(f"{galloper_url}/api/v1/ui_performance/reports/{project_id}", json=report_data,
                     headers=headers)
    except Exception:
        print(format_exc())



def upload_file(file_name, file_path, galloper_url, project_id, token, bucket="reports"):
    file = {'file': open(f"{file_path}{file_name}", 'rb')}
    try:
        requests.post(f"{galloper_url}/api/v1/artifacts/artifacts/{project_id}/{bucket}",
                      files=file, allow_redirects=True, headers={'Authorization': f"Bearer {token}"})
    except Exception:
        print(format_exc())


def upload_page_results_data(path, page_name, timestamp, galloper_url, project_id, token, loops):
    for i in range(1, loops + 1):
        filmstrip_files = os.listdir(f"{path}data/filmstrip/{i}/")
        for each in filmstrip_files:
            os.rename(f"{path}data/filmstrip/{i}/{each}", f"{path}data/filmstrip/{i}/{page_name}_{timestamp}_{each}")
            upload_file(f"{page_name}_{timestamp}_{each}", f"{path}data/filmstrip/{i}/", galloper_url, project_id,
                        token)
        screenshot_files = os.listdir(f"{path}data/screenshots/{i}/")
        for each in screenshot_files:
            os.rename(f"{path}data/screenshots/{i}/{each}",
                      f"{path}data/screenshots/{i}/{page_name}_{timestamp}_{each}")
            upload_file(f"{page_name}_{timestamp}_{each}", f"{path}data/screenshots/{i}/", galloper_url, project_id,
                        token)

        os.rename(f"{path}data/video/{i}.mp4", f"{path}data/video/{page_name}_{timestamp}_{i}.mp4")
        upload_file(f"{page_name}_{timestamp}_{i}.mp4", f"{path}data/video/", galloper_url, project_id, token)


def upload_static_files(path, galloper_url, project_id, token):
    static_bucket = "sitespeedstatic"
    for each in ["css", "img", "img/ico", "js", "font"]:
        files = [f for f in os.listdir(f"{path}{each}/") if os.path.isfile(f"{path}{each}/{f}")]
        for file in files:
            upload_file(file, f"{path}{each}/", galloper_url, project_id, token, bucket=static_bucket)


def upload_distributed_report_files(path, timestamp, galloper_url, project_id, token, loops):
    report_bucket = f"{galloper_url}/api/v1/artifacts/artifact/{project_id}/reports"
    static_bucket = f"{galloper_url}/api/v1/artifacts/artifact/{project_id}/sitespeedstatic"
    for each in ["index.html", "detailed.html", "pages.html", "domains.html", "toplist.html", "assets.html",
                 "settings.html", "help.html"]:
        with open(f"{path}{each}", "r", encoding='utf-8') as f:
            html = f.read()
        html = update_page_results_html(html, report_bucket, static_bucket, "", timestamp, loops, "")
        with open(f"/{timestamp}_{each}", 'w') as f:
            f.write(html)
        upload_file(f"{timestamp}_{each}", "/", galloper_url, project_id, token)


def aggregate_results(page_result):
    aggregated_result = {"time_to_interactive": 0}  # there is no TTI in browsertime json
    for metric in list(page_result.keys()):
        if metric == "timestamps":
            aggregated_result[metric] = "0"
        else:
            aggregated_result[metric] = get_aggregated_value(sys.argv[4], page_result[metric])
    return aggregated_result


def update_page_results_html(html, report_bucket, static_bucket, page_name, timestamp, loops, prefix):
    html = html.replace(f'<li><a href="{prefix}assets.html">Assets</a></li>',
                        f'<li><a href="{report_bucket}/{timestamp}_assets.html">Assets</a></li> <li><a href="{timestamp}_distributed_report.zip">Report</a></li>')
    html = html.replace(f'href="{prefix}css/index.min.css"', f'href="{static_bucket}/index.min.css"')
    html = html.replace(f'href="{prefix}img/ico/sitespeed.io-144.png"', f'href="{static_bucket}/sitespeed.io-144.png"')
    html = html.replace(f'href="{prefix}img/ico/sitespeed.io-114.png"', f'href="{static_bucket}/sitespeed.io-114.png"')
    html = html.replace(f'href="{prefix}img/ico/sitespeed.io-72.png"', f'href="{static_bucket}/sitespeed.io-72.png"')
    html = html.replace(f'href="{prefix}img/ico/sitespeed.io.ico"', f'href="{static_bucket}/sitespeed.io.ico"')
    html = html.replace(f'src="{prefix}img/sitespeed.io-logo.png"', f'src="{static_bucket}/sitespeed.io-logo.png"')
    html = html.replace(f'src="{prefix}img/coach.png"', f'src="{static_bucket}/coach.png"')
    html = html.replace(f'src="{prefix}js/perf-cascade.min.js"', f'src="{static_bucket}/perf-cascade.min.js"')
    html = html.replace(f'src="{prefix}js/sortable.min.js"', f'src="{static_bucket}/sortable.min.js"')
    html = html.replace(f'src="{prefix}js/chartist.min.js"', f'src="{static_bucket}/chartist.min.js"')
    html = html.replace(f'src="{prefix}js/chartist-plugin-axistitle.min.js"',
                        f'src="{static_bucket}/chartist-plugin-axistitle.min.js"')
    html = html.replace(f'src="{prefix}js/chartist-plugin-tooltip.min.js"',
                        f'src="{static_bucket}/chartist-plugin-tooltip.min.js"')
    html = html.replace(f'src="{prefix}js/chartist-plugin-legend.min.js"',
                        f'src="{static_bucket}/chartist-plugin-legend.min.js"')
    html = html.replace(f'src="{prefix}js/video.core.novtt.min.js"', f'src="{static_bucket}/video.core.novtt.min.js"')
    html = html.replace(f'href="{prefix}help.html', f'href="{report_bucket}/{timestamp}_help.html')

    for html_file in ["index.html", "detailed.html", "pages.html", "domains.html", "toplist.html", "settings.html"]:
        html = html.replace(f'href="{prefix}{html_file}"', f'href="{report_bucket}/{timestamp}_{html_file}"')
    for i in range(1, loops + 1):
        html = html.replace(f'href="./{i}.html"', f'href="{report_bucket}/{page_name}_{timestamp}_{i}.html"')
        for data_file_path in [f"data/screenshots/{i}/", "data/video/", f"data/filmstrip/{i}/"]:
            html = html.replace(data_file_path, f'{report_bucket}/{page_name}_{timestamp}_')
    html = html.replace('href="metrics.html"', f'href="{report_bucket}/{page_name}_{timestamp}_metrics.html"')

    # Links for pages
    links = re.findall('href="pages/(.+?)/index.html"', html)
    for each in links:
        try:
            link = f'href="pages/{each}/index.html"'
            page_name = link.split("/")[-2]
            html = html.replace(f'href="pages/{each}/index.html"',
                                f'href="{report_bucket}/{page_name}_{timestamp}_index.html"')
        except:
            print(f"failed to update {each} link")
    return html


def upload_distributed_report(timestamp, galloper_url, project_id, token):
    shutil.make_archive(base_name=f'{timestamp}_distributed_report', format="zip", root_dir="/",
                        base_dir="/sitespeed.io/sitespeed-result")
    upload_file(f'{timestamp}_distributed_report.zip', "/sitespeed.io/", galloper_url, project_id, token)


def update_test_results(test_name, galloper_url, project_id, token, report_id, records):
    bucket = test_name.replace("_", "").lower()
    header = "timestamp,name,identifier,type,loop,load_time,dom,tti,fcp,lcp,cls,tbt,fvc,lvc,file_name\n".encode('utf-8')
    with open(f"/tmp/{report_id}.csv", 'wb') as f:
        f.write(header)
        for each in records:
            f.write(
                f"{each['metrics']['timestamps']},{each['name']},{each['identifier']},{each['type']},{each['loop']},"
                f"{each['metrics']['load_time']},{each['metrics']['dom_processing']},"
                f"{each['metrics']['time_to_interactive']},{each['metrics']['first_contentful_paint']},"
                f"{each['metrics']['largest_contentful_paint']},"
                f"{each['metrics']['cumulative_layout_shift']},{each['metrics']['total_blocking_time']},"
                f"{each['metrics']['first_visual_change']},{each['metrics']['last_visual_change']},"
                f"{each['file_name']}\n".encode('utf-8'))

    import gzip
    import shutil
    with open(f"/tmp/{report_id}.csv", 'rb') as f_in:
        with gzip.open(f"/tmp/{report_id}.csv.gz", 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    upload_file(f"{report_id}.csv.gz", "/tmp/", galloper_url, project_id, token, bucket=bucket)
