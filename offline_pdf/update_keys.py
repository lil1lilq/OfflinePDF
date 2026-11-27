"""Trusted OfflinePDF release signing keys, as hex-encoded raw Ed25519 public keys."""

# Before the first signed release, add the public key printed by sign_update.
# Leaving this tuple empty permits version checks and manual downloads only.
TRUSTED_PUBLIC_KEYS: tuple[str, ...] = ()
