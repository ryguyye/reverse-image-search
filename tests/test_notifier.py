import httpx
import respx

from selfwatch.notifier import send_webhook


@respx.mock
async def test_send_webhook_returns_ok():
    route = respx.post("https://hook.example/x").mock(return_value=httpx.Response(200))
    status = await send_webhook("https://hook.example/x", {"hello": "world"})
    assert status == "ok"
    assert route.called
    assert route.calls.last.request.headers["content-type"].startswith("application/json")


@respx.mock
async def test_send_webhook_returns_error_on_http_failure():
    respx.post("https://hook.example/x").mock(return_value=httpx.Response(500))
    status = await send_webhook("https://hook.example/x", {"hello": "world"})
    assert status.startswith("error:")


@respx.mock
async def test_send_webhook_returns_error_on_network():
    respx.post("https://hook.example/x").mock(side_effect=httpx.ConnectError("boom"))
    status = await send_webhook("https://hook.example/x", {"hello": "world"})
    assert status.startswith("error:")
