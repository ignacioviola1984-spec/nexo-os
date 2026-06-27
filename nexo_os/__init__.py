"""Nexo Operating Model v2 — deterministic, human-in-the-loop co-pilot for a single
insurance brokerage.

Three non-negotiables drive every module:
  1. Every number is computed deterministically in `nexo_os.core` and is traceable to
     its inputs. The language model never produces, estimates, or rounds a figure.
  2. Human-in-the-loop at every action: agents propose, a person approves.
  3. It fails closed: missing data / failed check / low confidence -> flag and stop.
"""

__version__ = "2.0.0"
