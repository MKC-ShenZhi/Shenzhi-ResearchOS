"""Retired auto-assignment entry point; only Admin may assign entitlements.

Kept as a no-op for old registration clients. It never writes an assignment,
including when invoked as the legacy backfill command.
"""
async def initialize_free(db, user_id=None):
    return 0


if __name__ == '__main__':
    raise SystemExit('Automatic Free initialization is retired. Use Admin migration preview and assignment.')
