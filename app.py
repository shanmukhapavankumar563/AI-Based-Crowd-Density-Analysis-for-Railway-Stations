"""AI-Based Crowd Density Analysis For Railway Stations Flask entry point."""

from __future__ import annotations

import os
import smtplib
import sqlite3
import threading
import time
from pathlib import Path
from email.message import EmailMessage

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from analytics import AnalyticsManager
from density import DensityManager, draw_roi_and_calibration
from detection import YOLOTracker, draw_tracking_overlay
from tracking import TrackingManager


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "crowdsense-dev-secret-key")
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["DATABASE"] = "crowdsense.db"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_FROM"] = os.environ.get("MAIL_FROM", os.environ.get("MAIL_USERNAME", ""))

state_lock = threading.Lock()
tracker_model = YOLOTracker()
tracking_manager = TrackingManager()
density_manager = DensityManager()
analytics_manager = AnalyticsManager()

app_state = {
    "is_running": False,
    "source_mode": "webcam",
    "model_status": "YOLOv8 Ready" if tracker_model.is_ready else "YOLOv8 person model not loaded",
    "live_count": 0,
    "unique_people": 0,
    "peak_count": 0,
    "avg_per_frame": 0.0,
    "fps": 0.0,
    "density_label": "Low",
    "density_color": "#22c55e",
    "density_value": None,
    "roi_area_m2": None,
    "roi_count": 0,
    "alert": {"active": False, "message": ""},
}


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                alert_email TEXT,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "alert_email" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN alert_email TEXT")
            conn.execute("UPDATE users SET alert_email = email WHERE alert_email IS NULL OR alert_email = ''")
        conn.commit()


def current_user_payload() -> dict[str, object]:
    if "user_id" not in session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "id": session.get("user_id"),
            "name": session.get("user_name"),
            "email": session.get("user_email"),
            "alert_email": session.get("user_alert_email"),
        },
    }


def require_logged_in() -> tuple[bool, tuple[Response, int] | None]:
    if "user_id" not in session:
        return False, (jsonify({"success": False, "error": "Please log in first."}), 401)
    return True, None


def save_uploaded_file(file_storage) -> tuple[Path, str]:
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    original_name = secure_filename(file_storage.filename or "")
    timestamp = int(time.time())
    filename = f"{timestamp}_{original_name}"
    filepath = Path(app.config["UPLOAD_FOLDER"]) / filename
    file_storage.save(filepath)
    return filepath, filename


def signed_up_emails() -> list[str]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT alert_email, email FROM users ORDER BY id").fetchall()
    recipients: list[str] = []
    for row in rows:
        email = row["alert_email"] or row["email"]
        if email and email not in recipients:
            recipients.append(email)
    return recipients


def send_alert_email(message: str) -> None:
    recipients = signed_up_emails()
    if not recipients or not app.config["MAIL_SERVER"] or not app.config["MAIL_FROM"]:
        return

    subject = "AI-Based Crowd Density Analysis For Railway Stations High Density Alert"
    email_message = EmailMessage()
    email_message["Subject"] = subject
    email_message["From"] = app.config["MAIL_FROM"]
    email_message["To"] = ", ".join(recipients)
    email_message.set_content(
        "\n".join(
            [
                "AI-Based Crowd Density Analysis For Railway Stations detected a high-density crowd condition.",
                "",
                f"Alert: {message}",
                "",
                "Please open the dashboard and review the live feed immediately.",
            ]
        )
    )

    try:
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"], timeout=20) as smtp:
            if app.config["MAIL_USE_TLS"]:
                smtp.starttls()
            if app.config["MAIL_USERNAME"]:
                smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            smtp.send_message(email_message)
    except Exception as exc:
        print(f"Alert email failed: {exc}")


def send_alert_email_async(message: str) -> None:
    worker = threading.Thread(target=send_alert_email, args=(message,), daemon=True)
    worker.start()


def reset_runtime_state() -> None:
    tracking_manager.reset()
    analytics_manager.reset()
    with state_lock:
        app_state.update(
            {
                "is_running": False,
                "model_status": "YOLOv8 Ready" if tracker_model.is_ready else "YOLOv8 person model not loaded",
                "live_count": 0,
                "unique_people": 0,
                "peak_count": 0,
                "avg_per_frame": 0.0,
                "fps": 0.0,
                "density_label": "Low",
                "density_color": "#22c55e",
                "density_value": None,
                "roi_area_m2": density_manager.roi_area_m2(),
                "roi_count": 0,
                "alert": {"active": False, "message": ""},
            }
        )


