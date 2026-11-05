"""Personal-token auth adapter for legacy MindForge CLI3e52e3f.

Keeps canonical CLI routing and server-side authentication. No credentials are
stored, no local-mode fallback, and no training/deployment submission here.
"""
from mindforge.cli.remote import RemoteMindForge


def install():
    original = RemoteMindForge._authenticate

    def authenticate(self):
        if self._token.startswith('mfpat_'):
            self._client.headers['Authorization'] = 'Bearer ' + self._token
            self._authenticated = True
        else:
            original(self)

    RemoteMindForge._authenticate = authenticate


if __name__ == '__main__':
    import sys
    import json
    install()
    # Explicit local read-only CLI extensions for documented production endpoints.
    discovery = {('train', 'models'): '/api/models',
                 ('train', 'clusters'): '/api/train/clusters/status'}
    route = discovery.get(tuple(sys.argv[1:]))
    if route:
        from mindforge.cli.remote import remote_client
        client = remote_client()
        if client is None:
            raise SystemExit('Authenticated remote mode required')
        print(json.dumps(client.get(route), ensure_ascii=False))
    else:
        from mindforge.cli import main
        main()
