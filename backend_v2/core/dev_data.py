"""Explicit development-data steps shared by the management commands."""

from dataclasses import dataclass
from typing import Callable

from accounts.dev_data import clear_users, seed_users
from accounts.models import User

StepFunction = Callable[[User, bool], int]


@dataclass(frozen=True)
class DevDataStep:
    key: str
    seed: StepFunction
    clear: StepFunction
    reset_count: int = 0


# Demo records and test users only: a default row is written by its app's data migration
# and put back by `restore_defaults` (specs/CONFIGURATION.md §10). Later units extend
# development data by importing their functions and adding a line.
STEPS = (DevDataStep("users", seed_users, clear_users, reset_count=4),)
