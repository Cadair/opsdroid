from nio.responses import ErrorResponse
from nio.http import TransportResponse

from opsdroid.connector.matrix import MatrixException


def test_properties():
    er = ErrorResponse("message", "M_TEST")
    tr = TransportResponse()
    tr.status_code = 404
    er.transport_response = tr
    me = MatrixException(er)

    assert me.status_code == "M_TEST"
    assert me.message == "message"
    assert me.http_code == 404

    assert me.nio_error is er
