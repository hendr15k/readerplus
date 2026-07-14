#!/usr/bin/env python3
"""
ReaderPlus Anna's Archive Proxy
Uses Playwright (headless Chromium) to fetch JS-rendered pages,
parses them into structured JSON.
"""
import re
import os
import sys
import io
import time
import json
import glob
import wave
import threading
import requests as plain_requests
from urllib.parse import quote
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

app = Flask(__name__)
CORS(app)

AA_BASE = "https://annas-archive.gl"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT_MS = 25000
WAIT_AFTER_LOAD = 3500

CACHE = {}
CACHE_TTL = 300

# ---- Piper TTS ----
VOICES_DIR = os.environ.get("VOICES_DIR", "/var/www/piper-voices")
FRONTEND_HTML = os.environ.get("FRONTEND_HTML", "/var/www/html/readerplus.html")
_voice_cache = {}          # voice_id -> PiperVoice
_voice_lock = threading.Lock()
TTS_MAX_CHARS = 1500       # keep requests bounded

VOICE_META = {
    'de_DE-thorsten-medium':  {'name': 'Thorsten (DE)',     'lang': 'de-DE', 'gender': 'male',   'quality': 'medium'},
    'en_US-amy-medium':       {'name': 'Amy (EN)',          'lang': 'en-US', 'gender': 'female', 'quality': 'medium'},
    'en_US-lessac-medium':    {'name': 'Lessac (EN)',       'lang': 'en-US', 'gender': 'female', 'quality': 'medium'},
    'en_US-joe-medium':       {'name': 'Joe (EN)',          'lang': 'en-US', 'gender': 'male',   'quality': 'medium'},
}

def load_voice(voice_id):
    """Lazily load a Piper voice, thread-safe."""
    if voice_id in _voice_cache:
        return _voice_cache[voice_id]
    with _voice_lock:
        if voice_id in _voice_cache:
            return _voice_cache[voice_id]
        from piper import PiperVoice
        onnx_path = os.path.join(VOICES_DIR, f'{voice_id}.onnx')
        json_path = onnx_path + '.json'
        if not os.path.isfile(onnx_path):
            raise FileNotFoundError(f'voice {voice_id} not found at {onnx_path}')
        voice = PiperVoice.load(onnx_path, json_path if os.path.isfile(json_path) else None)
        _voice_cache[voice_id] = voice
        return voice

def list_available_voices():
    if not os.path.isdir(VOICES_DIR):
        return []
    out = []
    for onnx_path in sorted(glob.glob(os.path.join(VOICES_DIR, '*.onnx'))):
        vid = os.path.splitext(os.path.basename(onnx_path))[0]
        meta = VOICE_META.get(vid, {'name': vid, 'lang': 'unknown', 'gender': 'unknown', 'quality': 'unknown'})
        meta['id'] = vid
        meta['size_mb'] = round(os.path.getsize(onnx_path) / 1024 / 1024, 1)
        out.append(meta)
    return out

def cached(key):
    e = CACHE.get(key)
    if e and (time.time() - e['t']) < CACHE_TTL:
        return e['v']
    return None

def store(key, val):
    CACHE[key] = {'t': time.time(), 'v': val}
    if len(CACHE) > 200:
        oldest = min(CACHE.items(), key=lambda x: x[1]['t'])[0]
        CACHE.pop(oldest, None)


def _is_private_host(hostname):
    """v14 SSRF guard: reject loopback / RFC1918 / link-local / cloud metadata.
    Returns True when the target is considered unsafe to fetch from the proxy."""
    import socket
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return True  # DNS fail → block
    for fam, *_rest, sockaddr in infos:
        ip = sockaddr[0]
        # IPv4
        if ip.count('.') == 3:
            try:
                parts = [int(x) for x in ip.split('.')]
                o = parts[0]
                if o == 10: return True                                 # 10.0.0.0/8
                if o == 127: return True                                # 127.0.0.0/8 loopback
                if o == 172 and 16 <= parts[1] <= 31: return True       # 172.16.0.0/12
                if o == 192 and parts[1] == 168: return True            # 192.168.0.0/16
                if o == 169 and parts[1] == 254: return True            # 169.254.0.0/16 link-local
                if o == 0: return True                                  # 0.0.0.0/8
                if o == 100 and 64 <= parts[1] <= 127: return True       # 100.64.0.0/10 CGN
                if o == 198 and (parts[1] == 18 or parts[1] == 19): return True  # 198.18/15 benchmark
                if o == 224: return True                                # multicast
                if o >= 240: return True                                # reserved/broadcast
            except Exception:
                return True
        # IPv6 loopback & private
        elif ':' in ip:
            lo = ip.lower()
            if lo == '::1' or lo.startswith('::ffff:127.') or lo.startswith('fe80:') \
                    or lo.startswith('fc') or lo.startswith('fd') \
                    or ip.startswith('169.254'):  # IPv4-mapped IPv6 link-local
                return True
    return False

