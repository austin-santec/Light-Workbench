"""Concrete file and report adapters used at the application boundary.

Submodules are intentionally not imported eagerly. Some compatibility
facades depend on schema helpers, so eager adapter imports would create cycles
while those legacy modules are being migrated.
"""
