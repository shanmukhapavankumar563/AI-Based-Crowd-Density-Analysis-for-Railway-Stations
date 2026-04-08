"""ROI, calibration, and density calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import cv2
import numpy as np

from detection import Detection


@dataclass
class CalibrationState:
    """Stores two clicked points and the solved pixel-to-meter scale."""

    points: List[tuple[float, float]] = field(default_factory=list)
    real_length_m: Optional[float] = None
    scale_m_per_px: Optional[float] = None

    def clear(self) -> None:
        self.points.clear()
        self.real_length_m = None
        self.scale_m_per_px = None


class DensityManager:
    """Owns the ROI polygon and density math."""

    def __init__(self) -> None:
        self.roi_points: List[tuple[int, int]] = []
        self.calibration = CalibrationState()

    def set_roi(self, points: Iterable[Iterable[float]]) -> None:
        self.roi_points = [(int(p[0]), int(p[1])) for p in points][:4]

    def clear_roi(self) -> None:
        self.roi_points = []

    def set_calibration_points(self, points: Iterable[Iterable[float]]) -> None:
        self.calibration.points = [(float(p[0]), float(p[1])) for p in points][:2]

    def set_real_length(self, real_length_m: float) -> None:
        self.calibration.real_length_m = real_length_m
        if len(self.calibration.points) != 2 or real_length_m <= 0:
            self.calibration.scale_m_per_px = None
            return

        first = np.array(self.calibration.points[0], dtype=float)
        second = np.array(self.calibration.points[1], dtype=float)
        pixel_distance = float(np.linalg.norm(first - second))
        if pixel_distance <= 0:
            self.calibration.scale_m_per_px = None
            return

        self.calibration.scale_m_per_px = real_length_m / pixel_distance

    def pixel_to_cm(self) -> Optional[float]:
        if self.calibration.scale_m_per_px is None:
            return None
        return self.calibration.scale_m_per_px * 100.0

    def filter_in_roi(self, detections: Iterable[Detection]) -> tuple[list[Detection], set[int]]:
        detection_list = list(detections)
        if len(self.roi_points) < 3:
            ids = {det.track_id for det in detection_list if det.track_id is not None}
            return detection_list, ids

        polygon = np.array(self.roi_points, dtype=np.int32)
        inside: list[Detection] = []
        inside_ids: set[int] = set()
        for det in detection_list:
            if cv2.pointPolygonTest(polygon, det.center, False) >= 0:
                inside.append(det)
                if det.track_id is not None:
                    inside_ids.add(det.track_id)
        return inside, inside_ids

    def roi_area_px(self) -> float:
        if len(self.roi_points) < 3:
            return 0.0
        return float(cv2.contourArea(np.array(self.roi_points, dtype=np.float32)))

    def roi_area_m2(self) -> Optional[float]:
        if self.calibration.scale_m_per_px is None:
            return None
        return self.roi_area_px() * (self.calibration.scale_m_per_px ** 2)

    def density_value(self, people_in_roi: int) -> Optional[float]:
        area_m2 = self.roi_area_m2()
        if area_m2 is None or area_m2 <= 0:
            return None
        return people_in_roi / area_m2

    def classify_density(self, people_in_roi: int) -> tuple[str, str, Optional[float]]:
        density = self.density_value(people_in_roi)
        if density is None:
            if people_in_roi <= 2:
                return "Low", "#22c55e", None
            if people_in_roi <= 5:
                return "Medium", "#f59e0b", None
            return "High", "#ef4444", None

        if density < 0.5:
            return "Low", "#22c55e", density
        if density <= 1.5:
            return "Medium", "#f59e0b", density
        return "High", "#ef4444", density


def draw_roi_and_calibration(
    frame,
    roi_points: list[tuple[int, int]],
    calibration_points: list[tuple[float, float]],
) -> np.ndarray:
    """Draw ROI and calibration overlays on the processed frame."""
    output = frame.copy()

    if len(roi_points) >= 2:
        for idx in range(len(roi_points)):
            pt1 = roi_points[idx]
            pt2 = roi_points[(idx + 1) % len(roi_points)]
            if idx == len(roi_points) - 1 and len(roi_points) < 4:
                break
            cv2.line(output, pt1, pt2, (45, 212, 191), 2, cv2.LINE_AA)
        for point in roi_points:
            cv2.circle(output, point, 5, (45, 212, 191), -1)

    if len(calibration_points) == 2:
        p1 = tuple(int(v) for v in calibration_points[0])
        p2 = tuple(int(v) for v in calibration_points[1])
        cv2.line(output, p1, p2, (96, 165, 250), 2, cv2.LINE_AA)
        cv2.circle(output, p1, 5, (96, 165, 250), -1)
        cv2.circle(output, p2, 5, (96, 165, 250), -1)

    return output
