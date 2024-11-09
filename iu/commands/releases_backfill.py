from triggers.message import store_new_release

async def backfill_releases(channel):
    messages = [message async for message in channel.history(limit=200)]
    print(f'retrieved {len(messages)} messages')
    for msg in messages:
        store_new_release(msg)