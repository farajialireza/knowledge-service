"""Centralized logging configuration for the application and uvicorn."""
import logging.config


def configure_logging(level: str) -> None:
    """Install a single consistent console format for all loggers.

    Called during app startup (lifespan), i.e. after uvicorn has applied its
    own defaults, so this configuration wins for both app and server loggers.
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "root": {"handlers": ["console"], "level": level.upper()},
            "loggers": {
                # Re-route uvicorn's loggers through the same handler/format.
                "uvicorn": {"handlers": ["console"], "level": level.upper(), "propagate": False},
                "uvicorn.error": {"handlers": ["console"], "level": level.upper(), "propagate": False},
                "uvicorn.access": {"handlers": ["console"], "level": level.upper(), "propagate": False},
            },
        }
    )
