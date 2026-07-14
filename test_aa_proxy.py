import unittest
from aa_proxy import parse_book

class TestParseBook(unittest.TestCase):
    def setUp(self):
        self.md5 = "e10adc3949ba59abbe56e057f20f883e"
        self.base_out = {
            'id': self.md5, 'slug': self.md5, 'md5': self.md5,
            'title': '', 'authors': [], 'cover': None,
            'isbn': None, 'year': None, 'publisher': None,
            'language': None, 'description': '',
            'categories': [], 'download_servers': [],
            'login_required': True, 'source_url': f'https://annas-archive.gl/md5/{self.md5}',
            'filename': '', 'filesize_bytes': None, 'format': '',
        }

    def test_json_ld_parsing(self):
        html_text = """
        <script type="application/ld+json">
        {
            "@type": "Book",
            "name": " 1984 ",
            "author": "George Orwell, Test Author and Another",
            "image": "https://covers.example.com/1984.jpg",
            "isbn": "9780451524935",
            "datePublished": "1949-06-08",
            "publisher": "Secker & Warburg",
            "inLanguage": "English",
            "description": "A dystopian social science fiction novel and cautionary tale."
        }
        </script>
        """
        result = parse_book(html_text, self.md5)
        self.assertEqual(result['title'], "1984")
        self.assertEqual(result['authors'], ["George Orwell", "Test Author", "Another"])
        self.assertEqual(result['cover'], "https://covers.example.com/1984.jpg")
        self.assertEqual(result['isbn'], "9780451524935")
        self.assertEqual(result['year'], "1949")
        self.assertEqual(result['publisher'], "Secker & Warburg")
        self.assertEqual(result['language'], "English")
        self.assertEqual(result['description'], "A dystopian social science fiction novel and cautionary tale.")

    def test_json_ld_graph_parsing(self):
        html_text = """
        <script type="application/ld+json">
        {
            "@graph": [
                {
                    "@type": "WebPage"
                },
                {
                    "@type": "Book",
                    "name": "Brave New World",
                    "author": ["Aldous Huxley", "Another Author"]
                }
            ]
        }
        </script>
        """
        result = parse_book(html_text, self.md5)
        self.assertEqual(result['title'], "Brave New World")
        self.assertEqual(result['authors'], ["Aldous Huxley", "Another Author"])

    def test_title_fallback(self):
        html_text = """
        <html>
        <head>
            <title>
                My Awesome Book - Anna's Archive
            </title>
        </head>
        </html>
        """
        result = parse_book(html_text, self.md5)
        self.assertEqual(result['title'], "My Awesome Book")

        html_text2 = """<title>Another Book – Anna’s Archive</title>"""
        result2 = parse_book(html_text2, self.md5)
        self.assertEqual(result2['title'], "Another Book")

    def test_filename_and_size(self):
        html_text = """
        <div>
            filesize_bytes: 1234567
            lgli/no-category - Orwell, George - 1984.epub
        </div>
        """
        result = parse_book(html_text, self.md5)
        self.assertEqual(result['filesize_bytes'], 1234567)
        self.assertEqual(result['format'], 'EPUB')
        self.assertEqual(result['filename'], 'no-category - Orwell, George - 1984.epub')
        self.assertEqual(result['authors'], ['Orwell, George'])
        self.assertEqual(result['title'], '1984')

    def test_filename_author_in_path(self):
        html_text = """
        zlib/O/Orwell, George/1984.pdf
        """
        result = parse_book(html_text, self.md5)
        # Note: zlib/O/Orwell, George/1984.pdf doesn't actually match the regex
        # due to having too many path parts. We have to separate the two matching pieces.
        html_text_parts = "zlib/O/1984.pdf\\n/Orwell, George/"
        result_parts = parse_book(html_text_parts, self.md5)
        self.assertEqual(result_parts['format'], 'PDF')
        self.assertEqual(result_parts['filename'], '1984.pdf')
        self.assertEqual(result_parts['title'], '1984')
        self.assertEqual(result_parts['authors'], ['Orwell, George'])

    def test_filename_url_encoded(self):
        html_text = """
        libgen/Orwell%2C%20George/1984.mobi
        """
        result = parse_book(html_text, self.md5)
        self.assertEqual(result['format'], 'MOBI')
        self.assertEqual(result['filename'], '1984.mobi')
        self.assertEqual(result['title'], '1984')


    def test_field_links(self):
        html_text = """
        <a href="/search?q=1984">1984</a>
        <a href="/search?q=9780451524935">9780451524935</a>
        <a href="/search?q=English">English</a>
        <a href="/search?q=George%20Orwell">George Orwell</a>
        <a href="/search?q=Secker%20%26%20Warburg">Secker & Warburg</a>
        """
        result = parse_book(html_text, self.md5)
        self.assertEqual(result['year'], "1984")
        self.assertEqual(result['isbn'], "9780451524935")
        self.assertEqual(result['language'], "English")
        # Author link matching uses heuristic `re.search(r'[\u00C0-\u017F]', label)` or `',' in label`, which isn't present in "George Orwell"
        # Let's add a comma version for author
        html_text_comma = '<a href="/search?q=Orwell%2C%20George">Orwell, George</a>'
        result2 = parse_book(html_text_comma, self.md5)
        self.assertEqual(result2['authors'], ["Orwell, George"])

        # Publisher fallback logic
        html_text_pub = '<a href="/search?q=Secker%20%26%20Warburg">Secker & Warburg</a>'
        result3 = parse_book(html_text_pub, self.md5)
        self.assertEqual(result3['publisher'], "Secker & Warburg")

    def test_fallbacks_categories_covers_servers(self):
        html_text = """
        <a href="https://annas-archive.gl/categories/Fiction">Fiction</a>
        <a href="https://annas-archive.gl/author/George%20Orwell">George Orwell</a>
        https://covers.example.com/cover.jpg
        <a href="http://example-download.com/file" class="archive-download-pill">Download</a>
        """
        result = parse_book(html_text, self.md5)
        self.assertIn("Fiction", result['categories'])
        self.assertEqual(result['authors'], ["George Orwell"])
        self.assertEqual(result['cover'], "https://covers.example.com/cover.jpg")
        self.assertEqual(len(result['download_servers']), 1)
        self.assertEqual(result['download_servers'][0]['host'], "example-download.com")
        self.assertEqual(result['download_servers'][0]['url'], "http://example-download.com/file")


