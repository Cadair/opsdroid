"""Utilities for use when testing."""
import pytest

from contextlib import asynccontextmanager
import asyncio
import aiohttp
from aiohttp import web
import json
from typing import Any, Awaitable, List, Dict

from opsdroid.core import OpsDroid

MINIMAL_CONFIG = {
    "connectors": {
        "mock": {"module": "opsdroid.testing.mockmodules.connectors.mocked"}
    },
    "skills": {"hello": {"module": "opsdroid.testing.mockmodules.skills.hello"}},
}


class ExternalAPIMockServer:
    """A webserver which can pretend to be an external API.

    The general idea with this class is to allow you to push expected responses onto
    a stack for each API call you expect your test to make. Then as your tests make those
    calls each response is popped from the stack.

    You can then assert that routes were called and that data and headers were sent correctly.

    Your test will need to switch the URL of the API calls, so the thing you are testing should be
    configurable at runtime. You will also need to capture the responses from the real API your are
    mocking and store them as JSON files. Then you can push those responses onto the stack at the start
    of your test.

    Examples:
        A simple example of pushing a response onto a stack and making a request::

            import pytest
            import aiohttp

            from opsdroid.testing import ExternalAPIMockServer

            @pytest.mark.asyncio
            async def test_example():
                # Construct the mock API server and push on a test method
                mock_api = ExternalAPIMockServer()
                mock_api.add_response("/test", "GET", None, 200)

                async with mock_api:
                    # Make an HTTP request to our mock_api
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{mock_api.base_url}/test") as resp:

                            # Assert that it gives the expected responses
                            assert resp.status == 200
                assert mock_api.called("/test")

    """

    def __init__(self):
        """Initialize a server."""
        self.app = None
        self.runner = None
        self._initialize_web_app()

        self.site = None
        self.host = "localhost"
        self.port = 8089
        self._calls = {}
        self.responses = {}
        self._payloads = {}
        self.status = "stopped"

    def _initialize_web_app(self) -> None:
        self.app = web.Application()
        self.runner = web.AppRunner(self.app)

    async def _start(self) -> None:
        """Start the server."""
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host=self.host, port=self.port)
        await self.site.start()
        self.status = "running"

    async def _stop(self) -> None:
        """Stop the web server."""
        await self.runner.cleanup()
        self.site = None
        self.status = "stopped"

    async def _handler(self, request: web.Request) -> web.Response:
        route = request.path
        if route in self._calls:
            self._calls[route].append(request)
        else:
            self._calls[route] = [request]
        if route in self._payloads:
            self._payloads[route].append(await request.post())
        else:
            self._payloads[route] = [await request.post()]
        status, response = self.responses[route].pop(0)
        return web.json_response(response, status=status)

    @property
    def base_url(self) -> str:
        """Return the base url of the web server."""
        return f"http://{self.host}:{self.port}"

    def add_response(
        self, route: str, method: str, response_path: str, status: int = 200
    ) -> None:
        """Push a mocked response onto a route."""
        if response_path is not None:
            with open(response_path) as json_file:
                response = json.load(json_file)
        else:
            response = None

        if route in self.responses:
            self.responses[route].append((status, response))
        else:

            if method.upper() == "GET":
                routes = [web.get(route, self._handler)]
            elif method.upper() == "POST":
                routes = [web.post(route, self._handler)]
            else:
                raise TypeError(f"Unsupported method {method}")

            self.responses[route] = [(status, response)]
            self.app.add_routes(routes)

    async def __aenter__(self):
        if self.status == "stopped":
            await self._start()
        while self.status != "running":
            await asyncio.sleep(0.1)

    async def __aexit__(self, exc_type, exc, tb):
        await self._stop()

    def reset(self) -> None:
        """Reset the mock back to a clean state."""
        if self.status == "stopped":
            self._initialize_web_app()
            self._calls = {}
            self.responses = {}
        else:
            raise RuntimeError("Web server must be stopped before it can be reset.")

    def called(self, route: str) -> bool:
        """Route has been called.

        Args:
            route: The API route that we want to know if was called.

        Returns:
            Wether or not it was called.

        """
        return route in self._calls

    def call_count(self, route: str) -> int:
        """Route has been called n times.

        Args:
            route: The API route that we want to know if was called.

        Returns:
            The number of times it was called.

        """
        return len(self._calls[route])

    def get_request(self, route: str, idx: int = 0) -> web.Request:
        """Route has been called n times.

        Args:
            route: The API route that we want to get the request for.
            idx: The index of the call. Useful if it was called multiple times and we want something other than the first one.

        Returns:
            The request that was made.

        """
        return self._calls[route][idx]

    def get_payload(self, route: str, idx: int = 0) -> Dict:
        """Return data payload that the route was called with.

        Args:
            route: The API route that we want to get the payload for.
            idx: The index of the call. Useful if it was called multiple times and we want something other than the first one.

        Returns:
            The data payload which was sent in the POST request.

        """
        return self._payloads[route][idx]

