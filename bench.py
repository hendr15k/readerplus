import time
import re
from aa_proxy import parse_book

html_content = """
<html><body>
<h1>Test Book</h1>
<a href="/search?q=author&param=1">Author Name</a>
<a href="/search?q=publisher">Publisher Name</a>
<a href="/search?q=2023">2023</a>
""" * 100

start = time.time()
for _ in range(1000):
    parse_book(html_content, "md5test")
end = time.time()

print(f"Time taken: {end - start:.4f} seconds")
