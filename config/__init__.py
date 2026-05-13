"""Centralized configuration for the cinema pipeline.

Modules should import the singleton via:

    from config.settings import settings

instead of calling `os.environ` or `load_dotenv` directly.
"""

from config.settings import settings

__all__ = ["settings"]
