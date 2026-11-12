# This file was generated with the assistance of an AI coding tool.
"""The server's own data in PostgreSQL (ADR 0029), beside the graph's store of ADR 0027.

``database`` holds the pool and the statements' three ways to run, ``schema`` the migrations run at startup, and
``cleanup`` the deletion of expired rows. The repositories are in ``opencde/store/<area>/postgres.py``. Statements are
literals with numbered parameters (``$1``); a value never becomes part of one.
"""
