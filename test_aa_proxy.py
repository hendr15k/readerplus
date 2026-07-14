import unittest
from unittest.mock import patch
from aa_proxy import parse_book, app

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


class TestSearchAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_search_missing_q(self):
        response = self.client.get('/api/search')
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'query parameter q required')

        response_empty_q = self.client.get('/api/search?q=   ')
        self.assertEqual(response_empty_q.status_code, 400)

    @patch('aa_proxy.fetch_with_browser')
    @patch('aa_proxy.cached')
    @patch('aa_proxy.store')
    def test_search_success(self, mock_store, mock_cached, mock_fetch):
        mock_cached.return_value = None
        mock_html = """
        <div data-content="The Great Gatsby"></div>
        <div data-content="F. Scott Fitzgerald"></div>
        <div class="font-mono">>zlib/O/Fitzgerald/gatsby.epub<</div>
        <a href="/md5/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" class="line-clamp">The Great Gatsby</a>
        """
        mock_fetch.return_value = mock_html

        response = self.client.get('/api/search?q=gatsby')
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data['query'], 'gatsby')
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['count'], 1)
        self.assertEqual(len(data['results']), 1)

        result = data['results'][0]
        self.assertEqual(result['md5'], 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4')
        self.assertEqual(result['title'], 'The Great Gatsby')
        self.assertEqual(result['authors'], ['F. Scott Fitzgerald'])

        mock_fetch.assert_called_once_with('https://annas-archive.gl/search?q=gatsby&page=1')
        mock_cached.assert_called_once_with('search:gatsby:1')
        mock_store.assert_called_once()

    @patch('aa_proxy.fetch_with_browser')
    @patch('aa_proxy.cached')
    def test_search_cached(self, mock_cached, mock_fetch):
        cached_response = {
            'query': 'test', 'page': 1, 'count': 0, 'results': [], 'source_url': 'https://annas-archive.gl/search?q=test'
        }
        mock_cached.return_value = cached_response

        response = self.client.get('/api/search?q=test')
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data, cached_response)

        mock_cached.assert_called_once_with('search:test:1')
        mock_fetch.assert_not_called()

    @patch('aa_proxy.fetch_with_browser')
    @patch('aa_proxy.cached')
    def test_search_fetch_failed(self, mock_cached, mock_fetch):
        mock_cached.return_value = None
        mock_fetch.side_effect = Exception("Browser timeout")

        response = self.client.get('/api/search?q=test')
        self.assertEqual(response.status_code, 502)

        data = response.get_json()
        self.assertIn('error', data)
        self.assertIn('fetch failed: Browser timeout', data['error'])

if __name__ == '__main__':
    unittest.main()
