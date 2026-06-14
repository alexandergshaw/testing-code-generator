"""Turn an in-memory file tree into a zip archive."""

from __future__ import annotations

import io
import zipfile


def to_zip(tree: dict[str, bytes]) -> io.BytesIO:
    """Pack ``{relative_path: bytes}`` into an in-memory ``.zip``.

    Paths are written verbatim, so callers are expected to have already rooted
    every entry under the project name (e.g. ``my-app/README.md``). The returned
    buffer is rewound to the start, ready for ``send_file``.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, data in sorted(tree.items()):
            # Normalise to forward slashes for cross-platform zip entries.
            arcname = path.replace("\\", "/")
            zf.writestr(arcname, data)
    buf.seek(0)
    return buf
