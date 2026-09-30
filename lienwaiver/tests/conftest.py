import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="lienwaiver-test-"))
os.environ["DATA_DIR"] = str(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["BASE_URL"] = "http://testserver"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "pw"
os.environ["AP_NOTIFY_EMAIL"] = "ap@test.example"

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.models import Project, Vendor  # noqa: E402
from app.services.email import ConsoleBackend  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    ConsoleBackend.sent.clear()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def sample(db):
    v = Vendor(name="Acme Stone LLC", address1="1 Quarry Rd", city="Columbus", zip="43215",
               contact_name="Pat", contact_email="pat@acme.example")
    p = Project(name="Riverside Flats", job_number="J1", address1="1200 Riverside Dr", city="Columbus", zip="43215",
                county="Franklin", owner_name="Owner LLC", gc_name="Big GC")
    bond = Project(name="Maple Court", job_number="J2", address1="88 Maple Ct", city="Dublin", zip="43017",
                   owner_name="Maple LP", gc_name="Scioto GC", bond_project=True, surety_name="Surety Co", bond_number="B-1")
    db.add_all([v, p, bond])
    db.commit()
    return {"vendor": v, "project": p, "bond": bond}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.post("/login", data={"username": "admin", "password": "pw", "next": "/"})
        yield c
