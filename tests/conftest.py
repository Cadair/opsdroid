import pytest

from opsdroid.core import OpsDroid
from opsdroid.cli.start import configure_lang  # noqa


@pytest.fixture
def opsdroid(event_loop):
    with OpsDroid() as od:
        od.event_loop = event_loop
        yield od
