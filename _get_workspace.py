"""Quick script to get workspace slug from Modal credentials."""
from modal.client import _Client
from modal_proto import api_pb2
import asyncio

async def main():
    c = await _Client.from_credentials(
        'ak-NyRWsEinJ6Tts9Gepctjsn',
        'as-A2gwiOQwfhCVv4ByLHaIxX'
    )
    # Try to call ClientHello
    req = api_pb2.ClientHelloRequest()
    resp = await c.stub.ClientHello(req)
    print("Response fields:")
    for field in resp.DESCRIPTOR.fields:
        print(f"  {field.name} = {getattr(resp, field.name)}")

asyncio.run(main())
