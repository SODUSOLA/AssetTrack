"""Fill an empty database with demo data so the web app has something to show (development only).

    docker compose run --rm api python -m scripts.seed_demo

It creates units, people, devices and a believable repair history (with confirmed, pending,
overdue and disputed acknowledgements), and prints the sign-in details once. The password is
random for every run, unless DEMO_PASSWORD is set (the end-to-end tests do that so they can sign
in). It refuses to run in production, and on a database that already has users.
"""

import os
import secrets
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Acknowledgement,
    Complaint,
    ComplaintComment,
    Device,
    DeviceEvent,
    Unit,
    User,
)
from app.models.enums import (
    AckStatus,
    ComplaintCategory,
    ComplaintStatus,
    DeviceStatus,
    EventType,
    PriorityLevel,
    UserRole,
)

E, S, C = EventType, DeviceStatus, ComplaintStatus
NOW = datetime.now(UTC)


def ago(days: float = 0, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


def picked_up(name: str) -> str:
    return f"Assigned to {name}. Status: open -> in_progress. Device received for repair."


def main() -> None:
    if get_settings().env == "production":
        sys.exit("Refusing to load demo data when ENV=production.")
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)
    if len(password) < 10:
        sys.exit("DEMO_PASSWORD must be at least 10 characters.")
    password_hash = hash_password(password)

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            sys.exit("This database already has users; demo data is only for an empty one.")

        units = {
            code: Unit(name=name, code=code)
            for code, name in (
                ("REG", "Registration Office"),
                ("ENR", "Enrolment Centre"),
                ("FIN", "Finance and Accounts"),
            )
        }
        db.add_all(units.values())
        db.flush()

        def person(name, email, role, unit=None):
            user = User(
                full_name=name,
                email=email,
                password_hash=password_hash,
                role=role,
                unit_id=units[unit].id if unit else None,
            )
            db.add(user)
            return user

        head = person("Funmilayo Adeyemi", "head@demo.test", UserRole.admin)
        emeka = person("Emeka Okafor", "emeka@demo.test", UserRole.engineer)
        ibrahim = person("Ibrahim Musa", "ibrahim@demo.test", UserRole.engineer)
        person("Ngozi Eze", "auditor@demo.test", UserRole.auditor)
        reps = {
            "REG": person("Adebayo Ogunleye", "adebayo@demo.test", UserRole.unit_rep, "REG"),
            "ENR": person("Chioma Nwosu", "chioma@demo.test", UserRole.unit_rep, "ENR"),
            "FIN": person("Folake Balogun", "folake@demo.test", UserRole.unit_rep, "FIN"),
        }
        db.flush()

        def device(kind, make, model, serial, unit=None, status=S.in_stock):
            d = Device(
                device_type=kind,
                make=make,
                model=model,
                serial_number=serial,
                unit_id=units[unit].id if unit else None,
                status=status,
                created_by=head.id,
                created_at=ago(90),
            )
            db.add(d)
            db.flush()
            return d

        def event(dev, kind, when, to_status, unit, actor=emeka, **kw):
            e = DeviceEvent(
                device_id=dev.id,
                event_type=kind,
                to_status=to_status,
                unit_id=units[unit].id if unit else None,
                actor_id=actor.id,
                occurred_at=when,
                **kw,
            )
            db.add(e)
            db.flush()
            return e

        def ack(ev, unit, status, when, comment=None):
            db.add(
                Acknowledgement(
                    event_id=ev.id,
                    acknowledged_by=reps[unit].id,
                    status=status,
                    comment=comment,
                    acknowledged_at=when,
                )
            )

        def ticket(
            unit,
            title,
            description,
            created,
            status=C.open,
            dev=None,
            priority=PriorityLevel.medium,
            category=ComplaintCategory.hardware,
            **kw,
        ):
            t = Complaint(
                unit_id=units[unit].id,
                raised_by=reps[unit].id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                category=category,
                device_id=dev.id if dev else None,
                created_at=created,
                **kw,
            )
            db.add(t)
            db.flush()
            return t

        def note(t, text, when, author=emeka, system=True):
            db.add(
                ComplaintComment(
                    complaint_id=t.id,
                    author_id=author.id,
                    body=text,
                    is_system=system,
                    created_at=when,
                )
            )

        def handed_over(dev, unit, days):
            e = event(
                dev,
                E.assigned_to_unit,
                ago(days),
                S.assigned,
                unit,
                counterparty_name=reps[unit].full_name,
                counterparty_user_id=reps[unit].id,
            )
            return e

        def registered(dev):
            event(dev, E.device_registered, ago(90), S.in_stock, None, actor=head)

        # --- Registration Office
        reg_laptop = device("laptop", "Dell", "Latitude 5440", "DL5440-0192", "REG", S.assigned)
        reg_printer = device(
            "printer", "HP", "LaserJet Pro M404", "HP404-7731", "REG", S.received_for_repair
        )
        reg_router = device("router", "TP-Link", "Archer C80", "TPC80-2210", "REG", S.assigned)
        # --- Enrolment Centre
        enr_desktop = device(
            "desktop", "Lenovo", "ThinkCentre M70s", "LN70-5521", "ENR", S.assigned
        )
        enr_laptop = device(
            "laptop", "HP", "ProBook 450 G9", "HP450-9040", "ENR", S.received_for_repair
        )
        enr_scanner = device("scanner", "Fujitsu", "fi-7160", "FJ7160-1187", "ENR", S.assigned)
        enr_ups = device("UPS", "APC", "Back-UPS 1500", "APC1500-3302", "ENR", S.assigned)
        # --- Finance and Accounts
        fin_printer = device(
            "printer", "Canon", "imageRUNNER 2224", "CN2224-6618", "FIN", S.in_repair
        )
        fin_desktop = device("desktop", "Dell", "OptiPlex 3000", "DO3000-4417", "FIN", S.assigned)
        fin_monitor = device("monitor", "Samsung", '24" S24C330', "SS24-8820", "FIN", S.assigned)
        # --- stock and retired
        new_laptop = device("laptop", "Dell", "Latitude 3440", "DL3440-0001", None, S.assigned)
        device("UPS", "APC", "Smart-UPS 750", "APC750-0007")  # in stock
        old_monitor = device("monitor", "LG", "W2243", "LG2243-0911", None, S.decommissioned)

        for d in (
            reg_laptop,
            reg_printer,
            reg_router,
            enr_desktop,
            enr_laptop,
            enr_scanner,
            enr_ups,
            fin_printer,
            fin_desktop,
            fin_monitor,
            new_laptop,
            old_monitor,
        ):
            registered(d)

        # Settled handovers: assigned long ago and confirmed by the unit.
        for dev, unit, days in (
            (reg_laptop, "REG", 60),
            (reg_printer, "REG", 58),
            (reg_router, "REG", 55),
            (enr_desktop, "ENR", 52),
            (enr_laptop, "ENR", 50),
            (enr_scanner, "ENR", 48),
            (enr_ups, "ENR", 47),
            (fin_printer, "FIN", 45),
            (fin_desktop, "FIN", 44),
            (fin_monitor, "FIN", 40),
        ):
            ack(handed_over(dev, unit, days), unit, AckStatus.confirmed, ago(days - 1))

        # A laptop handed to Finance yesterday: still waiting for the unit.
        handed_over(new_laptop, "FIN", 1)
        new_laptop.unit_id = units["FIN"].id
        event(
            old_monitor,
            E.decommissioned,
            ago(20),
            S.decommissioned,
            None,
            notes="Cracked panel, beyond repair",
        )

        # 1. REG laptop: repaired, returned, confirmed, ticket closed.
        t = ticket(
            "REG",
            "Laptop will not start",
            "Black screen when the power button is pressed.",
            ago(21),
            C.closed,
            reg_laptop,
            PriorityLevel.high,
            assigned_to=emeka.id,
            resolved_at=ago(17),
            closed_at=ago(16),
        )
        i = event(
            reg_laptop,
            E.received_for_repair,
            ago(20),
            S.received_for_repair,
            "REG",
            complaint_id=t.id,
            counterparty_name="Adebayo Ogunleye",
        )
        ack(i, "REG", AckStatus.confirmed, ago(20, -1))
        event(
            reg_laptop,
            E.diagnosed,
            ago(19),
            S.diagnosed,
            "REG",
            complaint_id=t.id,
            diagnosis="Faulty battery connector",
        )
        event(reg_laptop, E.repair_started, ago(19, -3), S.in_repair, "REG", complaint_id=t.id)
        event(
            reg_laptop,
            E.repair_completed,
            ago(18),
            S.repaired,
            "REG",
            complaint_id=t.id,
            notes="Connector re-seated and battery replaced",
        )
        r = event(
            reg_laptop,
            E.returned_to_unit,
            ago(17),
            S.assigned,
            "REG",
            complaint_id=t.id,
            counterparty_name="Adebayo Ogunleye",
        )
        ack(r, "REG", AckStatus.confirmed, ago(16))
        note(
            t,
            "Assigned to Emeka Okafor. Status: open -> in_progress. Device received for repair.",
            ago(20),
        )
        note(t, "Status: in_progress -> resolved. Device returned to the unit.", ago(17))
        note(
            t,
            "Status: resolved -> closed. Return confirmed by the unit.",
            ago(16),
            author=reps["REG"],
        )
        note(t, "Works perfectly now, thank you.", ago(16, 1), author=reps["REG"], system=False)

        # 2. ENR desktop: returned 8 days ago, the unit has not answered (overdue).
        t = ticket(
            "ENR",
            "Desktop keeps restarting",
            "Restarts by itself several times a day.",
            ago(14),
            C.resolved,
            enr_desktop,
            PriorityLevel.medium,
            assigned_to=ibrahim.id,
            resolved_at=ago(8),
        )
        i = event(
            enr_desktop,
            E.received_for_repair,
            ago(12),
            S.received_for_repair,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
            counterparty_name="Chioma Nwosu",
        )
        ack(i, "ENR", AckStatus.confirmed, ago(12, -2))
        event(
            enr_desktop,
            E.diagnosed,
            ago(11),
            S.diagnosed,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
            diagnosis="Failing power supply",
        )
        event(
            enr_desktop,
            E.parts_requested,
            ago(10),
            S.awaiting_parts,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
            notes="Waiting for a 500W power supply",
        )
        event(
            enr_desktop,
            E.repair_started,
            ago(9),
            S.in_repair,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
        )
        event(
            enr_desktop,
            E.repair_completed,
            ago(8, 3),
            S.repaired,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
            notes="Power supply replaced, stress tested for 2 hours",
        )
        event(
            enr_desktop,
            E.returned_to_unit,
            ago(8),
            S.assigned,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
            counterparty_name="Chioma Nwosu",
        )
        note(
            t,
            "Assigned to Ibrahim Musa. Status: open -> in_progress. Device received for repair.",
            ago(12),
            author=ibrahim,
        )
        note(
            t,
            "Status: in_progress -> resolved. Device returned to the unit.",
            ago(8),
            author=ibrahim,
        )

        # 3. FIN printer: in repair right now.
        t = ticket(
            "FIN",
            "Printer jams on every page",
            "Paper jams on the second page of any job.",
            ago(6),
            C.in_progress,
            fin_printer,
            PriorityLevel.high,
            assigned_to=emeka.id,
        )
        i = event(
            fin_printer,
            E.received_for_repair,
            ago(5),
            S.received_for_repair,
            "FIN",
            complaint_id=t.id,
            counterparty_name="Folake Balogun",
        )
        ack(i, "FIN", AckStatus.confirmed, ago(5, -3))
        event(
            fin_printer,
            E.diagnosed,
            ago(4),
            S.diagnosed,
            "FIN",
            complaint_id=t.id,
            diagnosis="Worn pickup roller and misaligned tray",
        )
        event(fin_printer, E.repair_started, ago(3), S.in_repair, "FIN", complaint_id=t.id)
        note(
            t,
            "Assigned to Emeka Okafor. Status: open -> in_progress. Device received for repair.",
            ago(5),
        )

        # 4. REG printer: the unit disputed the return; it came back in again two days ago.
        t = ticket(
            "REG",
            "Printer produces blank pages",
            "Every page comes out blank.",
            ago(32),
            C.in_progress,
            reg_printer,
            PriorityLevel.medium,
            assigned_to=emeka.id,
        )
        i = event(
            reg_printer,
            E.received_for_repair,
            ago(30),
            S.received_for_repair,
            "REG",
            complaint_id=t.id,
            counterparty_name="Adebayo Ogunleye",
        )
        ack(i, "REG", AckStatus.confirmed, ago(30, -2))
        event(
            reg_printer,
            E.diagnosed,
            ago(29),
            S.diagnosed,
            "REG",
            complaint_id=t.id,
            diagnosis="Empty toner cartridge",
        )
        event(reg_printer, E.repair_started, ago(28), S.in_repair, "REG", complaint_id=t.id)
        event(
            reg_printer,
            E.repair_completed,
            ago(27, 4),
            S.repaired,
            "REG",
            complaint_id=t.id,
            notes="Toner replaced",
        )
        r = event(
            reg_printer,
            E.returned_to_unit,
            ago(27),
            S.assigned,
            "REG",
            complaint_id=t.id,
            counterparty_name="Adebayo Ogunleye",
        )
        ack(r, "REG", AckStatus.disputed, ago(26), "Prints, but pages come out streaked")
        event(
            reg_printer,
            E.note_added,
            ago(25),
            S.assigned,
            "REG",
            complaint_id=t.id,
            notes="Noted. Booking it back in to check the drum unit.",
            corrects_event_id=r.id,
        )
        event(
            reg_printer,
            E.received_for_repair,
            ago(2),
            S.received_for_repair,
            "REG",
            complaint_id=t.id,
            counterparty_name="Adebayo Ogunleye",
        )
        note(
            t,
            "Assigned to Emeka Okafor. Status: open -> in_progress. Device received for repair.",
            ago(30),
        )
        note(t, "Status: in_progress -> resolved. Device returned to the unit.", ago(27))
        note(
            t,
            "Status: resolved -> reopened. Return disputed by the unit.",
            ago(26),
            author=reps["REG"],
        )
        note(t, "Status: reopened -> in_progress. Device received for repair.", ago(2))
        # Its acknowledgement is deliberately still pending: 2 days, not yet overdue.

        # 5. ENR laptop: handed in yesterday, the unit has not confirmed yet.
        t = ticket(
            "ENR",
            "Laptop screen flickers",
            "The display flickers and goes dark.",
            ago(2),
            C.in_progress,
            enr_laptop,
            PriorityLevel.medium,
            assigned_to=ibrahim.id,
        )
        event(
            enr_laptop,
            E.received_for_repair,
            ago(1),
            S.received_for_repair,
            "ENR",
            actor=ibrahim,
            complaint_id=t.id,
            counterparty_name="Chioma Nwosu",
        )
        note(
            t,
            "Assigned to Ibrahim Musa. Status: open -> in_progress. Device received for repair.",
            ago(1),
            author=ibrahim,
        )

        # Open tickets that have not been picked up.
        ticket(
            "REG",
            "Wi-Fi keeps dropping",
            "The office Wi-Fi disconnects every few minutes.",
            ago(6),
            C.open,
            None,
            PriorityLevel.medium,
            ComplaintCategory.network,
        )
        ticket(
            "FIN",
            "Cannot sign in to the shared PC",
            "The shared accounts PC rejects the password.",
            ago(3),
            C.open,
            None,
            PriorityLevel.high,
            ComplaintCategory.software,
        )
        ticket(
            "ENR",
            "Scanner is not recognised",
            "The scanner is not detected by the enrolment PCs.",
            ago(1),
            C.open,
            enr_scanner,
            PriorityLevel.critical,
        )

        db.commit()

    print("Demo data loaded.\n")
    print(f"  Password for every demo user: {password}\n")
    for user_email, label in (
        ("head@demo.test", "Head of Engineering (admin)"),
        ("emeka@demo.test", "Engineer"),
        ("ibrahim@demo.test", "Engineer"),
        ("auditor@demo.test", "Auditor"),
        ("adebayo@demo.test", "Registration Office rep"),
        ("chioma@demo.test", "Enrolment Centre rep"),
        ("folake@demo.test", "Finance and Accounts rep"),
    ):
        print(f"  {user_email:<20} {label}")
    print("\nThe password is shown once; load the data again into a fresh database for a new one.")


if __name__ == "__main__":
    main()
