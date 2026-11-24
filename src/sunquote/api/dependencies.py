"""The collaborators the API needs, passed to the app factory so tests can inject fakes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AppDependencies:
    """Ports (geocoder, yield provider, repository, ...) are added here as they are built."""