def update_metrics(frame, fps: float, use_tracking: bool = True) -> np.ndarray:
    """Run detection, ROI filtering, density math, and analytics logging."""
    detections = tracker_model.track_people(frame) if use_tracking else tracker_model.detect_people(frame)
    roi_detections, counted_ids = density_manager.filter_in_roi(detections)
    summary = tracking_manager.update(roi_detections, counted_ids, fps)
    density_label, density_color, density_value = density_manager.classify_density(len(roi_detections))
    roi_area_m2 = density_manager.roi_area_m2()
    alert_state = analytics_manager.log_sample(
        live_count=summary.live_count,
        unique_people=summary.unique_people,
        density_level=density_label,
        density_value=density_value,
        roi_area_m2=roi_area_m2,
        fps=fps,
    )
    if alert_state and alert_state.get("triggered"):
        send_alert_email_async(alert_state["message"])

    processed = draw_tracking_overlay(frame, detections, counted_ids)
    processed = draw_roi_and_calibration(
        processed,
        density_manager.roi_points,
        density_manager.calibration.points,
    )
    draw_hud(processed, summary, density_label, density_color, density_value, roi_area_m2)

    with state_lock:
        app_state.update(
            {
                "is_running": True,
                "live_count": summary.live_count,
                "unique_people": summary.unique_people,
                "peak_count": summary.peak_count,
                "avg_per_frame": round(summary.avg_per_frame, 2),
                "fps": round(summary.fps, 2),
                "density_label": density_label,
                "density_color": density_color,
                "density_value": round(density_value, 3) if density_value is not None else None,
                "roi_area_m2": round(roi_area_m2, 3) if roi_area_m2 is not None else None,
                "roi_count": len(roi_detections),
                "alert": alert_state or {"active": False, "message": ""},
            }
        )

    return processed


def process_image(image_path: Path) -> tuple[str, dict[str, object]]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("Unable to read uploaded image.")

    reset_runtime_state()
    processed = update_metrics(image, fps=0.0, use_tracking=False)

    output_name = f"processed_{image_path.name}"
    output_path = Path(app.config["UPLOAD_FOLDER"]) / output_name
    success = cv2.imwrite(str(output_path), processed)
    if not success:
        raise ValueError("Unable to save processed image.")

    with state_lock:
        payload = dict(app_state)
    return output_name, payload


def draw_hud(frame, summary, density_label, density_color, density_value, roi_area_m2) -> None:
    """Render the top status overlay shown on the live stream."""
    density_bgr = hex_to_bgr(density_color)
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 88), (15, 25, 35), -1)
    cv2.putText(frame, f"LIVE COUNT: {summary.live_count}", (18, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (45, 212, 191), 2)
    cv2.putText(frame, f"UNIQUE PEOPLE: {summary.unique_people}", (18, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (45, 212, 191), 2)
    cv2.putText(frame, f"PEAK: {summary.peak_count}", (320, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (245, 158, 11), 2)
    cv2.putText(frame, f"AVG/FRAME: {summary.avg_per_frame:.2f}", (320, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (226, 232, 240), 2)
    cv2.putText(frame, f"FPS: {summary.fps:.2f}", (575, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (226, 232, 240), 2)

    density_text = (
        f"{density_label} Density ({density_value:.2f} p/m2)"
        if density_value is not None
        else f"{density_label} Density ({summary.live_count} persons/frame)"
    )
    cv2.rectangle(frame, (frame.shape[1] - 310, 14), (frame.shape[1] - 18, 54), density_bgr, -1)
    cv2.putText(frame, density_text, (frame.shape[1] - 300, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

    if roi_area_m2 is not None:
        cv2.putText(frame, f"ROI Area: {roi_area_m2:.2f} m2", (575, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (96, 165, 250), 2)
    else:
        cv2.putText(frame, "ROI Area: calibrate for m2", (575, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (96, 165, 250), 2)


def generate_stream(source) -> bytes:
    """Stream processed frames as MJPEG for video and webcam feeds."""
    cap = cv2.VideoCapture(source)
    previous = time.time()
    if not cap.isOpened():
        return

    reset_runtime_state()
    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            now = time.time()
            fps = 1.0 / max(now - previous, 1e-6)
            previous = now
            processed = update_metrics(frame, fps)

            ok, buffer = cv2.imencode(".jpg", processed, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if not ok:
                continue

            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    finally:
        cap.release()
        with state_lock:
            app_state["is_running"] = False


def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.lstrip("#")
    rgb = tuple(int(cleaned[i : i + 2], 16) for i in (0, 2, 4))
    return rgb[2], rgb[1], rgb[0]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/auth/status")
def auth_status():
    return jsonify(current_user_payload())


@app.route("/api/signup", methods=["POST"])
def signup():
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not name or not email or not password:
        return jsonify({"success": False, "error": "Name, email, and password are required."}), 400

    password_hash = generate_password_hash(password)
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (name, email, alert_email, password_hash) VALUES (?, ?, ?, ?)",
                (name, email, email, password_hash),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "An account with this email already exists."}), 409

    session["user_id"] = cursor.lastrowid
    session["user_name"] = name
    session["user_email"] = email
    session["user_alert_email"] = email
    return jsonify({"success": True, "message": "Signup successful.", **current_user_payload()})


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(force=True)
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400

    with get_db_connection() as conn:
        user = conn.execute(
            "SELECT id, name, email, alert_email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"success": False, "error": "Invalid email or password."}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    session["user_alert_email"] = user["alert_email"] or user["email"]
    return jsonify({"success": True, "message": "Login successful.", **current_user_payload()})


@app.route("/api/account/profile", methods=["POST"])
def update_profile():
    allowed, error_response = require_logged_in()
    if not allowed:
        return error_response

    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Name is required."}), 400

    with get_db_connection() as conn:
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, session["user_id"]))
        conn.commit()

    session["user_name"] = name
    return jsonify({"success": True, "message": "Profile updated.", **current_user_payload()})


@app.route("/api/account/alert-email", methods=["POST"])
def update_alert_email():
    allowed, error_response = require_logged_in()
    if not allowed:
        return error_response

    payload = request.get_json(force=True)
    alert_email = (payload.get("alert_email") or "").strip().lower()
    if not alert_email:
        return jsonify({"success": False, "error": "Alert email is required."}), 400

    with get_db_connection() as conn:
        conn.execute("UPDATE users SET alert_email = ? WHERE id = ?", (alert_email, session["user_id"]))
        conn.commit()

    session["user_alert_email"] = alert_email
    return jsonify({"success": True, "message": "Alert email updated.", **current_user_payload()})


@app.route("/api/account/password", methods=["POST"])
def change_password():
    allowed, error_response = require_logged_in()
    if not allowed:
        return error_response

    payload = request.get_json(force=True)
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""

    if not current_password or not new_password:
        return jsonify({"success": False, "error": "Current password and new password are required."}), 400

    with get_db_connection() as conn:
        user = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], current_password):
            return jsonify({"success": False, "error": "Current password is incorrect."}), 401

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), session["user_id"]),
        )
        conn.commit()

    return jsonify({"success": True, "message": "Password changed successfully."})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully.", "authenticated": False})


@app.route("/upload_image", methods=["POST"])
def upload_image():
    file = request.files.get("image")
    if file is None or file.filename == "":
        return jsonify({"error": "No image file selected."}), 400

    filepath, _filename = save_uploaded_file(file)
    try:
        output_name, payload = process_image(filepath)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"success": True, "filename": output_name, "status": payload})


