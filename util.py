import math
import requests
from traceback import format_exc
from os import listdir, rename
from json import loads
import sys
from datetime import datetime
import pytz
import re
import shutil


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
    report_bucket = f"{galloper_url}/api/v1/artifacts/{project_id}/reports"
    static_bucket = f"{galloper_url}/api/v1/artifacts/{project_id}/sitespeedstatic"
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
    metrics_html = update_page_results_html(metrics_html, report_bucket, static_bucket, page_name, timestamp, loops, prefix)
    with open(f"/{page_name}_{timestamp}_metrics.html", 'w') as f:
        f.write(metrics_html)
    upload_file(f"{page_name}_{timestamp}_metrics.html", "/", galloper_url, project_id, token)

    # results.html
    for i in range(1, loops + 1):
        with open(f"{path}{i}.html", "r", encoding='utf-8') as f:
            results_html = f.read()
        results_html = update_page_results_html(results_html, report_bucket, static_bucket, page_name, timestamp, loops, prefix)
        with open(f"/{page_name}_{timestamp}_{i}.html", 'w') as f:
            f.write(results_html)
        upload_file(f"{page_name}_{timestamp}_{i}.html", "/", galloper_url, project_id, token)

    upload_static_files(path, page_name, timestamp, galloper_url, project_id, token, loops)

    page_results = get_page_results(path)
    return page_results


def get_page_results(path):
    json_file = f"{path}data/browsertime.pageSummary.json"
    with open(json_file, "r") as f:
        page = loads(f.read())
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
    return page_result


def update_report(page_name, aggregated_result, galloper_url, project_id, token, report_id, timestamp):
    data = {
        "name": page_name,
        "type": "page",
        "identifier": page_name,
        "metrics": aggregated_result,
        "bucket_name": "reports",
        "file_name": f"{page_name}_{timestamp}_index.html",
        "resolution": "auto",
        "browser_version": "chrome",
        "thresholds_total": 0, # add thresholds
        "thresholds_failed": 0,
        "locators": [],
        "session_id": "session_id"
    }

    try:
        requests.post(f"{galloper_url}/api/v1/observer/{project_id}/{report_id}", json=data,
                      headers={'Authorization': f"Bearer {token}"})
    except Exception:
        print(format_exc())


def finalize_report(galloper_url, project_id, token, report_id):
    time = datetime.now(tz=pytz.timezone("UTC"))
    # exception_message = ""
    # if test_thresholds_total:
    #     violated = round(float(test_thresholds_failed / test_thresholds_total) * 100, 2)
    #     print(f"Failed thresholds: {violated}")
    #     if violated > 30:
    #         exception_message = f"Failed thresholds rate more then {violated}%"
    report_data = {
        "report_id": report_id,
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "status": "Finished",
        "thresholds_total": 0,
        "thresholds_failed": 0,
        "exception": ""
    }

    try:
        requests.put(f"{galloper_url}/api/v1/observer/{project_id}", json=report_data,
                     headers={'Authorization': f"Bearer {token}"})
    except Exception:
        print(format_exc())


def upload_file(file_name, file_path, galloper_url, project_id, token):
    file = {'file': open(f"{file_path}{file_name}", 'rb')}
    try:
        requests.post(f"{galloper_url}/api/v1/artifacts/{project_id}/reports/{file_name}",
                      files=file,
                      headers={'Authorization': f"Bearer {token}"})
    except Exception:
        print(format_exc())


def upload_static_files(path, page_name, timestamp, galloper_url, project_id, token, loops):
    for i in range(1, loops + 1):
        filmstrip_files = listdir(f"{path}data/filmstrip/{i}/")
        for each in filmstrip_files:
            rename(f"{path}data/filmstrip/{i}/{each}", f"{path}data/filmstrip/{i}/{page_name}_{timestamp}_{each}")
            upload_file(f"{page_name}_{timestamp}_{each}", f"{path}data/filmstrip/{i}/", galloper_url, project_id, token)
        screenshot_files = listdir(f"{path}data/screenshots/{i}/")
        for each in screenshot_files:
            rename(f"{path}data/screenshots/{i}/{each}", f"{path}data/screenshots/{i}/{page_name}_{timestamp}_{each}")
            upload_file(f"{page_name}_{timestamp}_{each}", f"{path}data/screenshots/{i}/", galloper_url, project_id, token)

        rename(f"{path}data/video/{i}.mp4", f"{path}data/video/{page_name}_{timestamp}_{i}.mp4")
        upload_file(f"{page_name}_{timestamp}_{i}.mp4", f"{path}data/video/", galloper_url, project_id, token)


def upload_distributed_report_files(path, timestamp, galloper_url, project_id, token, loops):
    report_bucket = f"{galloper_url}/api/v1/artifacts/{project_id}/reports"
    static_bucket = f"{galloper_url}/api/v1/artifacts/{project_id}/sitespeedstatic"
    for each in ["index.html", "detailed.html", "pages.html", "domains.html", "toplist.html", "assets.html", "settings.html", "help.html"]:
        with open(f"{path}{each}", "r", encoding='utf-8') as f:
            html = f.read()
        html = update_page_results_html(html, report_bucket, static_bucket, "", timestamp, loops, "")
        with open(f"/{timestamp}_{each}", 'w') as f:
            f.write(html)
        upload_file(f"{timestamp}_{each}", "/", galloper_url, project_id, token)


def aggregate_results(page_result):
    aggregated_result = {"requests": len(page_result["total"]), "domains": 1,
                         "time_to_interactive": 0}  # there is no TTI in browsertime json
    for metric in list(page_result.keys()):
        aggregated_result[metric] = get_aggregated_value(sys.argv[3], page_result[metric])
    return aggregated_result


def update_page_results_html(html, report_bucket, static_bucket, page_name, timestamp, loops, prefix):
    html = html.replace(f'<li><a href="{prefix}assets.html">Assets</a></li>', f'<li><a href="{report_bucket}/{timestamp}_assets.html">Assets</a></li> <li><a href="{timestamp}_distributed_report.zip">Download distributed report</a></li>')
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
    html = html.replace(f'src="{prefix}js/chartist-plugin-axistitle.min.js"', f'src="{static_bucket}/chartist-plugin-axistitle.min.js"')
    html = html.replace(f'src="{prefix}js/chartist-plugin-tooltip.min.js"', f'src="{static_bucket}/chartist-plugin-tooltip.min.js"')
    html = html.replace(f'src="{prefix}js/chartist-plugin-legend.min.js"', f'src="{static_bucket}/chartist-plugin-legend.min.js"')
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
            html = html.replace(f'href="pages/{each}/index.html"', f'href="{report_bucket}/{page_name}_{timestamp}_index.html"')
        except:
            print(f"failed to update {each} link")
    return html


def upload_distributed_report(timestamp, galloper_url, project_id, token):
    shutil.make_archive(base_name=f'{timestamp}_distributed_report', format="zip", root_dir="/", base_dir="/sitespeed.io/sitespeed-result")
    upload_file(f'{timestamp}_distributed_report.zip', "/sitespeed.io/", galloper_url, project_id, token)
