"""Session analytics and alert tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from typing import Optional

import csv


@dataclass
class AlertEvent:
    started_at: datetime
    ended_at: Optional[datetime] = None
    peak_density: float = 0.0
    status: str = "Active"

    def duration_seconds(self) -> int:
        end_time = self.ended_at or datetime.now()
        return int((end_time - self.started_at).total_seconds())


class AnalyticsManager:
    """Stores session samples, computes charts, and raises alerts."""

    def __init__(self, location_name: str = "Platform A") -> None:
        self.location_name = location_name
        self.samples: list[dict] = []
        self.alerts: list[AlertEvent] = []
        self.high_density_started_at: Optional[datetime] = None
        self.active_alert: Optional[AlertEvent] = None

    def reset(self) -> None:
        self.samples.clear()
        self.alerts.clear()
        self.high_density_started_at = None
        self.active_alert = None

    def log_sample(
        self,
        live_count: int,
        unique_people: int,
        density_level: str,
        density_value: Optional[float],
        roi_area_m2: Optional[float],
        fps: float,
    ) -> Optional[dict]:
        now = datetime.now()
        sample = {
            "timestamp": now.isoformat(timespec="seconds"),
            "hour": now.hour,
            "live_count": live_count,
            "unique_people": unique_people,
            "density_level": density_level,
            "density_value": round(density_value, 3) if density_value is not None else None,
            "roi_area_m2": round(roi_area_m2, 3) if roi_area_m2 is not None else None,
            "fps": round(fps, 2),
        }
        self.samples.append(sample)
        return self._update_alert_state(now, density_level, density_value)

    def _update_alert_state(
        self,
        now: datetime,
        density_level: str,
        density_value: Optional[float],
    ) -> Optional[dict]:
        if density_level == "High":
            if self.high_density_started_at is None:
                self.high_density_started_at = now

            elapsed = (now - self.high_density_started_at).total_seconds()
            if elapsed >= 10 and self.active_alert is None:
                self.active_alert = AlertEvent(started_at=self.high_density_started_at)
                self.active_alert.peak_density = density_value or 0.0
                self.alerts.append(self.active_alert)
                return {
                    "active": True,
                    "triggered": True,
                    "message": f"HIGH DENSITY ALERT - {self.location_name} - {now.strftime('%Y-%m-%d %H:%M:%S')}",
                }

            if self.active_alert is not None:
                self.active_alert.peak_density = max(self.active_alert.peak_density, density_value or 0.0)
                return {
                    "active": True,
                    "triggered": False,
                    "message": f"HIGH DENSITY ALERT - {self.location_name} - {now.strftime('%Y-%m-%d %H:%M:%S')}",
                }

        if density_level != "High":
            self.high_density_started_at = None
            if self.active_alert is not None:
                self.active_alert.ended_at = now
                self.active_alert.status = "Resolved"
                self.active_alert = None

        return {"active": False, "triggered": False, "message": ""}

    def alerts_payload(self) -> list[dict]:
        rows = []
        for alert in self.alerts:
            rows.append(
                {
                    "timestamp": alert.started_at.isoformat(timespec="seconds"),
                    "duration": alert.duration_seconds(),
                    "peak_density": round(alert.peak_density, 3),
                    "status": alert.status,
                }
            )
        return rows

    def analytics_payload(self) -> dict:
        heatmap = {hour: 0 for hour in range(24)}
        for alert in self.alerts:
            heatmap[alert.started_at.hour] += 1

        return {
            "densitySeries": [
                {"time": sample["timestamp"], "value": sample["density_value"] or 0}
                for sample in self.samples
            ],
            "uniqueSeries": [
                {"time": sample["timestamp"], "value": sample["unique_people"]}
                for sample in self.samples
            ],
            "alertHeatmap": [{"hour": hour, "count": count} for hour, count in heatmap.items()],
            "alerts": self.alerts_payload(),
        }

    def export_csv(self) -> str:
        buffer = StringIO()
        fieldnames = [
            "timestamp",
            "hour",
            "live_count",
            "unique_people",
            "density_level",
            "density_value",
            "roi_area_m2",
            "fps",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(self.samples)
        return buffer.getvalue()
