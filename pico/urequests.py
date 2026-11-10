import usocket
import ussl

def post(url, data=None, headers=None):
    if headers is None:
        headers = {}

    # Very small URL parser (https only)
    assert url.startswith("https://")
    url2 = url[8:]
    host, path = url2.split("/", 1)
    path = "/" + path

    port = 443
    addr = usocket.getaddrinfo(host, port)[0][-1]
    s = usocket.socket()
    s.connect(addr)
    s = ussl.wrap_socket(s, server_hostname=host)

    body = data if data is not None else ""
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body

    req = (
        "POST {} HTTP/1.1\r\n"
        "Host: {}\r\n"
        "Connection: close\r\n"
        "Content-Length: {}\r\n"
    ).format(path, host, len(body_bytes))

    for k, v in headers.items():
        req += "{}: {}\r\n".format(k, v)
    req += "\r\n"

    s.write(req.encode("utf-8"))
    s.write(body_bytes)

    # read & discard response
    while True:
        chunk = s.read(512)
        if not chunk:
            break
    s.close()