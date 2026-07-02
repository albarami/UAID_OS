"""Maker-checker-verifier review layer (Slice 42, §13.1-13.3/§27.2/§12.3) — pure modules.

``task_contracts`` holds the §27.2 contract shape validators; ``workflow`` holds the
§12.3-subset lifecycle, the §13.3 verdict validators, and the per-registration done-gate
decision. Storage lives in ``app.models.task_contract``/``app.models.review_report``; the
DB orchestrators are ``app.repositories.task_contracts``/``app.repositories.review_reports``.
"""
