from recon.core.module import BaseModule
import dns
import re


class Module(BaseModule):

    meta = {
        'name': 'Reverse Resolver',
        'author': 'Mor Davidovich @Dec0ne',
        'version': '1.0',
        'description': 'Searches for possible subnets (C classes) and conducts a reverse lookup for each IP address in the subnet to resolve the hostname. Updates the \'hosts\' table with the results.',
        'query': 'SELECT DISTINCT ip_address FROM hosts WHERE ip_address IS NOT NULL',
        'options': (
            ('min_subnet_hosts', 3, True, 'Minimum hosts in a C class subnet to include in search'),
            ('restrict', True, True, 'restrict added hosts to current domains'),
        ),
    }
    subnets = {}

    def module_run(self, addresses):
        domains = [x[0] for x in self.query('SELECT DISTINCT domain from domains WHERE domain IS NOT NULL')]
        domains_str = '|'.join([r'\.' + re.escape(x) + '$' for x in domains])
        regex = "(?:{})".format(domains_str)
        max_attempts = 3
        DnsResolver = dns.resolver.Resolver()
        DnsResolver.nameserver = ['8.8.8.8', '8.8.4.4']
        for address in addresses:
            c_class = '.'.join(address.split('.')[0:3])
            if c_class in self.subnets.keys():
                self.subnets[c_class] += 1
            else:
                self.subnets[c_class] = 1
        for c_class in self.subnets.keys():
            if self.subnets[c_class] >= int(self.options['min_subnet_hosts']):
                self.heading("{}.0/24".format(c_class), level=0)
                for address in ["{}.{}".format(c_class, str(i)) for i in range(1,256)]:
                    attempt = 0
                    while attempt < max_attempts:
                        try:
                            addr = dns.reversename.from_address(address)
                            hosts = DnsResolver.query(addr, 'PTR')
                        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                            self.verbose("{} => No record found.".format(address))
                        except dns.resolver.Timeout:
                            self.verbose("{} => Request timed out.".format(address))
                            attempt += 1
                            continue
                        except dns.resolver.NoNameservers:
                            self.verbose("{} => Invalid nameserver.".format(address))
                            self.error('Invalid nameserver.')
                            return
                        else:
                            for host in hosts:
                                host = str(host)[:-1]
                                if host[:4] == 'xn--':
                                    host = host.encode().decode("idna")
                                if not self.options['restrict'] or re.search(regex, host):
                                    self.insert_hosts(host, address)
                        attempt = max_attempts
