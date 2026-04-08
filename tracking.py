"""Track state and unique ID management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from detection import Detection


@dataclass
class TrackingSummary:
    """Current session-level tracking metrics."""

    live_count: int = 0
    unique_people: int = 0
    peak_count: int = 0
    avg_per_frame: float = 0.0
    fps: float = 0.0
    frame_count: int = 0
    counted_ids: set[int] = field(default_factory=set)
    seen_ids: set[int] = field(default_factory=set)


class TrackingManager:
    """Stores persistent IDs returned by ByteTrack."""

    def __init__(self) -> None:
        self.summary = TrackingSummary()
        self.total_people_sum = 0

    def reset(self) -> None:
        self.summary = TrackingSummary()
        self.total_people_sum = 0

    def update(
        self,
        detections: Iterable[Detection],
        counted_ids: set[int],
        fps: float,
    ) -> TrackingSummary:
        detection_list = list(detections)
        self.summary.frame_count += 1
        self.summary.live_count = len(detection_list)
        self.summary.counted_ids = counted_ids
        self.summary.fps = fps

        for det in detection_list:
            if det.track_id is not None:
                self.summary.seen_ids.add(det.track_id)

        self.summary.unique_people = (
            len(self.summary.seen_ids)
            if self.summary.seen_ids
            else self.summary.live_count
        )
        self.summary.peak_count = max(self.summary.peak_count, self.summary.live_count)
        self.total_people_sum += self.summary.live_count
        self.summary.avg_per_frame = self.total_people_sum / max(self.summary.frame_count, 1)
        return self.summary
