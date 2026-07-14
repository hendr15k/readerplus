# ReaderPlus — Server-Setup

ReaderPlus ist eine Text-zu-Sprache-Web-App mit:
- **Frontend** (`readerplus.html`) — Single-File HTML, läuft auf nginx/Caddy
- **AA + TTS Proxy** (`aa_proxy.py`) — Flask: Anna's-Archive-Suche + Piper TTS
- **Piper KI-Stimmen** (`piper-voices/`) — 4× ONNX-Modelle (de_DE-thorsten, en_US-amy/joe/lessac)

## Installation (Debian/Ubuntu als root)

```bash
# 1. Zip-File hochladen und auspacken
mkdir -p /opt/readerplus && cd /opt/readerplus
unzip readerplus.zip
chmod +x setup.sh

# 2. Setup laufen lassen (5-10 Min für Python + Chromium + Voices)
./setup.sh

# 3. Testen
curl http://localhost:9999/                        # Webapp
curl http://localhost:18792/api/health              # Proxy Health
curl http://localhost:18792/api/voices              # Stimmenliste
```

## Manuelle Pfade
- Frontend: `/var/www/html/readerplus.html`
- Proxy-Code: `/var/www/aa_proxy.py`
- Stimmen: `/var/www/piper-voices/*.onnx + *.onnx.json`
- systemd-Service: `readerplus-aa.service` (Port 18792)
- Caddy: `:9999` → `/var/www/html` + `/api/*` reverse_proxy 127.0.0.1:18792

## API-Endpoints
- `GET  /api/health` — Status-Check
- `GET  /api/voices` — Liste der Piper-Stimmen
- `POST /api/search?q=...` — Anna's Archive Search
- `GET  /api/book/{md5}` — Buch-Detail
- `GET  /api/cover?url=...` — Cover-Image-Proxy
- `POST /api/tts` — Piper Text-zu-WAV (`{text, voice, length_scale}`)

## Reader-Tastatur-Shortcuts

| Taste | Aktion |
|-------|--------|
| `Space` | Play / Pause |
| `←` / `→` | Vorheriger / nächster Satz |
| `+` / `-` | Schrift vergrößern / verkleinern |
| `A` | Auto-Scroll an / aus |
| `?` | Shortcut-Overlay anzeigen |

Die Schriftgröße und der Auto-Scroll-Status werden in `localStorage`
gespeichert (`rp_font_size`, `rp_auto_scroll`). Die zuletzt gespielte
Satzposition wird pro Bibliothek-Eintrag unter `rp_progress:<id>`
gespeichert und beim erneuten Öffnen automatisch wiederhergestellt.

## Update
```bash
cd /opt/readerplus && cp -f readerplus.html /var/www/html/
cp -f aa_proxy.py /var/www/ && systemctl restart readerplus-aa
```

Versionshistorie siehe [CHANGELOG.md](CHANGELOG.md).
