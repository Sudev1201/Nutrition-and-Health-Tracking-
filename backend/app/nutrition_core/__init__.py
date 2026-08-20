"""The scientific core: energy, targets, condition rules and compensation.

Pure functions over plain data structures — no database, no HTTP. That is what
makes the science testable in isolation and is why the golden cases in
`tests/test_energy.py` can assert directly against ICMR-NIN's published figures.
"""
