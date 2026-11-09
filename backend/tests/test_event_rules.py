"""The state machine, checked against SPEC 8.1 typed out independently of the code."""

import pytest

from app.models.enums import DeviceStatus, EventType
from app.services.event_rules import (
    CLIENT_EVENT_TYPES,
    CYCLE_EVENTS,
    RULES,
    allowed_events,
    is_allowed,
    resulting_status,
)

# event type -> (statuses it may start from, status it leaves the device in); None = unchanged
SPEC_8_1 = {
    "assigned_to_unit": ({"in_stock"}, "assigned"),
    "received_for_repair": ({"assigned"}, "received_for_repair"),
    "diagnosed": ({"received_for_repair"}, "diagnosed"),
    "repair_started": ({"diagnosed", "awaiting_parts"}, "in_repair"),
    "parts_requested": ({"in_repair"}, "awaiting_parts"),
    "repair_completed": ({"in_repair"}, "repaired"),
    "returned_to_unit": ({"repaired"}, "assigned"),
    "decommissioned": (
        {s.value for s in DeviceStatus} - {"decommissioned"},
        "decommissioned",
    ),
    "note_added": (None, None),
}


def test_rules_cover_exactly_the_client_events_of_the_spec() -> None:
    assert {e.value for e in RULES} == set(SPEC_8_1)
    assert EventType.device_registered not in CLIENT_EVENT_TYPES  # system-only
    assert {e.value for e in CLIENT_EVENT_TYPES} == set(SPEC_8_1)


@pytest.mark.parametrize("name", sorted(SPEC_8_1))
def test_each_rule_matches_the_spec(name: str) -> None:
    allowed, target = SPEC_8_1[name]
    rule = RULES[EventType(name)]
    if allowed is None:
        assert rule.allowed_from is None
    else:
        assert {s.value for s in rule.allowed_from} == allowed
    assert (rule.to_status.value if rule.to_status else None) == target


@pytest.mark.parametrize("status", list(DeviceStatus))
@pytest.mark.parametrize("name", sorted(SPEC_8_1))
def test_is_allowed_for_every_pair(status: DeviceStatus, name: str) -> None:
    allowed, _ = SPEC_8_1[name]
    expected = allowed is None or status.value in allowed
    assert is_allowed(EventType(name), status) is expected


@pytest.mark.parametrize("status", list(DeviceStatus))
def test_allowed_events_lists_what_may_follow(status: DeviceStatus) -> None:
    expected = {
        n for n, (allowed, _) in SPEC_8_1.items() if allowed is None or status.value in allowed
    }
    assert {e.value for e in allowed_events(status)} == expected


def test_repairs_are_in_house_so_there_is_no_vendor_step() -> None:
    assert "sent_to_vendor" not in {e.value for e in EventType}
    assert "with_vendor" not in {s.value for s in DeviceStatus}


def test_a_decommissioned_device_only_takes_notes() -> None:
    assert allowed_events(DeviceStatus.decommissioned) == [EventType.note_added]


def test_resulting_status() -> None:
    assert (
        resulting_status(EventType.diagnosed, DeviceStatus.received_for_repair)
        is DeviceStatus.diagnosed
    )
    assert resulting_status(EventType.note_added, DeviceStatus.in_repair) is DeviceStatus.in_repair


def test_cycle_events_are_the_steps_between_intake_and_return() -> None:
    assert {e.value for e in CYCLE_EVENTS} == {
        "diagnosed", "repair_started", "parts_requested",
        "repair_completed", "returned_to_unit",
    }  # fmt: skip
    assert EventType.received_for_repair not in CYCLE_EVENTS  # intake starts the cycle
