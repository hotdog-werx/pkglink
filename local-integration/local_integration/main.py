from pydantic import BaseModel

from .version import __version__


class InfoModel(BaseModel):
    """Model for package information."""

    name: str
    version: str


def main() -> None:
    """Main function to display package information."""
    info = InfoModel(name='PKG Link Integration Package', version=__version__)
    print(info.model_dump_json())  # noqa: T201 - this is a testing module
