"""Backward compatibility shim for the removed mise.toml loader."""

from __future__ import annotations

from pkglink.batch_config import PkglinkConfigError  # re-export for API compatibility


def load_batch_contexts(*_args, **_kwargs):  # pragma: no cover - compatibility shim
    """Raise an informative error for the removed mise.toml loader."""

    msg = (
        'The mise.toml-based loader has been removed. '
        'Please migrate to pkglink.config.yaml and pkglink.batch_config.load_batch_contexts.'
    )
    raise PkglinkConfigError(msg)


__all__ = ['PkglinkConfigError', 'load_batch_contexts']