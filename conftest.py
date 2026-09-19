"""Disable .env loading before any application module is collected."""
from unittest.mock import patch


def pytest_configure(config):
    config._dotenv_patch = patch('dotenv.load_dotenv', return_value=False)
    config._dotenv_patch.start()


def pytest_unconfigure(config):
    config._dotenv_patch.stop()
