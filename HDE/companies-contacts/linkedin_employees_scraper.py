from recon.core.module import BaseModule
import re
import requests
import json

class Module(BaseModule):

    meta = {
        'name': 'Linkedin Profile and Contact Company Employees Harvester',
        'author': 'Mor Davidovich @Dec0ne',
        'version': '1.0',
        'description': 'Harvests profiles from LinkedIn by scraping for LinkedIn employees search related to the given companies, and adds them to the \'profiles\' table. The module will then parse the resulting information to extract the user\'s full name and job title. The user\'s full name and title are then added to the \'contacts\' table. This module access LinkedIn and needs valid request headers of an active Linkedin user',
        'required_keys': [],
        'comments': (
            'Be sure to set the correct path for the headers file.',
            'The headers file should contains the full headers of an active logged in user'
        ),
        'query': 'SELECT DISTINCT company FROM companies WHERE company IS NOT NULL',
        'options': (
            ('limit', 0, True, 'limit total number of pages per company (0 = unlimited)'),
            ('headers_file', None, True, 'full path to the headers_file'),
        ),
    }

    def module_run(self, companies):
        self.headers_parser()
        for company in companies:
            urn_dict = {}
            company_employees_dict = {}
            self.heading(company, level=0)
            urn_list = self.choose_company(company)
            company_employees_list = []
            if urn_list is not None:
                for urn in urn_list:
                    company_employees_list += self.get_employees_for_urn(urn, company + " [urn: {}]".format(str(urn)))
            self.insert_results(company_employees_list, company)


    def choose_company(self, company):
        companies_search_url = 'https://www.linkedin.com/voyager/api/typeahead/hitsV2'
        companies_search_params = {'keywords': company, 'origin': 'GLOBAL_SEARCH_HEADER', 'q':'blended'}
        results = []
        response = requests.get(companies_search_url, headers=self.headers, params=companies_search_params)
        j = json.loads(response.text)
        for d in j['data']['elements']:
            if d['type'].lower() == 'company':
                results.append(d)
        if len(results) == 0:
            print("[WARNING] Got no matches for company: " + company + ". Skipping this one...\n")
            return None
        elif len(results) == 1:
            print("[INFO] Got only 1 match for company: " + company + ", Continuing...\n")
            return [results[0]['objectUrn'].split(':')[-1]]
        else:
            i = 1
            print("[USER] Which compaines? (select the corresponding numbers separated by a space):")
            for d in results:
                print("[USER] " + str(i) + ') ' + d['text']['text'])
                i += 1
            choice = input()
            urn_list = []
            try:
                choices = choice.split()
                if len(choices) > 0:
                    for c in choices:
                        try:
                           urn_list.append(results[int(c)-1]['objectUrn'].split(':')[-1])
                        except:
                            print('Choice ' + str(c) + ' unrecognized, Skipping this one...\n')
                else:
                    print('[WARNING] Choice unrecognized, Skipping this one...\n')
                return urn_list
            except:
                print('[WARNING] Choice unrecognized, Skipping this one...\n')
                return None

    def get_employees_for_urn(self, urn, company):
        employees_search_url = 'https://www.linkedin.com/voyager/api/search/blended'
        employees_search_url_extension = '?count=10&filters=List(currentCompany-%3E[[COMPANY]],resultType-%3EPEOPLE)&origin=OTHER&q=all&queryContext=List(spellCorrectionEnabled-%3Etrue,relatedSearchesEnabled-%3Etrue)&start=[[START]]'
        results = []
        max_results = int(self.options['limit'])
        start_index = 0
        total_results = None
        while int(start_index / 10) < max_results:
            page_results = []
            try:
                current_extension = employees_search_url_extension
                current_extension = current_extension.replace('[[COMPANY]]', str(urn))
                current_extension = current_extension.replace('[[START]]', str(start_index))
                response = requests.get(employees_search_url + current_extension, headers=self.headers)
                j = json.loads(response.text)
                if total_results is None:
                    total_results = int(j['data']['paging']['total'])
                for element in j['data']['elements']:
                    if element.get('type') == 'SEARCH_HITS':
                        for d in element['elements']:
                            if not d['headless'] and d['type'] == 'PROFILE':
                                page_results.append(d)
                    break
                results += page_results
                print("[INFO] got {} contacts from page {} for {}".format(str(len(page_results)), str(int((start_index + 10) / 10)), company))
            except:
                print("[WARNING] page {} failed".format(str(int((start_index + 10) / 10))))
            start_index += 10
            if total_results != None and start_index >= total_results - 10:
                    break
        return results

    def insert_results(self, results, company):
        for d in results:
            name = d['title']['text'].split()
            fname = name[0] if len(name) > 0 else None
            mname = ' '.join(name[1:-1]) if len(name) > 2 else None
            lname = name[-1] if len(name) > 1 else None
            jobtitle = d['headline']['text']
            username = d['publicIdentifier']
            url = d['navigationUrl']
            self.insert_contacts(first_name=fname, middle_name=mname, last_name=lname, title=jobtitle)
            self.insert_profiles(username=username, url=url, resource='LinkedIn', category='social')

    def headers_parser(self):
        file_path = self.options['headers_file']
        f = open(file_path, 'r')
        raw = f.read()
        f.close()
        headers = {}
        for h in raw.split("\n"):
            if h != '':
                headers[h.split(": ")[0]] = h.split(": ")[1]
        self.headers = headers