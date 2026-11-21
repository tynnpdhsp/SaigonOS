# SPDX-License-Identifier: Apache-2.0
import base64
import binascii
import json
import socketserver
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SMTP_PORT = 2587
CONTROL_PORT = 8025
DEFAULT_REPLIES = {
    "greeting": "220 smtp-gia ESMTP",
    "starttls": "220 2.0.0 Ready to start TLS",
    "auth": "235 2.7.0 Accepted",
    "mail": "250 2.1.0 OK",
    "rcpt": "250 2.1.5 OK",
    "data": "354 Go ahead",
    "content": "250 2.0.0 OK queued",
    "quit": "221 2.0.0 Bye",
}


class Dropped(Exception):
    pass


class Mailbox:
    def __init__(self, username, password, context=None, implicit_tls=False):
        self.username = username
        self.password = password
        self.context = context
        self.implicit_tls = implicit_tls
        self.lock = threading.Lock()
        self.plan = []
        self.sessions = []

    def start(self):
        with self.lock:
            step = self.plan.pop(0) if self.plan else {}
            session = {"commands": [], "tls": False, "user": None, "content": None}
            session |= {"started": time.time(), "at": None}
            self.sessions.append(session)
        return step, session

    def reset(self, plan):
        with self.lock:
            self.plan, self.sessions = list(plan), []

    def dump(self):
        with self.lock:
            return json.dumps(self.sessions)


class Handler(socketserver.StreamRequestHandler):
    timeout = 60

    def handle(self):
        mailbox = self.server.mailbox
        self.step, self.session = mailbox.start()
        try:
            if mailbox.implicit_tls:
                self.secure()
            self.answer("greeting")
            self.converse(mailbox)
        except (Dropped, OSError, ValueError):
            pass

    def secure(self):
        self.connection = self.server.mailbox.context.wrap_socket(self.connection, server_side=True)
        self.rfile = self.connection.makefile("rb")
        self.session["tls"] = True

    def write(self, reply):
        self.connection.sendall(reply.encode("ascii") + b"\r\n")

    def answer(self, stage):
        reply = self.step.get(stage, DEFAULT_REPLIES[stage])
        if reply == "drop":
            raise Dropped
        self.write(reply)
        if reply.startswith("421"):
            raise Dropped
        return reply.startswith(("2", "3"))

    def converse(self, mailbox):
        while True:
            line = self.rfile.readline(4096)
            if not line:
                return
            command = line.decode("ascii").rstrip("\r\n")
            verb = command.split(" ", 1)[0].upper()
            head, colon, rest = command.partition(":")
            shown = head.upper() + colon + rest if verb in ("MAIL", "RCPT") else command
            shown = "AUTH" if verb == "AUTH" else verb + shown[len(verb) :]
            self.session["commands"].append([shown, self.tls])
            if verb in ("EHLO", "HELO"):
                self.hello(mailbox)
            elif verb == "STARTTLS" and self.offers_starttls(mailbox):
                if self.answer("starttls"):
                    self.secure()
            elif verb == "AUTH" and not self.step.get("no_auth"):
                self.authenticate(mailbox, command)
            elif verb == "MAIL":
                self.answer("mail")
            elif verb == "RCPT":
                self.answer("rcpt")
            elif verb == "DATA":
                if self.answer("data"):
                    self.receive()
            elif verb in ("RSET", "NOOP"):
                self.write("250 2.0.0 OK")
            elif verb == "QUIT":
                self.answer("quit")
                return
            else:
                self.write("502 5.5.2 Command not recognized")

    @property
    def tls(self):
        return self.session["tls"]

    def offers_starttls(self, mailbox):
        return mailbox.context is not None and not self.tls and not self.step.get("no_starttls")

    def hello(self, mailbox):
        lines = ["smtp-gia", "8BITMIME"]
        if self.offers_starttls(mailbox):
            lines.append("STARTTLS")
        if not self.step.get("no_auth"):
            lines.append(self.step.get("auth_line", "AUTH PLAIN"))
        lines.append("SIZE 10485760")
        replies = [f"250-{line}" for line in lines[:-1]] + [f"250 {lines[-1]}"]
        self.write("\r\n".join(replies))

    def authenticate(self, mailbox, command):
        parts = command.split(" ")
        try:
            plain = base64.b64decode(parts[2], validate=True) if len(parts) == 3 else b""
        except binascii.Error:
            plain = b""
        fields = plain.split(b"\0")
        if parts[1:2] != ["PLAIN"] or len(fields) != 3:
            self.write("501 5.5.4 Syntax error")
            return
        user, password = fields[1].decode(), fields[2].decode()
        if (user, password) != (mailbox.username, mailbox.password):
            self.write("535 5.7.8 Username and Password not accepted")
            return
        if self.answer("auth"):
            self.session["user"] = user

    def receive(self):
        lines = []
        while True:
            line = self.rfile.readline(4096)
            if not line:
                raise Dropped
            if line == b".\r\n":
                break
            lines.append(line[1:] if line.startswith(b"..") else line)
        self.session["content"] = b"".join(lines).decode("ascii")
        self.session["at"] = time.time()
        time.sleep(self.step.get("delay", 0))
        self.answer("content")


def make_certificates(folder, name):
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    def usage(**allowed):
        names = ["digital_signature", "content_commitment", "key_encipherment"]
        names += ["data_encipherment", "key_agreement", "key_cert_sign", "crl_sign"]
        names += ["encipher_only", "decipher_only"]
        return x509.KeyUsage(**{name: allowed.get(name, False) for name in names})

    def certificate(subject, key, issuer, issuer_key, extensions):
        now = datetime.now(UTC)
        builder = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
        builder = builder.public_key(key.public_key()).serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(now - timedelta(minutes=5))
        builder = builder.not_valid_after(now + timedelta(days=1))
        identifier = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
        authority = x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key())
        for extension, critical in [*extensions, (identifier, False), (authority, False)]:
            builder = builder.add_extension(extension, critical=critical)
        return builder.sign(issuer_key, hashes.SHA256())

    ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA thu cua SaigonOS")])
    ca = certificate(
        ca_name,
        ca_key,
        ca_name,
        ca_key,
        [
            (x509.BasicConstraints(ca=True, path_length=None), True),
            (usage(key_cert_sign=True, crl_sign=True), True),
        ],
    )
    leaf = certificate(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]),
        key,
        ca_name,
        ca_key,
        [
            (x509.SubjectAlternativeName([x509.DNSName(name)]), False),
            (x509.BasicConstraints(ca=False, path_length=None), True),
            (usage(digital_signature=True), True),
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False),
        ],
    )
    paths = [folder / file for file in ("ca.pem", "cert.pem", "key.pem")]
    paths[0].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    paths[2].write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    for path in paths:
        path.chmod(0o644)
    return paths


def serve(mailbox, host="127.0.0.1", port=0):
    server = socketserver.ThreadingTCPServer((host, port), Handler)
    server.daemon_threads = True
    server.mailbox = mailbox
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    return server


class Control(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path != "/sessions":
            self.reply(404, b"[]")
            return
        self.reply(200, self.server.mailbox.dump().encode())

    def do_POST(self):
        content = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/plan":
            self.reply(404, b"[]")
            return
        self.server.mailbox.reset(json.loads(content))
        self.reply(200, b"[]")

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main(username, password, certificate, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    mailbox = Mailbox(username, password, context)
    serve(mailbox, "", SMTP_PORT)
    control = ThreadingHTTPServer(("", CONTROL_PORT), Control)
    control.mailbox = mailbox
    control.serve_forever()


if __name__ == "__main__":
    main(*sys.argv[1:])