@app.route("/upload_video", methods=["POST"])
def upload_video():
    file = request.files.get("video")
    if file is None or file.filename == "":
        return jsonify({"error": "No video file selected."}), 400

    filepath, filename = save_uploaded_file(file)
    return jsonify({"success": True, "filename": filename})


@app.route("/image_result/<path:filename>")
def image_result(filename: str):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/video_feed/<path:filename>")
def video_feed(filename: str):
    filepath = Path(app.config["UPLOAD_FOLDER"]) / filename
    return Response(generate_stream(str(filepath)), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/webcam_feed")
def webcam_feed():
    return Response(generate_stream(0), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/detection_status")
def detection_status():
    with state_lock:
        payload = dict(app_state)
    payload["pixel_cm"] = density_manager.pixel_to_cm()
    payload["roi_points"] = density_manager.roi_points
    payload["calibration_points"] = density_manager.calibration.points
    payload["yolo_ready"] = tracker_model.is_ready
    payload["model_status"] = (
        "YOLOv8 Ready"
        if tracker_model.is_ready
        else f"YOLOv8 person model not loaded: {tracker_model.model_name}"
    )
    return jsonify(payload)


@app.route("/api/roi", methods=["POST"])
def set_roi():
    payload = request.get_json(force=True)
    density_manager.set_roi(payload.get("points", []))
    with state_lock:
        app_state["roi_area_m2"] = density_manager.roi_area_m2()
    return jsonify({"success": True, "roi_points": density_manager.roi_points})


@app.route("/api/roi/clear", methods=["POST"])
def clear_roi():
    density_manager.clear_roi()
    with state_lock:
        app_state["roi_area_m2"] = None
    return jsonify({"success": True})


@app.route("/api/calibration", methods=["POST"])
def set_calibration():
    payload = request.get_json(force=True)
    density_manager.set_calibration_points(payload.get("points", []))
    real_length = payload.get("real_length_m")
    if real_length is not None:
        density_manager.set_real_length(float(real_length))
    with state_lock:
        app_state["roi_area_m2"] = density_manager.roi_area_m2()
    return jsonify(
        {
            "success": True,
            "pixel_cm": density_manager.pixel_to_cm(),
            "roi_area_m2": density_manager.roi_area_m2(),
        }
    )


@app.route("/api/alerts")
def alerts():
    return jsonify({"alerts": analytics_manager.alerts_payload(), "active": app_state["alert"]})


@app.route("/api/analytics")
def analytics():
    return jsonify(analytics_manager.analytics_payload())


@app.route("/api/export_csv")
def export_csv():
    csv_content = analytics_manager.export_csv()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=session_analytics.csv"},
    )


if __name__ == "__main__":
    init_db()
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    print("AI-Based Crowd Density Analysis For Railway Stations running at http://127.0.0.1:5000")
    app.run(debug=True, threaded=True)

