from requests import post, get
from json import dumps
from typing import Dict, List
import hashlib


class IssuesConnector(object):
    def __init__(self, report_url, query_url, token):
        self.report_url = report_url
        self.query_url = query_url
        self.token = token
        self.headers = {
            "Content-type": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def create_issue(self, payload):
        issue_hash = payload['issue_id']
        exists = self.search_for_issue(issue_hash)
        if exists:
            print(f"The issue with {payload['title']} title already exists")
            return
        
        if exists is None:
            print(f"Unable to connect to query url")
            return

        result = post(self.report_url, data=dumps(payload), headers=self.headers)
        return result.content
    
    def search_for_issue(self, issue_hash):
        resp = get(self.query_url, params={'source.id': issue_hash, 'status': 'Open'}, headers=self.headers)
        
        print(resp.status_code)
        if not resp.status_code == 200:
            return None
        
        print(resp.json())
        data = resp.json()
        if not data['total'] == 0:
            return True
        return False


class EngagementReporter:
    def __init__(self, report_url, query_url, token, engagement_id, args):
        self.engagement_id = engagement_id
        self.args = args
        self.issues_connector = IssuesConnector(report_url, query_url, token)

    @staticmethod
    def _prepare_issue_payload(title, description, severity, engagement_id, issue_hash=None):
        return {
            'issue_id': issue_hash,
            'title': title,
            'description': description,
            'severity': severity,
            'project': None,
            'asset': None,
            'type': 'Bug',
            'engagement': engagement_id,
            'source': 'ui_performance'
        }

    def report_findings(self, failed_thresholds):
        title = self.get_title()
        hash_code = self.get_hash_code(title)
        description = self.create_description(failed_thresholds)
        payload = self._prepare_issue_payload(
            title, 
            description, 
            "High", 
            self.engagement_id,
            hash_code,
        )
        self.issues_connector.create_issue(payload)
    
    def get_hash_code(self, title):
        return hashlib.sha256(title.strip().encode('utf-8')).hexdigest()

    def create_description(self, thresholds: List[Dict[str, list]]):
        text = "Failed Thresholds:\n\n" 
        text += "---\n"
        for th in thresholds:
            rule = self.__get_rule(th['aggregation'], th['target'], th['comparison'], th['value'])
            for field, value in th.items():
                if 'id' in field or field in ('target', 'aggregation', 'comparison', 'value'):
                    continue
                field = field.capitalize().replace('_', ' ')
                text += f"{field}: {value}\n"
            text += f"Rule: {rule}"
            text += "\n"
        return text
    
    def __get_rule(self, aggregation, target, operator, value) -> str:
        operators_signs = {
            'gte': '>=',
            'lte': '<=',
            'gt': '>',
            'lt': '<',
            'eq': '=='
        }
        return f'{aggregation}({target}) {operators_signs[operator]} {value}'
    
    def get_title(self):
        test_thresholds_failed = self.args['thresholds_failed']
        test_thresholds_total = self.args['thresholds_total']
        test_name = self.args['test_name']
        env = self.args['env']
        violated = round(float(test_thresholds_failed / test_thresholds_total) * 100, 2)
        return f"UI test: {test_name}. {env} environment. Missed more then {violated}% thresholds."

    

    