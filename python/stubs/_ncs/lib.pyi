import socket


__all__ = ('decrypt', 'stream_connect')


def decrypt(ciphertext: str) -> str:
    ...


def stream_connect(sock: socket.socket, id: int, flags: int, ip: str, port: int) -> None:
    ...
