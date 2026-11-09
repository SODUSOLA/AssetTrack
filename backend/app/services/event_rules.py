"""The device state machine (SPEC 8.1) as plain data, with no database access.

Each event type says which device statuses it may start from and which status it leaves the
device in. `None` for `allowed_from` means "any status"; `None` for `to_status` means "unchanged".
"""

from dataclasses import dataclass

from app.models.enums import DeviceStatus, EventType

S = DeviceStatus
E = EventType


@dataclass(frozen=True)
class Rule:
    allowed_from: frozenset[DeviceStatus] | None
    to_status: DeviceStatus | None


RULES: dict[EventType, Rule] = {
    E.assigned_to_unit: Rule(frozenset({S.in_stock}), S.assigned),
    E.received_for_repair: Rule(frozenset({S.assigned}), S.received_for_repair),
    E.diagnosed: Rule(frozenset({S.received_for_repair}), S.diagnosed),
    E.repair_started: Rule(frozenset({S.diagnosed, S.awaiting_parts}), S.in_repair),
    E.parts_requested: Rule(frozenset({S.in_repair}), S.awaiting_parts),
    E.repair_completed: Rule(frozenset({S.in_repair}), S.repaired),
    E.returned_to_unit: Rule(frozenset({S.repaired}), S.assigned),
    E.decommissioned: Rule(frozenset(set(S) - {S.decommissioned}), S.decommissioned),
    E.note_added: Rule(None, None),
}

# `device_registered` is written by the system when a device is registered, never by a client.
CLIENT_EVENT_TYPES = frozenset(RULES)

# Events that happen between taking a device in and giving it back. They are linked to the
# ticket of that repair cycle automatically, so the ticket shows the whole story.
CYCLE_EVENTS = frozenset(
    {
        E.diagnosed,
        E.repair_started,
        E.parts_requested,
        E.repair_completed,
        E.returned_to_unit,
    }
)


def is_allowed(event_type: EventType, status: DeviceStatus) -> bool:
    rule = RULES[event_type]
    return rule.allowed_from is None or status in rule.allowed_from


def allowed_events(status: DeviceStatus) -> list[EventType]:
    """Event types a client may log for a device in `status`, in a stable order."""
    return [e for e in RULES if is_allowed(e, status)]


def resulting_status(event_type: EventType, current: DeviceStatus) -> DeviceStatus:
    to = RULES[event_type].to_status
    return current if to is None else to
