# AI-Based-Crowd-Density-Analysis-for-Railway-Stations

AI-Based-Crowd-Density-Analysis-for-Railway-Stations is a Flask-based web application for monitoring crowd density in railway station environments using computer vision. The system supports image upload, video upload, and webcam-based monitoring with live crowd counting, ROI-based density analysis, analytics, and alert tracking.

## Features

- YOLO-based person detection and tracking
- Crowd density estimation inside a selected ROI
- Image, video, and webcam input support
- Live dashboard with count, peak, FPS, and density metrics
- Calibration tools for pixel-to-meter conversion
- Analytics charts and CSV export
- Alert logging and email notification support
- Login, registration, and account settings

## Tech Stack

- Python
- Flask
- OpenCV
- Ultralytics YOLOv8
- NumPy
- SQLite
- HTML, CSS, JavaScript

## Project Structure

- `app.py` - Main Flask application
- `detection.py` - YOLO detection and tracking logic
- `density.py` - ROI and density calculation logic
- `tracking.py` - Crowd tracking helpers
- `analytics.py` - Analytics and alert history
- `templates/` - HTML templates
- `static/` - CSS and JavaScript assets

## Installation

1. Clone the repository:

```bash
git clone https://github.com/shanmukhapavankumar563/AI-Based-Crowd-Density-Analysis-for-Railway-Stations.git
cd AI-Based-Crowd-Density-Analysis-for-Railway-Stations
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run Locally

```bash
python app.py
```

Open the app in your browser:

`http://127.0.0.1:5000`

## Environment Variables

The application can use these optional environment variables:

- `SECRET_KEY`
- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `MAIL_USE_TLS`
- `MAIL_FROM`

## Deployment Notes

For Render deployment, use a Python Web Service.

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

Note: cloud deployment may have limitations for local webcam access, persistent uploads, and SQLite storage.

## GitHub Repository

https://github.com/shanmukhapavankumar563/AI-Based-Crowd-Density-Analysis-for-Railway-Stations
