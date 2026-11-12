"""N-antibot: block bot networks and scraper user agents at your web server (Caddy, nginx) without accounts or keys."""

__version__ = "0.4.0"

from .config import Config, ConfigError, load
from .core import generate
from .ranges import FetchError

__all__ = ["Config", "ConfigError", "FetchError", "__version__", "generate", "load"]
