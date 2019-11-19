from recon.core.module import BaseModule
from bs4 import BeautifulSoup as bs
import re
import requests
import json
from random import randint
from urllib.parse import quote
import concurrent.futures

class Module(BaseModule):

	meta = {
		'name': 'Startpage Domain Email Harvester',
		'author': 'Mor Davidovich @Dec0ne',
		'version': '1.0',
		'description': 'Scrape Startpage for links using the google-dorks: intext:"<domain>" then continue with scraping the links and extract every email it finds with the same domain.',
		'required_keys': [],
		'query': 'SELECT DISTINCT domain FROM domains WHERE domain IS NOT NULL',
		'options': (
			('limit', 50, True, 'limit total number of startpage-links per domains (0 = unlimited)'),
		),
	}
	email_regex = r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"
	user_agents = [
		'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:44.0) Gecko/20100101 Firefox/44.01',
		'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/'
		'54.0.2840.71 Safari/537.36',
		'Mozilla/5.0 (Linux; Ubuntu 14.04) AppleWebKit/537.36 Chromium/35.0.1870.2 Safa'
		'ri/537.36',
		'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.'
		'0.2228.0 Safari/537.36',
		'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko'
		') Chrome/42.0.2311.135 '
		'Safari/537.36 Edge/12.246',
		'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, '
		'like Gecko) Version/9.0.2 Safari/601.3.9',
		'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
		'Chrome/47.0.2526.111 Safari/537.36',
		'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:54.0) Gecko/20100101 Firefox/54.0',
	]

	def module_run(self, domains):
		for domain in domains:
			self.heading(domain, level=0)
			links = self.get_links(domain)
			email_list = self.scrape_links(links, domain)
			self.insert_results(email_list, domain)

	def get_links(self, domain):
		start_index = 0
		results = []
		max_results = int(self.options['limit'])
		query = "intext:'@{}'".format(domain)
		base_url = 'https://www.startpage.com/do/search'
		data = {
			'query': query,
			'cat': 'web',
			'cmd': 'process_search',
			'language': 'english',
			'engine0': 'v1all',
			'abp': 1,
			'pg': 0
			}
		cookies = {
			'preferences': 'num_of_resultsEEE20'
			}
		while len(results) < max_results:
			page_results = []
			try:
				data['pg'] = start_index
				response = requests.post(base_url, data=data, cookies=cookies, timeout=6, headers={'User-Agent': self.user_agents[randint(0, len(self.user_agents))]})
				soup = bs(response.content,"lxml")
				result_list = soup.select('li.search-result')
				if len(result_list) == 0:
					result_list = soup.select('div.w-gl__result')
				for res in result_list:
					page_results.append(res.a['href'])
				results += page_results
				print("[INFO] got {} links from page {}".format(str(len(page_results)), str(int((start_index + 10) / 10))))
			except Exception as e:
				print(e)
				print("[WARNING] page {} failed".format(str(int((start_index + 10) / 10))))
			start_index += 10
			if len(page_results) == 0:
					print("[INFO] no more pages...")
					break
		return results

	def scrape_links(self, links, domain):
		results = []
		i = 1
		with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
			links_futures = {executor.submit(self.scrape_single_link, url): url for url in links}
			for future in concurrent.futures.as_completed(links_futures):
				try:
					t = future.result()
					page_results = re.findall(self.email_regex, t)
					temp = []
					for email in page_results:
						if domain.lower() in email.lower() :
							temp.append(email.lower())
					page_results = list(set(temp))
					results += page_results
					print("[INFO] got {} emails from link[{}]: {}".format(str(len(page_results)), str(i), links_futures[future]))
				except:
					print("[WARNING] could not scrape link[{}]: {}, skipping this one...".format(str(i), links_futures[future]))
				i += 1
		results = list(set(results))
		return results

	def scrape_single_link(self, url):
		response = requests.get(url, headers={'User-Agent': self.user_agents[randint(0, len(self.user_agents))]})
		if response.status_code == 200:
			return response.text
		raise Exception("Scraping Error")


	def insert_results(self, results, domain):
		for email in results:
			self.insert_contacts(email=email)
