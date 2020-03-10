import collections
import asynctest.mock as amock

import pytest
import slack

from opsdroid.connector.slack import ConnectorSlack
from opsdroid.cli.start import configure_lang


@pytest.fixture
def slackconnector(opsdroid, mocker):
    connector = ConnectorSlack({"token": "1234"}, opsdroid=opsdroid)
    connector.slack_rtm._connect_and_read = amock.CoroutineMock()
    connector.slack.api_call = amock.CoroutineMock()
    connector.opsdroid.web_server = amock.CoroutineMock()
    connector.opsdroid.web_server.web_app = amock.CoroutineMock()
    connector.opsdroid.web_server.web_app.router = amock.CoroutineMock()
    connector.opsdroid.web_server.web_app.router.add_post = amock.CoroutineMock()

    yield connector

    # Make sure we clean up the slack RTMClient as well
    slack.RTMClient._callbacks = collections.defaultdict(list)


@pytest.mark.asyncio
async def test_connect(slackconnector):
    await slackconnector.connect()
    assert slackconnector.slack_rtm._connect_and_read.called is True
    assert slackconnector.slack.api_call.called is True
    assert slackconnector.opsdroid.web_server.web_app.router.add_post.called is True


@pytest.mark.asyncio
async def test_connect_auth_fail(slackconnector, caplog):
    slackconnector.slack_rtm._connect_and_read.side_effect = slack.errors.SlackApiError(
        message="error", response="response"
    )

    await slackconnector.connect()
    assert "error" in caplog.text
    assert "response" in caplog.text
    assert caplog.records[-1].levelname == "ERROR"
