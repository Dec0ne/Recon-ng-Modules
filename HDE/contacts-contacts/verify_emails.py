from recon.core.module import BaseModule
import smtplib
from dns import resolver
import requests
import concurrent.futures


class Module(BaseModule):

    meta = {
        'name': 'SMTP Email Validator (MailTester as fallback)',
        'author': 'Mor Davidovich @Dec0ne',
        'version': '1.0',
        'description': 'Try to validate email address from the domain smtp server. As a fallback - leverages MailTester.com to validate email addresses.',
        'query': 'SELECT DISTINCT email FROM contacts WHERE email IS NOT NULL',
        'options': (
            ('method', 0, True, 'Method to validate emails < 0=SMTP(MailTester.com as fall back) | 1=SMTP | 2=MailTester.com >'),
            ('concurrency', 1, True, 'Amount of concurrent threads to run'),
            ('proxy', None, False, 'Proxy for MailTester.com'),
            ('remove', False, True, 'Remove invalid email addresses'),
        ),
    }
    smtp_servers_dict = {}
    blocked_mailtester_domains = []
    headers = {'Host': 'mailtester.com', 'Connection': 'keep-alive', 'Content-Length': '39', 'Cache-Control': 'max-age=0', 'Origin': 'https://mailtester.com', 'Upgrade-Insecure-Requests': '1', 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-User': '?1', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3', 'Sec-Fetch-Site': 'same-origin', 'Referer': 'https://mailtester.com/index.php', 'Accept-Encoding': 'gzip, deflate, br', 'Accept-Language': 'en-US,en;q=0.9'}
    mailtester_answers = {
        "E-mail address does not exist on this server": False,
        "Server doesn't allow e-mail address verification": None,
        "E-mail address is valid": True,
        "The domain is invalid or no mail server was found for it": 0,
    }
    mailtester_error = 'Too many requests from the same IP address.'
    mailtester_error_flag = False
    proxies = None

    def module_run(self, emails):
        self.mailtester_error_flag = False
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        method = int(self.options['method'])
        if self.options['proxy'] not in [None, '', 'None']:
            self.proxies = {'http': self.options['proxy'], 'https': self.options['proxy']}
        else:
            self.proxies = None
        if self.options['concurrency'] not in [None, '', 'None']:
            concurrency = int(self.options['concurrency'])
        else:
            concurrency = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            mailtester_futures = {executor.submit(self.verify_email, method, email): email for email in emails}
            for future in concurrent.futures.as_completed(mailtester_futures):
                try:
                    exist = future.result()
                except Exception:
                    exist = None
                email = mailtester_futures[future]
                if self.mailtester_error_flag:
                    break
                if exist is True:
                    self.alert("{} => email exist".format(email))
                elif exist is False:
                    self.output("{} => email doesn't exist".format(email))
                    if self.options['remove']:
                        self.query('UPDATE contacts SET email=NULL where email=?', (email,))
                        self.error("{} removed.".format(email))
                elif exist is None or exist is 0:
                    self.verbose("{} => Could not verify email".format(email))

    def verify_email(self, method, email):
        exist = None
        if method in [0, 1]:
            smtp_server = self.get_smtp_server(email)
            if smtp_server is not None:
                try:
                    with smtplib.SMTP(smtp_server) as smtp:
                        smtp.helo()
                        smtp.mail('user@{}'.format(self.get_domain_form_email(email)))
                        resp = smtp.rcpt(email)
                        if resp[0] == 250:
                            exist = True
                        elif resp[0] == 550:
                            exist = False
                        else:
                            self.block_smtp_server(email)
                            #print("[WARNING]  from SMTP query for email[{}]".format(email))
                except:
                    self.block_smtp_server(email)
                    #print("[ERROR] Could not authenticate with SMTP server for email[{}]".format(email))
        if method in [0, 2] and exist is None and self.get_domain_form_email(email) not in self.blocked_mailtester_domains and not self.mailtester_error_flag:
            max_attempts = 2
            attempt = 0
            while attempt < max_attempts:
                try:
                    res = requests.post("https://mailtester.com/index.php", proxies=self.proxies, headers=self.headers, data={'lang': 'en', 'email': email}, verify=False, timeout=10)
                    attempt = max_attempts
                    if self.mailtester_error in res.text:
                        if not self.mailtester_error_flag:
                            self.error(self.mailtester_error)
                            self.mailtester_error_flag = True
                        break
                    for answer in self.mailtester_answers.keys():
                        if answer in res.text:
                            exist = self.mailtester_answers[answer]
                            if exist is 0:
                                print("[ERROR] MailTester.com could not find the SMTP server for email[{}]".format(email))
                                self.block_mailtester_domain(email)
                except Exception:
                    attempt += 1
        return exist

    def get_smtp_server(self, email_address):
        domain = email_address.split("@")[-1]
        if domain.lower() not in self.smtp_servers_dict.keys():
            try:
                mx_record = resolver.query(domain, 'MX')
                exchanges = [tuple(exchange.to_text().split()) for exchange in mx_record]
                lowest_priority = min(exchanges, key=lambda t: t[0])
            except (resolver.NoAnswer, resolver.NXDOMAIN, resolver.NoNameservers):
                lowest_priority = (0, None)
            self.smtp_servers_dict[domain.lower()] = lowest_priority[1]
        return self.smtp_servers_dict[domain.lower()]

    def get_domain_form_email(self, email):
        return email.split("@")[-1]

    def block_smtp_server(self, email):
        domain = self.get_domain_form_email(email)
        if self.smtp_servers_dict[domain.lower()] is not None:
            self.smtp_servers_dict[domain.lower()] = None
            print("[ERROR] Could not authenticate with SMTP server / Got unexpected response for email[{}]".format(email))
            print("[WARNING] Blacklisting SMTP Server for domain[{}]...".format(domain.lower()))

    def block_mailtester_domain(self, email):
        domain = self.get_domain_form_email(email)
        if domain.lower() not in self.blocked_mailtester_domains:
            self.blocked_mailtester_domains.append(domain.lower())
            print("[WARNING] Blacklisting domain[{}] for MailTester.com...".format(domain.lower()))
