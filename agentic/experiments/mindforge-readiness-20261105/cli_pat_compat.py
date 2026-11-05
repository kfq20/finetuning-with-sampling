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
    install()
    from mindforge.cli import main
    main()
