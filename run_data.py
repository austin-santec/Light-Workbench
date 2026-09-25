"""Compatibility facade for run models and CSV loading."""

from domain.models import MeasurementRecord
from domain.run_data import RunData
from infrastructure.csv_run_loader import load_run_csv

__all__ = ["MeasurementRecord", "RunData", "load_run_csv"]