def fetch_with_browser(url):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
        )
        try:
            ctx = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 800})
            page = ctx.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT_MS)
            except PWTimeout:
                pass
            except Exception as e:
                raise RuntimeError(f'goto failed: {e}')
            try:
                page.wait_for_selector('a[href*="/md5/"]', timeout=8000)
            except PWTimeout:
                pass
            page.wait_for_timeout(WAIT_AFTER_LOAD)
            html = page.content()
            return html
        finally:
            browser.close()


# ---------- Search parsing ----------

# Each result block contains, in this order:
#   <a href="/md5/{md5}">TITLE</a>          <-- main result link
#   <a href="/search?q=AUTHOR">AUTHOR</a>   <-- author link (optional)
#   <a href="/search?q=PUBLISHER">PUBLISHER</a>
#   <a href="/search?q=YEAR">YEAR</a>       <-- year link (optional)
#   <a href="/search?q=LANG">LANG</a>       <-- language (optional)
#   <a href="/search?q=ISBN">ISBN</a>       <-- ISBN (optional)
#
# The "/search?q=..." pattern is a useful anchor for fields, but the
# search keyword is URL-encoded. We'll parse them more loosely.

def parse_search(html_text):
    """Each result is a card with: md5 link (title text), data-content (title/author), filepath."""
    # Find all md5 links. For each, walk BACKWARDS to find the enclosing result block
    # (look for the nearest data-content div with the title).
    md5_anchors = list(re.finditer(
        r'<a\s+href="(/md5/([a-f0-9]{32}))"[^>]*class="[^"]*line-clamp[^"]*"[^>]*>([^<]{2,400})</a>',
        html_text, re.DOTALL
    ))
    if not md5_anchors:
        # Fallback: any md5 anchor
        md5_anchors = list(re.finditer(
            r'<a\s+href="(/md5/([a-f0-9]{32}))"[^>]*>([^<]{2,400})</a>',
            html_text, re.DOTALL
        ))

    results = []
    seen = set()
    skip_words = ('read online', 'download', 'open', 'more', 'show', 'see all', 'copy', 'share')

    for m in md5_anchors:
        url, md5, title = m.group(1), m.group(2), m.group(3).strip()
        if any(title.lower().startswith(w) for w in skip_words): continue
        if not title or len(title) < 2: continue
        if md5 in seen: continue
        seen.add(md5)

        # Look 1500 chars back to find the enclosing result card
        # The card has data-content divs for title & author
        pre_start = max(0, m.start() - 2500)
        pre = html_text[pre_start:m.start()]

        # Extract data-content="..." values that look like title/author
        # First one (violet) is title, second (amber) is author
        data_contents = re.findall(r'data-content="([^"]+)"', pre)
        author = None
        for dc in reversed(data_contents):
            if dc and dc not in (title, ''):
                author = dc
                break

        # Filepath (font-mono small text)
        path_m = re.search(r'>([a-z0-9]+/[^<>"]{10,300})<', pre)
        filepath = path_m.group(1) if path_m else None

        # Look AHEAD for ISBN / year / language links
        post = html_text[m.end():min(len(html_text), m.end() + 2500)]
        # ISBN
        isbn = None
        isbn_m = re.search(r'\b(\d{9}[\dX])\b', post)
        if isbn_m: isbn = isbn_m.group(1)
        # Year (4-digit standalone, not already in title)
        year = None
        years_in_post = re.findall(r'(?:^|\D)(19\d{2}|20\d{2})(?:\D|$)', post)
        for y in years_in_post:
            if y != '1984' and 1850 < int(y) < 2030:
                year = y; break
        # Language
        language = None
        if '(English)' in title: language = 'English'
        elif '(Deutsch)' in title or '(German)' in title: language = 'German'
        elif '(French)' in title: language = 'French'
        elif '(Español)' in title: language = 'Spanish'
        elif '(Italiano)' in title: language = 'Italian'

        # Try author/title split from "Author - Title" pattern
        if not author and ' - ' in title:
            parts = title.split(' - ', 1)
            author = parts[0].strip()
            title = parts[1].strip()

        results.append({
            'id': md5, 'md5': md5,
            'title': title,
            'authors': [author] if author else [],
            'publisher': None,
            'year': year,
            'language': language,
            'isbn': isbn,
            'filepath': filepath,
            'url': AA_BASE + url,
        })
        if len(results) >= 25: break
    return results


