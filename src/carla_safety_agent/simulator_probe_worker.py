"""Disposable read-only CARLA RPC probe. No world, actor or tick operations."""
import json
import sys


def main() -> None:
    import carla
    client = carla.Client(sys.argv[1], int(sys.argv[2]))
    client.set_timeout(1.0)
    version = client.get_server_version()
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError('CARLA server version was empty')
    print(json.dumps({'ok': True, 'version': version}))


if __name__ == '__main__':
    main()
