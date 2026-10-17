import os


def get_adapter(kind=None):
    """Return the mock adapter or the real chain adapter.
    Controlled by ADAPTER=mock or ADAPTER=chain in the .env file."""
    kind = kind or os.getenv("ADAPTER", "mock")
    if kind == "chain":
        from adapters.chain import ChainAdapter
        return ChainAdapter()
    from adapters.mock import MockAdapter
    return MockAdapter()