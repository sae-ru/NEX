"""Transactional fixture connections with deterministic OS-handle release."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def connection(*args,**kwargs):
    db=sqlite3.connect(*args,**kwargs)
    try:
        with db:
            yield db
    finally:
        # Connection.__exit__ commits/rolls back; it does not close the DB.
        # Windows cannot remove or replace the fixture while it remains open.
        db.close()
