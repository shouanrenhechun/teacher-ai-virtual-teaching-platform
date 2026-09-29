"""All application tests use disposable databases and cannot make remote calls."""
import socket

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

from app.database import session as database


@pytest.fixture(autouse=True)
def isolated_application(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    previous = database.SessionLocal.kw.get("bind")
    def forbid_original_database(*args):
        raise AssertionError('Tests cannot use the original application database')
    event.listen(previous, 'checkout', forbid_original_database)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(database, "DATABASE_PATH", path)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    database.SessionLocal.configure(bind=engine)

    original_init = TestClient.__init__
    def init_client(self, *args, **kwargs):
        kwargs.setdefault("headers", {"X-Practice-Token": "a" * 64})
        original_init(self, *args, **kwargs)
    monkeypatch.setattr(TestClient, "__init__", init_client)

    original_connect = socket.socket.connect
    def no_network(sock, address):
        # Windows asyncio implements socketpair using loopback sockets.
        if isinstance(address, tuple) and address[0] in {'127.0.0.1', '::1', 'localhost'}:
            return original_connect(sock, address)
        raise AssertionError("Tests cannot open network connections; use a fake HTTP transport")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    original_getaddrinfo = socket.getaddrinfo
    def no_remote_dns(host, *args, **kwargs):
        if host not in {None, '127.0.0.1', '::1', 'localhost', b'127.0.0.1', b'::1', b'localhost'}:
            raise AssertionError('Tests cannot resolve remote hosts; use a fake HTTP transport')
        return original_getaddrinfo(host, *args, **kwargs)
    monkeypatch.setattr(socket, 'getaddrinfo', no_remote_dns)
    yield
    database.SessionLocal.configure(bind=previous)
    event.remove(previous, 'checkout', forbid_original_database)
    engine.dispose()
