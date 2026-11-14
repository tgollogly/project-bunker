"""Air-gap bundle manifest format."""

BUNDLE_FORMAT_VERSION = 2
SUPPORTED_BUNDLE_VERSIONS = {2}

# Paths that may exist in a bundle but are not listed in manifest.files
MANIFEST_SIDECAR_NAMES = frozenset({"manifest.json"})