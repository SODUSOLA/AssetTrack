"""Import every model module here so Alembic and the drift test see all tables."""

from app.models.auth import RefreshToken
from app.models.complaints import Complaint, ComplaintComment
from app.models.core import Unit, User
from app.models.devices import Device
from app.models.events import Acknowledgement, DeviceEvent

__all__ = [
    "Acknowledgement",
    "Complaint",
    "ComplaintComment",
    "Device",
    "DeviceEvent",
    "RefreshToken",
    "Unit",
    "User",
]
