# Sydney Transport Dashboard

A quiet black-and-white commute dashboard for an e-ink reader.

This project turns a spare Xiaomi/Duokan Mi Reader into a small always-on information screen for Sydney transport, date, and weather. It is designed around a 758x1024 e-ink display, but it also has responsive layouts for desktop browsers and phones.

## The Story

The idea came from a disrupted trip.

One day, just as I was about to leave home, new Metro trackwork appeared and broke the route I had planned to take. I realized I had an unused Mi Reader sitting around, with a perfectly good e-ink screen, and it would be much more useful as a small household transit board than as a forgotten device in a drawer.

So I applied for a Transport for NSW API key and started building a dashboard that shows the station information I check most often, plus the date and weather before heading out.

## Features

- Live TfNSW departure data for selected Central platforms, Metro, and Light Rail services.
- Weather and hourly forecast from Open-Meteo.
- E-ink friendly visual design: black and white, high contrast, minimal animation.
- Responsive layouts:
  - Mi Reader / 3:4 tablet portrait: designed to fit on one screen.
  - Desktop: date, weather, and hourly forecast across the top; transport boards below.
  - Phone: stacked layout with scrolling.
- Conservative train stopping-pattern display:
  - Shows stop sequences only when the Trip Planner API can exactly match the departure.
  - Hides uncertain information instead of guessing.
- Plain Python backend with static HTML/CSS/JavaScript frontend.
- No frontend framework or build step required.

## Tech Stack

- Backend: Python standard library HTTP server.
- Frontend: static HTML, CSS, and vanilla JavaScript.
- Transport data: Transport for NSW Trip Planner APIs.
- Weather data: Open-Meteo.
- Deployment target: a lightweight Linux service, currently used behind a local reverse proxy.

## Running Locally

Create a local environment file:

```bash
cp mireader-dashboard.env.example .env
```

Set your TfNSW API key in `.env`:

```text
TFNSW_API_KEY=your_key_here
```

Start the server:

```bash
python3 server.py
```

Open:

```text
http://127.0.0.1:8080/
```

You can change the port:

```bash
PORT=8090 python3 server.py
```

## Deploying on Vercel

Use these import settings:

- Framework Preset: Other
- Root Directory: `./`
- Build Command: leave empty
- Output Directory: leave empty

Add this Environment Variable for Production, Preview, and Development:

```text
TFNSW_API_KEY=your_key_here
```

The repo includes `vercel.json` routing so Vercel serves the static dashboard from `static/` and exposes the backend state endpoint at `/api/state`.

## Configuration

Common environment variables:

```text
PORT=8080
TFNSW_API_KEY=...
DASHBOARD_LAT=-33.8846
DASHBOARD_LON=151.2119
DASHBOARD_WEATHER_CACHE_SECONDS=300
```

The current dashboard is tuned for Central Station and nearby Sydney commute patterns. Stop IDs, watched lines, and platform metadata live in `server.py`.

## Design Notes

The UI intentionally avoids colorful, motion-heavy dashboard patterns. E-ink displays refresh slowly and look best with strong contrast, stable layout, and simple shapes. The dashboard uses dense cards, bold type, and restrained animation so it remains readable on the Mi Reader while still working well in regular browsers.

## License

MIT License. See [LICENSE](LICENSE).