@asynccontextmanager
async def running_opsdroid(opsdroid: OpsDroid):
    """Run a unit test function against opsdroid.

    This method should be used when testing on a loaded but stopped instance of opsdroid.
    The instance will be started when the context manager is entered.
    When the context manager exits opsdroid will be stopped and unloaded.

    Args:
        opsdroid: A loaded but stopped instance of opsdroid.

    Examples:
        An example of running a coroutine test against opsdroid::

            import pytest
            from opsdroid.testing import (
                opsdroid,
                run_unit_test,
                MINIMAL_CONFIG
                )

            @pytest.mark.asyncio
            async def test_example(opsdroid):
                # Using the opsdrid fixture we load it with the
                # minimal example config
                await opsdroid.load(config=MINIMAL_CONFIG)

                # Check that opsdroid is not currently running
                assert not opsdroid.is_running()

                async with running_opsdroid(opsdroid):
                    assert opsdroid.is_running()

    """
    await opsdroid.start()
    yield
    await opsdroid.stop()


async def call_endpoint(
    opsdroid: OpsDroid,
    endpoint: str,
    method: str = "GET",
    data_path: str = None,
    data: Dict = None,
) -> web.Response:
    """Call an opsdroid API endpoint with the provided data.

    This method should be used when testing on a running instance of opsdroid.
    The endpoint will be appended to the base url of the running opsdroid, so you do not
    need to know the address of the running opsdroid. An HTTP request will be made with
    the provided method and data or data_path for methods that support it.

    For methods like ``"POST"`` either ``data`` or ``data_path`` should be set.

    Args:
        opsdroid: A running instance of opsdroid.
        endpoint: The API route to call.
        method: The HTTP method to use when calling.
        data_path: A local file path to load a JSON payload from to be sent in supported methods.
        data: A dictionary payload to be sent in supported methods.

    Returns:
        The response from the HTTP request.

    Examples:
        Call the ``/stats`` endpoint of opsdroid without having to know what address opsdroid
        is serving at::

            import pytest
            from opsdroid.testing import (
                opsdroid,
                call_endpoint,
                run_unit_test,
                MINIMAL_CONFIG
                )

            @pytest.mark.asyncio
            async def test_example(opsdroid):
                # Using the opsdrid fixture we load it with the
                # minimal example config
                await opsdroid.load(config=MINIMAL_CONFIG)

                async def test():
                    # Call our endpoint by just passing
                    # opsdroid, the endpoint and the method
                    resp = await call_endpoint(opsdroid, "/stats", "GET")

                    # Make assertions that opsdroid responded successfully
                    assert resp.status == 200
                    return True

                assert await run_unit_test(opsdroid, test)

    """
    if data_path:
        with open(data_path) as json_file:
            data = json.load(json_file)
    async with aiohttp.ClientSession() as session:
        if method.upper() == "GET":
            async with session.get(f"{opsdroid.web_server.base_url}{endpoint}") as resp:
                return resp
        elif method.upper() == "POST":
            if data_path is None and data is None:
                raise RuntimeError("Either data or data_path must be set")
            async with session.post(
                f"{opsdroid.web_server.base_url}{endpoint}", data=data
            ) as resp:
                return resp
        else:
            raise TypeError(f"Unsupported method {method}")


@pytest.fixture
def opsdroid() -> OpsDroid:
    """Fixture with a plain instance of opsdroid.

    Will yield an instance of :class:`opsdroid.core.OpsDroid` which hasn't been loaded.

    """
    with OpsDroid(config={}) as opsdroid:
        yield opsdroid


@pytest.fixture
async def mock_api() -> ExternalAPIMockServer:
    """Fixture for making a mock API server.

    Will give an instance of :class:`opsdroid.testing.ExternalAPIMockServer`.

    """
    return ExternalAPIMockServer()
