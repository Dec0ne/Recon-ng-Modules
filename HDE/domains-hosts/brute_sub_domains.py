from recon.core.module import BaseModule
import dns
import os
import concurrent.futures


class Module(BaseModule):

    meta = {
        'name': 'DNS Sub-Domain Brute Forcer',
        'author': 'Mor Davidovich @Dec0ne',
        'version': '1.0',
        'description': 'Brute forces sub-domains using DNS. Updates the \'hosts\' table with the results.',
        'query': 'SELECT DISTINCT domain FROM domains WHERE domain IS NOT NULL',
        'options': (
            ('concurrency', 1, True, 'Amount of concurrent threads to run'),
            ('sub-domains', os.path.join(BaseModule.data_path, 'hostnames.txt'), True, 'path to sub-domains wordlist'),
        ),
        'files': ['hostnames.txt'],
    }
    max_attempts = 3
    DnsResolver = None


    def module_run(self, domains):
        if self.options['concurrency'] not in [None, '', 'None']:
            concurrency = int(self.options['concurrency'])
        else:
            concurrency = 1
        self.DnsResolver = dns.resolver.Resolver()
        self.DnsResolver.nameserver = ['8.8.8.8', '8.8.4.4']
        with open(self.options['sub-domains']) as fp:
            sub_domains = [line.strip().lower() for line in fp if len(line)>0 and line[0] is not '#']
        for domain in domains:
            self.heading(domain, level=0)
            domain_root = domain
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                sub_domains_futures = {executor.submit(self.check_sub_domain, "{}.{}".format(sub_domain, domain_root)): sub_domain for sub_domain in sub_domains}
                for future in concurrent.futures.as_completed(sub_domains_futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(e)
            for sub_domain in sub_domains:
                domain = "{}.{}".format(sub_domain, domain_root)


    def check_sub_domain(self, domain):
        attempt = 0
        while attempt < self.max_attempts:
            ip = None
            try:
                ip = self.DnsResolver.query(domain, 'A')[0].to_text()
            except dns.resolver.Timeout:
                self.verbose("{} => Request timed out.".format(domain))
                attempt += 1
                continue
            except:
                pass
            else:
                if ip is not None:
                    self.alert("{} => {}".format(domain, ip))
                    self.insert_hosts(domain, ip)
            attempt = self.max_attempts
