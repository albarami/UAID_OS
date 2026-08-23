"""Ecosystem catalog (Slice 61a/61b) plus Slice 62 cost learning.

This package records declared connectors, agent-blueprint versions, and
reference intakes. A listing is impossible without a passing vetting record of
the required kind bound to that exact asset row. The catalog is populated by
``populate_declared_catalog`` and is empty until that runs. Slice 61b still
does not close the roadmap Slice 61 exit. D-8, D-9, and D-10 stay OPEN.

Slice 62 adds a tenant-safe cross-project learning publisher and a
decision-only cost-optimizer tier recommendation. A freshly migrated database
has no published aggregates until ``make learning-publish``. This does not
meet the Slice 61 exit and does not authorize go-live.

The database cannot attribute a payload to the code that produced it.
Provenance labels are app-stamped.
"""
