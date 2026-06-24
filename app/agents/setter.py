"""DEPRECATED — removed in the KORE IA spec alignment.

There is no "Setter" agent in the KORE IA spec. Qualification (classification)
and closing are separate concerns: the Qualification Agent classifies
temperature, and CLOSING is a human responsibility reached via escalation (P3).
Booking/cierre is never done autonomously by an agent.

This module intentionally registers nothing. Kept only to avoid breaking stale
imports during the transition; safe to delete.
"""
