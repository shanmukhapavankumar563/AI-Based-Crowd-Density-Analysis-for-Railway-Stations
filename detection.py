"""YOLOv8 detection and ByteTrack integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import os
import cv2
import numpy as np

# Keep Ultralytics config inside the project workspace.
os.environ.setdefault('YOLO_CONFIG_DIR', str(Path('.ultralytics').resolve()))
os.environ.setdefault('ULTRALYTICS_CONFIG_DIR', str(Path('.ultralytics').resolve()))

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - allows UI to run without the package
    YOLO = None


@dataclass
class Detection:
    """Single tracked person detection."""

    track_id: Optional[int]
    bbox: tuple[int, int, int, int]
    confidence: float
    center: tuple[float, float]


class YOLOTracker:
    """Wraps YOLOv8 tracking so the rest of the app stays beginner-friendly."""

    def __init__(self, model_name: str = "yolov8n.pt") -> None:
        self.model_name = model_name
        self.model = None
        self.load_error: Optional[str] = None
        if YOLO is not None:
            try:
                # Allow Ultralytics to load a local weights file or its built-in model name.
                self.model = YOLO(str(Path(model_name)) if Path(model_name).exists() else model_name)
            except Exception as exc:
                self.model = None
                self.load_error = str(exc)
        else:
            self.load_error = "Ultralytics is not installed."

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    def _collect_detections(self, results) -> List[Detection]:
        """Convert Ultralytics results into the app's Detection objects."""
        detections: List[Detection] = []
        if not results:
            return detections

        boxes = results[0].boxes
        if boxes is None:
            return detections

        xyxy = boxes.xyxy.cpu().numpy().astype(int) if boxes.xyxy is not None else []
        confs = boxes.conf.cpu().numpy().tolist() if boxes.conf is not None else []
        classes = (
            boxes.cls.cpu().numpy().astype(int).tolist()
            if boxes.cls is not None
            else [0] * len(xyxy)
        )
        ids = (
            boxes.id.cpu().numpy().astype(int).tolist()
            if boxes.id is not None
            else [None] * len(xyxy)
        )

        for index, box in enumerate(xyxy):
            # Keep only COCO class 0 ("person"), even if the tracker returns mixed classes.
            if index < len(classes) and classes[index] != 0:
                continue
            x1, y1, x2, y2 = box.tolist()
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            detections.append(
                Detection(
                    track_id=ids[index],
                    bbox=(x1, y1, x2, y2),
                    confidence=float(confs[index]) if index < len(confs) else 0.0,
                    center=(center_x, center_y),
                )
            )

        return detections

    def track_people(self, frame: np.ndarray) -> List[Detection]:
        """Run YOLOv8 + ByteTrack on a frame and return person detections only."""
        if self.model is None:
            return []

        results = self.model.track(
            source=frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=0.3,
            verbose=False,
        )
        return self._collect_detections(results)

    def detect_people(self, frame: np.ndarray) -> List[Detection]:
        """Use a denser, higher-resolution pass for still images."""
        if self.model is None:
            return []

        results = self.model.predict(
            source=frame,
            classes=[0],
            conf=0.1,
            imgsz=1280,
            verbose=False,
        )
        return self._collect_detections(results)


def draw_tracking_overlay(
    frame: np.ndarray,
    detections: List[Detection],
    counted_ids: set[int],
) -> np.ndarray:
    """Draw tracked bounding boxes and ID labels."""
    output = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        in_roi = det.track_id in counted_ids if det.track_id is not None else False
        color = (45, 212, 191) if in_roi else (148, 163, 184)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        label_id = det.track_id if det.track_id is not None else "NA"
        label = f"ID {label_id} {det.confidence:.2f}"
        cv2.rectangle(output, (x1, max(0, y1 - 22)), (x1 + 120, y1), color, -1)
        cv2.putText(
            output,
            label,
            (x1 + 4, max(16, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (15, 25, 35),
            1,
            cv2.LINE_AA,
        )
        cx, cy = int(det.center[0]), int(det.center[1])
        cv2.circle(output, (cx, cy), 4, color, -1)
    return output