# ---------- Book detail parsing ----------

_FIELD_PAT = re.compile(r'<a[^>]+href="/search\?q=([^"&]+)"[^>]*>([^<]+)</a>')
_SERVER_PAT = re.compile(
    r'href="(https?://(?!annas-archive\.gl)[^"]+)"[^>]*class="[^"]*(?:archive-download-pill|archive-download-primary|archive-download-inline)[^"]*"',
    re.IGNORECASE)

def parse_book(html_text, md5):
    out = {
        'id': md5, 'slug': md5, 'md5': md5,
        'title': '', 'authors': [], 'cover': None,
        'isbn': None, 'year': None, 'publisher': None,
        'language': None, 'description': '',
        'categories': [], 'download_servers': [],
        'login_required': True, 'source_url': f'{AA_BASE}/md5/{md5}',
        'filename': '', 'filesize_bytes': None, 'format': '',
    }
    # JSON-LD
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_text, re.DOTALL):
        try:
            data = json.loads(block)
        except Exception: continue
        book = None
        if isinstance(data, dict) and data.get('@type') == 'Book': book = data
        elif isinstance(data, dict) and '@graph' in data:
            for node in data['@graph']:
                if isinstance(node, dict) and node.get('@type') == 'Book':
                    book = node; break
        if book:
            out['title'] = book.get('name', '').strip()
            author = book.get('author', '')
            if isinstance(author, str):
                out['authors'] = [a.strip() for a in re.split(r',|;| and ', author) if a.strip()]
            elif isinstance(author, list):
                out['authors'] = [str(a).strip() for a in author if a]
            out['cover'] = book.get('image')
            out['isbn'] = book.get('isbn')
            yr = book.get('datePublished')
            if yr: out['year'] = str(yr)[:4]
            out['publisher'] = book.get('publisher')
            out['language'] = book.get('inLanguage')
            desc = book.get('description', '')
            if desc: out['description'] = desc[:3000]
            break

    # Title from <title> tag
    if not out['title']:
        m = re.search(r'<title>([^<]+)</title>', html_text)
        if m:
            t = m.group(1).strip()
            t = re.sub(r'\s*[-–—]\s*Anna.?s Archive.*$', '', t).strip()
            if t and t.lower() != "anna's archive":
                out['title'] = t

    # Filename → title/author/format/filesize
    # AA sometimes embeds the filepath URL-encoded (e.g. O%5COrwell%2C%20George)
    file_m = re.search(r'(?:zlib|lgli|lgrs|libgen)[/\\](?:[^/\\\n<"]+[/\\])?([^/\\\n<"]+?)\.(epub|mobi|pdf|azw3|djvu|fb2|txt|cbr|cbz|rtf|html|htm|doc|docx|chm|lit|odt)(?:\b|%20|&nbsp;|"|<|$)',
                       html_text, re.IGNORECASE)
    if file_m:
        fname = file_m.group(1); ext = file_m.group(2).lower()
        # URL-decode
        from urllib.parse import unquote
        fname = unquote(fname)
        out['filename'] = fname + '.' + ext
        out['format'] = ext.upper()
        if not out['title']:
            clean = re.sub(r'^no-category\s*-\s*', '', fname)
            if ' - ' in clean:
                parts = clean.split(' - ', 1)
                if not out['authors']: out['authors'] = [parts[0].strip()]
                out['title'] = parts[1].strip()
            else:
                # No " - " separator. Try to strip extension-only filename
                # Strip dash-separated author prefix like "orwell-1984" → "1984"
                # but keep it as title since we can't reliably tell author from this
                out['title'] = clean.strip()
        # Also look at the directory name for author (e.g. "O\Orwell, George\orwell-1984.pdf")
        if not out['authors']:
            dir_m = re.search(r'[\\/]([A-Z][^\\/]+[\\/](?:[^\\/]+[\\/])?[^\\/]+)\.(?:epub|mobi|pdf|azw3)', html_text)
            # Look for path components that look like an author (e.g. "Orwell, George")
            author_in_path = re.findall(r'[\\/]([A-Z][a-zA-Z]+,\s+[A-Z][a-zA-Z]+)[\\/]', html_text)
            if author_in_path:
                out['authors'] = [author_in_path[0]]
    sz_m = re.search(r'filesize_bytes[:\s]+(\d+)', html_text)
    if sz_m: out['filesize_bytes'] = int(sz_m.group(1))

    if not out['year']:
        yrs = re.findall(r'\b(19\d{2}|20\d{2})\b', html_text)
        if yrs: out['year'] = max(set(yrs), key=yrs.count)

    # Field links in /search?q= form
    seen = set()
    for fm in _FIELD_PAT.finditer(html_text):
        from urllib.parse import unquote
        kw = unquote(fm.group(1)).strip()
        label = fm.group(2).strip()
        if (kw, label) in seen: continue
        seen.add((kw, label))
        if re.match(r'^\d{4}$', kw) and not out['year']: out['year'] = kw
        elif re.match(r'^\d{9,}[\dX]$', re.sub(r'[\s\-]', '', kw)) and not out['isbn']:
            out['isbn'] = re.sub(r'[\s\-]', '', kw)
        elif kw.lower() in ('english', 'deutsch', 'german', 'french', 'spanish', 'français', 'español', 'italian', 'russian'):
            if not out['language']: out['language'] = kw
        elif not out['authors'] and (',' in label or re.search(r'[\u00C0-\u017F]', label)) and 0 < len(label) < 80:
            out['authors'] = [label]
        elif not out['publisher'] and 0 < len(label) < 80 and label not in (out['authors'] or ['']):
            out['publisher'] = label

    # Cover
    if not out['cover']:
        m = re.search(r'(https://covers\.[^"\s]+?\.(?:jpg|jpeg|png|webp))', html_text)
        if m: out['cover'] = m.group(1)
    if not out['cover']:
        m = re.search(r'(https://[a-z0-9.\-]*covers?[a-z0-9.\-]*/[^\s"<>]+?\.(?:jpg|jpeg|png|webp))', html_text, re.IGNORECASE)
        if m: out['cover'] = m.group(1)

    # Categories
    cats = re.findall(r'href="https://annas-archive\.gl/categories/[^"]+"[^>]*>([^<]+)</a>', html_text)
    cseen = set()
    for c in cats:
        c = c.strip()
        if c and c not in cseen: cseen.add(c); out['categories'].append(c)
        if len(out['categories']) >= 8: break

    # Author links fallback
    if not out['authors']:
        authors = re.findall(r'href="https://annas-archive\.gl/author/[^"]+"[^>]*>([^<]+)</a>', html_text)
        out['authors'] = [a.strip() for a in authors[:5] if a.strip()]

    # ISBN
    if not out['isbn']:
        m = re.search(r'(?:isbn|ISBN)[^\d]{0,20}([\dX\-]{10,17})', html_text)
        if m: out['isbn'] = m.group(1).replace('-', '')

    # Language hint from title
    if not out['language']:
        if '(English)' in out['title']: out['language'] = 'English'
        elif '(Deutsch)' in out['title']: out['language'] = 'German'
        elif '(French)' in out['title']: out['language'] = 'French'

    # Download servers
    servers = []
    for sm in _SERVER_PAT.finditer(html_text):
        url = sm.group(1)
        host = re.search(r'https?://([^/]+)', url).group(1)
        if not any(s['host'] == host for s in servers):
            servers.append({'host': host, 'url': url, 'requires_login': True})
    out['download_servers'] = servers[:10]
    return out


