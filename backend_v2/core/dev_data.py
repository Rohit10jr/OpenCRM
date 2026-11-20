"""Explicit development-data steps shared by the management commands."""

from dataclasses import dataclass
from typing import Callable

from accounts.dev_data import clear_users, seed_users
from accounts.models import User
from configuration.dev_data import (
    clear_default_layouts,
    clear_quick_filters,
    clear_standard_form_scripts,
    sync_standard_form_scripts,
    write_default_layouts,
    write_quick_filters,
)

StepFunction = Callable[[User, bool], int]


@dataclass(frozen=True)
class DevDataStep:
    key: str
    seed: StepFunction
    clear: StepFunction
    reset_count: int = 0


# Later units extend development data by importing their functions and adding a line.
STEPS = (
    DevDataStep("users", seed_users, clear_users, reset_count=4),
    DevDataStep("fields_layouts", write_default_layouts, clear_default_layouts),
    DevDataStep("quick_filters", write_quick_filters, clear_quick_filters),
    DevDataStep("form_scripts", sync_standard_form_scripts, clear_standard_form_scripts),
)