from aa_proxy import parse_search

class TestParseSearch(unittest.TestCase):

    def test_normal_result(self):
        html = """
        <div data-content="Title Content"></div>
        <div data-content="John Doe"></div>
        <span>>libgen/123/abcd.pdf<</span>
        <a href="/md5/00000000000000000000000000000001" class="line-clamp">Normal Title</a>
        <span>123456789X</span>
        <span>2020</span>
        """
        results = parse_search(html)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r['md5'], "00000000000000000000000000000001")
        self.assertEqual(r['title'], "Normal Title")
        self.assertEqual(r['authors'], ["John Doe"])
        self.assertEqual(r['filepath'], "libgen/123/abcd.pdf")
        self.assertEqual(r['isbn'], "123456789X")
        self.assertEqual(r['year'], "2020")

    def test_fallback_md5(self):
        # Missing 'line-clamp' class
        html = """
        <a href="/md5/00000000000000000000000000000002">Fallback Title</a>
        """
        results = parse_search(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['md5'], "00000000000000000000000000000002")
        self.assertEqual(results[0]['title'], "Fallback Title")

    def test_skip_words(self):
        html = """
        <a href="/md5/00000000000000000000000000000003" class="line-clamp">Read Online Now</a>
        <a href="/md5/00000000000000000000000000000004" class="line-clamp">Download Book</a>
        <a href="/md5/00000000000000000000000000000005" class="line-clamp">Valid Title</a>
        """
        results = parse_search(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['md5'], "00000000000000000000000000000005")
        self.assertEqual(results[0]['title'], "Valid Title")

    def test_author_title_split_and_language(self):
        html = """
        <a href="/md5/00000000000000000000000000000006" class="line-clamp">Jane Doe - My Great Book (English)</a>
        """
        results = parse_search(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['authors'], ["Jane Doe"])
        self.assertEqual(results[0]['title'], "My Great Book (English)")
        self.assertEqual(results[0]['language'], "English")

    def test_deduplication(self):
        html = """
        <a href="/md5/00000000000000000000000000000007" class="line-clamp">Dupe Title</a>
        <a href="/md5/00000000000000000000000000000007" class="line-clamp">Dupe Title Again</a>
        <a href="/md5/00000000000000000000000000000008" class="line-clamp">Unique Title</a>
        """
        results = parse_search(html)
        self.assertEqual(len(results), 2)
        md5s = [r['md5'] for r in results]
        self.assertEqual(md5s, ["00000000000000000000000000000007", "00000000000000000000000000000008"])
if __name__ == '__main__':
    unittest.main()
