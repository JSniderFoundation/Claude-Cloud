"""Load sample data for a demo: three projects (one bonded), five vendors, payments and waivers in every state.
Run: python -m scripts.seed   (wipes data/ first)"""
from __future__ import annotations

import shutil
from datetime import date, timedelta

from app.config import settings
from app.db import SessionLocal, engine, init_db
from app.auth import hash_password
from app.models import Base, Payment, Project, User, Vendor
from app.services import hold, waivers


def main() -> None:
    Base.metadata.drop_all(engine)
    shutil.rmtree(settings.pdf_dir, ignore_errors=True)
    init_db()
    db = SessionLocal()
    today = date.today()

    db.add(User(username="admin", name="AP Admin", password_hash=hash_password("admin")))
    projects = [
        Project(name="Riverside Flats", job_number="J-2401", address1="1200 Riverside Dr", city="Columbus", state="OH",
                zip="43215", county="Franklin", owner_name="Riverside Flats Owner LLC", gc_name="Buckeye Builders Inc."),
        Project(name="Maple Court Apartments", job_number="J-2407", address1="88 Maple Ct", city="Dublin", state="OH",
                zip="43017", county="Franklin", owner_name="Maple Court Partners LP", gc_name="Scioto Construction Co.",
                bond_project=True, surety_name="Liberty Mutual Insurance Company", bond_number="LM-0048812"),
        Project(name="Harbor View Lofts", job_number="J-2312", address1="45 Harbor View Rd", city="Cleveland", state="OH",
                zip="44113", county="Cuyahoga", owner_name="Harbor View Lofts LLC", gc_name="Lakefront GC", complete=True),
    ]
    vendors = [
        Vendor(name="Precision Stone Fabricators LLC", address1="410 Industrial Pkwy", city="Grove City", zip="43123",
               contact_name="Dana Ortiz", contact_email="dana@precisionstone.example"),
        Vendor(name="Ohio Cabinet Supply Co.", address1="2200 Commerce Dr", city="Hilliard", zip="43026",
               contact_name="Marcus Lee", contact_email="ap@ohiocabinet.example"),
        Vendor(name="Summit Installers Inc.", address1="77 Summit St", city="Akron", zip="44308",
               contact_name="Priya Nair", contact_email="priya@summitinstall.example", hold_mode="exchange"),
        Vendor(name="Northcoast Hardware Distributors", address1="900 Lakeside Ave", city="Cleveland", zip="44114",
               contact_name="Tom Becker", contact_email="tbecker@northcoasthw.example"),
        Vendor(name="Metro Countertop Delivery", address1="15 Freight Ln", city="Columbus", zip="43204",
               contact_name="", contact_email=""),
    ]
    db.add_all(projects + vendors)
    db.flush()
    rf, mc, hv = projects
    ps, oc, si, nh, md = vendors

    def pay(vendor, project, days_ago, amount, ref):
        p = Payment(vendor_id=vendor.id, project_id=project.id, payment_date=today - timedelta(days=days_ago),
                    amount_cents=int(round(amount * 100)), reference=ref)
        db.add(p)
        db.flush()
        return p

    # Waivers already received
    p1 = pay(ps, rf, 40, 18450.00, "ACH 100231")
    w1 = waivers.create_from_payment(db, p1, "progress", "seed")
    waivers.send(db, w1, "seed", today - timedelta(days=39))
    waivers.receive(db, w1, b"%PDF-1.4 sample signed copy", "portal", "seed")

    # Sent, still inside the window
    p2 = pay(oc, rf, 3, 42780.25, "ACH 100302")
    w2 = waivers.create_from_payment(db, p2, "progress", "seed")
    waivers.send(db, w2, "seed", today - timedelta(days=2))

    # Overdue -> vendor goes on hold (previous mode)
    p3 = pay(nh, mc, 20, 9120.00, "CHK 5521")
    w3 = waivers.create_from_payment(db, p3, "progress", "seed")
    waivers.send(db, w3, "seed", today - timedelta(days=19))

    # Exchange-mode vendor with a waiver out -> on hold immediately
    p4 = pay(si, mc, 5, 27300.00, "ACH 100310")
    w4 = waivers.create_from_payment(db, p4, "progress", "seed")
    waivers.send(db, w4, "seed", today - timedelta(days=4))

    # Draft
    p5 = pay(ps, mc, 2, 15600.00, "ACH 100318")
    w5 = waivers.create_from_payment(db, p5, "progress", "seed")
    waivers.regenerate_pdf(db, w5, "seed")

    # Queue: payments with no waiver yet, including a final on the complete project
    pay(oc, mc, 1, 31250.00, "ACH 100322")
    pay(ps, hv, 1, 6400.00, "ACH 100323")
    pay(md, rf, 0, 1850.00, "CHK 5530")
    pay(nh, rf, 0, 4975.50, "ACH 100325")

    db.commit()
    hold.apply_holds(db, today, user="seed")
    db.close()
    print("Seeded. Login admin / admin")


if __name__ == "__main__":
    main()
