import timeit
import re
import random

# We'll just copy the regex logic and test it directly to avoid importing the module
# and dealing with dependency hell.

server_pat_str = r'href="(https?://(?!annas-archive\.gl)[^"]+)"[^>]*class="[^"]*(?:archive-download-pill|archive-download-primary|archive-download-inline)[^"]*"'

html_text = """
<a href="https://example.com/download" class="archive-download-pill">Download</a>
<a href="https://annas-archive.gl/download" class="archive-download-pill">Download</a>
<a href="https://other.com/download" class="archive-download-primary">Download</a>
<a href="https://annas-archive.gl/download2" class="archive-download-primary">Download</a>
<a href="http://unsecure.com/download" class="archive-download-inline">Download</a>
""" * 1000

def original_function():
    server_pat = re.compile(
        server_pat_str,
        re.IGNORECASE)
    servers = []
    for sm in server_pat.finditer(html_text):
        url = sm.group(1)
        host = re.search(r'https?://([^/]+)', url).group(1)
        if not any(s['host'] == host for s in servers):
            servers.append({'host': host, 'url': url, 'requires_login': True})
    return servers[:10]

server_pat_global = re.compile(
    server_pat_str,
    re.IGNORECASE)

def optimized_function():
    servers = []
    for sm in server_pat_global.finditer(html_text):
        url = sm.group(1)
        host = re.search(r'https?://([^/]+)', url).group(1)
        if not any(s['host'] == host for s in servers):
            servers.append({'host': host, 'url': url, 'requires_login': True})
    return servers[:10]

if __name__ == "__main__":
    t1 = timeit.timeit("original_function()", setup="from __main__ import original_function", number=100)
    t2 = timeit.timeit("optimized_function()", setup="from __main__ import optimized_function", number=100)
    print(f"Original Time: {t1:.4f} seconds")
    print(f"Optimized Time: {t2:.4f} seconds")
    print(f"Improvement: {(t1-t2)/t1*100:.2f}%")
