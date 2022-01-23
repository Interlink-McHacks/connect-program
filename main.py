#!/usr/bin/env python3

# Thanks to https://github.com/jimparis/unwebsockify

desc = """\
Unwebsockify is a TCP to WebSocket proxy/bridge.  It accepts a
plain TCP connection and connects to a WebSocket server, effectively
adding WS support to a client that does not natively support it.  It
is essentially the opposite of "websockify".
Note that this only handles simple byte streams of data, with no
support for conveying WebSockets message framing back to the client.
In most cases, specifying the WebSockets subprotocol is necessary.
For example, Eclipse Mosquitto supports WebSockets on the server side,
but not on the client side (for bridging).  To connect one instance
to another, run
  {prog} --port 13232 --subproto mqtt wss://server/
and configure the client with e.g.
  address 127.0.0.1:13232
"""

import sys

import asyncio
import websockets
import requests


class Proxy:
    def __init__(self, port, addr, url):
        self.port = port
        self.addr = addr
        self.url = url

    async def copy(self, reader, writer):
        while True:
            data = await reader()
            if data == b'':
                break
            future = writer(data)
            if future:
                await future

    async def handle_client(self, r, w):
        peer = w.get_extra_info("peername")
        #print(f'{peer} connected')
        loop = asyncio.get_event_loop()
        try:
            async with websockets.connect(
                    self.url) as ws:
                #print(f'{peer} connected to {self.url}')
                def r_reader():
                    return r.read(65536)
                tcp_to_ws = loop.create_task(self.copy(r_reader, ws.send))
                ws_to_tcp = loop.create_task(self.copy(ws.recv, w.write))
                done, pending = await asyncio.wait([tcp_to_ws, ws_to_tcp],
                                                   return_when=asyncio.FIRST_COMPLETED)
                for x in done:
                    try:
                        await x
                    except:
                        pass
                for x in pending:
                    x.cancel()
        except Exception as e:
            print(f'{peer} exception:', e)
        w.close()
        print(f'{peer} closed')

    async def start(self):
        await asyncio.start_server(self.handle_client, self.addr, self.port)
        print(f'Listening on {self.addr} port {self.port}')


def main(argv):
    import argparse
    import textwrap

    parser = argparse.ArgumentParser(
        prog=argv[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.indent(desc.format(prog=argv[0]), prefix="    "))

    parser.add_argument("--server", metavar="SERVER", default="http://localhost:3000",
                        help="Interlink server address")

    parser.add_argument("--email", metavar="EMAIl", help="Interlink account email")

    parser.add_argument("--password", metavar="PASSWORD", help="Interlink password")

    parser.add_argument("--listen", "-l", metavar="ADDR", default="0.0.0.0",
                        help="TCP listen address")

    parser.add_argument("--port", "-p", metavar="PORT", default=13232,
                        help="TCP listen port")

    parser.add_argument("tunnelID", metavar="TUNID", help="Tunnel ID")

    args = parser.parse_args()

    try:
        print("Welcome to Interlink. Logging to you in...")
        login_res = requests.post(args.server + "/api/login", json={
            "email": args.email,
            "password": args.password
        })

        login_token = login_res.json()["data"]["token"]

        print("Successfully logged in to Interlink. Requesting authorization for the tunnel.")

        try:
            request_connection = requests.post(args.server + "/api/tunnel/{}/connection".format(args.tunnelID), headers={
                'Authorization': 'Bearer ' + login_token
            })

            tunnel_url = args.server.replace("http", "ws") + "/relay?token=" + request_connection.json()["data"]["token"]

            print("Authorization received. Attempting to connect.")

            loop = asyncio.get_event_loop()
            proxy = Proxy(args.port, args.listen, tunnel_url)
            loop.run_until_complete(proxy.start())
            loop.run_forever()
        except requests.exceptions.HTTPError as err2:
            print("Error request connection from Interlink", err2)

    except requests.exceptions.HTTPError as err:
        print("Error logging in to Interlink", err)


if __name__ == "__main__":
    main(sys.argv)