# ---------- Routes ----------

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q: return jsonify({'error': 'query parameter q required'}), 400
    page = request.args.get('page', '1')
    cache_key = f"search:{q}:{page}"
    cv = cached(cache_key)
    if cv: return jsonify(cv)
    try:
        url = f"{AA_BASE}/search?q={quote(q)}&page={page}"
        html = fetch_with_browser(url)
    except Exception as e:
        return jsonify({'error': f'fetch failed: {e}'}), 502
    results = parse_search(html)
    payload = {
        'query': q, 'page': int(page), 'count': len(results),
        'results': results, 'source_url': f"{AA_BASE}/search?q={quote(q)}",
    }
    store(cache_key, payload)
    return jsonify(payload)


@app.route('/api/book/<book_id>')
def book_detail(book_id):
    cache_key = f"book:{book_id}"
    cv = cached(cache_key)
    if cv: return jsonify(cv)
    try:
        url = f"{AA_BASE}/md5/{book_id}"
        html = fetch_with_browser(url)
    except Exception as e:
        return jsonify({'error': f'fetch failed: {e}'}), 502
    data = parse_book(html, book_id)
    data['source_url'] = url
    store(cache_key, data)
    return jsonify(data)


@app.route('/api/cover')
def cover_proxy():
    url = request.args.get('url', '')
    if not url.startswith('https://'):
        return jsonify({'error': 'invalid url'}), 400
    # v14: SSRF guard — resolve hostname and reject private/loopback addresses.
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or '').lower()
        if not host or _is_private_host(host):
            return jsonify({'error': 'host not allowed (SSRF guard)'}), 400
    except Exception:
        return jsonify({'error': 'invalid url'}), 400
    try:
        r = plain_requests.get(url, headers={'User-Agent': UA, 'Referer': AA_BASE}, timeout=20, stream=True, allow_redirects=False)
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    if r.status_code != 200:
        return jsonify({'error': f'upstream {r.status_code}'}), 502
    return Response(r.content, content_type=r.headers.get('Content-Type', 'image/jpeg'),
                    headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=86400'})


@app.route('/api/voices')
def voices():
    return jsonify({'voices': list_available_voices()})

@app.route('/api/tts', methods=['GET', 'POST'])
def tts():
    """Synthesize text via Piper to WAV. Piper runs in a worker thread (CPU-bound)."""
    data = request.get_json(silent=True) or {}
    text = data.get('text') or request.args.get('text', '').strip()
    voice_id = data.get('voice') or request.args.get('voice', 'de_DE-thorsten-medium')
    length_scale = float(data.get('length_scale') or request.args.get('length_scale') or 1.0)
    if not text:
        return jsonify({'error': 'text parameter required'}), 400
    if len(text) > TTS_MAX_CHARS:
        text = text[:TTS_MAX_CHARS]
    try:
        voice = load_voice(voice_id)
    except FileNotFoundError as e:
        return jsonify({'error': str(e), 'available_voices': list_available_voices()}), 404
    except Exception as e:
        return jsonify({'error': f'voice load failed: {e}'}), 500

    synth_conf_kwargs = {'length_scale': max(0.5, min(2.0, length_scale))}

    def synth_in_thread():
        from piper import SynthesisConfig
        buf = io.BytesIO()
        syn = SynthesisConfig(**synth_conf_kwargs)
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(voice.config.sample_rate)
            for chunk in voice.synthesize(text, syn):
                wf.writeframes(chunk.audio_int16_bytes)
        return buf.getvalue()

    # Run in a worker thread so we don't block the single-threaded sync_playwright loop
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        future = ex.submit(synth_in_thread)
        try:
            wav = future.result(timeout=60)
        except concurrent.futures.TimeoutError:
            return jsonify({'error': 'tts synthesis timeout (60s)'}), 504
        except Exception as e:
            return jsonify({'error': f'tts synthesis failed: {e}'}), 500

    resp = Response(wav, mimetype='audio/wav')
    resp.headers['Content-Length'] = len(wav)
    resp.headers['X-Voice'] = voice_id
    resp.headers['X-Sample-Rate'] = str(voice.config.sample_rate)
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/')
def index():
    if os.path.isfile(FRONTEND_HTML):
        return send_file(FRONTEND_HTML, mimetype='text/html')
    return Response('<h1>ReaderPlus proxy running</h1><p>See /api/health</p>', mimetype='text/html')


@app.route('/readerplus.html')
def readerplus_html():
    if os.path.isfile(FRONTEND_HTML):
        return send_file(FRONTEND_HTML, mimetype='text/html')
    return send_file('/tmp/opencode/uploads/readerplus/index.html', mimetype='text/html')


@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'readerplus-aa-proxy',
        'base': AA_BASE,
        'engine': 'playwright',
        'tts_engine': 'piper',
        'tts_voices_available': len(list_available_voices()),
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", "9999"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"ReaderPlus on {host}:{port} (frontend={FRONTEND_HTML}, voices={VOICES_DIR})", file=sys.stderr)
    app.run(host=host, port=port, debug=False, threaded=True)
