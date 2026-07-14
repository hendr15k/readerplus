# Changelog

Alle nennenswerten Änderungen an ReaderPlus.

## v26 — Reader-Toolbar & Resume
- **Persistente Schriftgröße**: Neue Toolbar im Reader mit `−` / `+` (`A-` / `A+`).
  Auswahl wird in `localStorage` (`rp_font_size`) gespeichert und beim nächsten
  Öffnen wiederhergestellt.
- **Auto-Scroll-Toggle**: Pfeil-Button in der Toolbar deaktiviert das
  automatische Nachscrollen der aktiven Satzposition. Shortcut: `A`.
- **Lese-Fortsetzung**: Die aktuelle Satzposition (`currentSentIdx`) wird
  pro Bibliothek-Eintrag in `localStorage` (`rp_progress:<id>`) gespeichert
  und beim erneuten Öffnen automatisch wiederhergestellt.
- **Safe-Area Insets**: Player-Bar und Mobile-Toggle respektieren
  `env(safe-area-inset-top/bottom)` für Geräte mit Notch.
- **Tastatur-Shortcuts erweitert**: `A` (Auto-Scroll), `+` / `-`
  (Schriftgröße). Shortcut-Overlay aktualisiert.

## v25 — Mobile Sidebar Accessibility
- **Sidebar-Accessibility**: Mobile-Toggle setzt nun `aria-controls` /
  `aria-expanded`, ein Escape-Tastendruck schließt die Sidebar.
- **Resize-Cleanup**: Beim Verlassen des Mobile-Modus wird die Sidebar
  zuverlässig zurückgesetzt.
- **z-index-Konsistenz**: Vereinheitlichte Stacking-Order für Header,
  Player und Mobile-Toggle.

## v24 — Scroll-Fix
- `body` und `.app` verwenden wieder `100dvh`. `.content` wächst über
  `height: 100%`, sodass die Reader-Spalte wieder scrollbar ist.

## v23 — Prefetch
- Piper-TTS-Antworten werden beim Satzwechsel im Hintergrund
  vorgeladen, sobald der Sprachcache des aktuellen Satzes eintrifft.
- Verhindert hörbare Pausen beim Wechsel zwischen Sätzen.

## v22 — History
- Lese-History pro Bibliothek-Eintrag mit Zeitstempel und zuletzt
  gespieltem Satz. Schnellzugriff aus der Sidebar.

## v21 — Bookmark & Swipe
- Mobile-Wisch-Gesten (links/rechts) zum Navigieren zwischen Sätzen.
- Bookmark-Verwaltung im Reader.

## v20 — Voice-Persistenz
- Stimme und Sprechtempo (`length_scale`) werden in `localStorage`
  gespeichert.

## v19 — Sidebar Collapse
- Sidebar kann auf Desktop eingeklappt werden, Zustand wird gemerkt.

## v18 — Performance
- Optimierte Token-Liste, kleinere DOM-Updates beim Satzwechsel.
- Audio-Decoder-Pooling.

## v17 — Aria-Live Status
- Eigene `aria-live="polite"`-Region für die aktive Satzposition.

## v16 — Cover-SSRF-Schutz
- `aa_proxy.py` blockiert nicht-öffentliche Cover-URLs.

## v12 — Layout-Baseline
- 100dvh-Layout, Mobile-First Sidebar, Notched-Safe-Areas.

## v1 — Initial
- Basisimplementierung: Suche, Bibliothek, Reader, Piper TTS.