"""Mocks for unit testing interactions"""

class MockMessage:
    """Mock for the response message"""
    def __init__(self):
        self.reactions = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

class MockResponder:
    """Mock for a discord.InteractionResponse"""
    def __init__(self):
        self.message = None
        self.embed = None
        self.file = None
        self.bot_response = None

    async def send_message(self, message, embed=None, file=None, ephemeral=False):
        self.message = message
        self.embed = embed
        self.ephemeral = ephemeral
        self.file = file
        self.bot_response = MockMessage()

class MockUser():
    """Mock for a discord.User"""
    def __init__(self, id = "", name = "", nick = "", display_name = "", global_name = ""):
        self.dm = ""
        self.mention = name
        self.id = id
        self.nick = nick
        self.display_name = display_name
        self.global_name = global_name

    async def send(self, message):
        self.dm = message

    def assert_dm_equals(self, message):
        assert self.dm == message

class MockInteraction():
    """Mock for a discord.Interaction"""
    def __init__(self, user=None):
        self.response = MockResponder()
        if user:
            self.user = user

    async def original_response(self):
        return self.response.bot_response

    def assert_message_equals(self, message, ephemeral=False):
        assert self.response.message == message and self.response.ephemeral == ephemeral

    def assert_embed_equals(self, embed):
        if embed is None:
            assert self.response.embed is None
        else:
            assert self.response.embed.title == embed.title and self.response.embed.type == embed.type and self.response.embed.image.url == embed.image.url and self.response.embed.color == embed.color and self.response.embed.fields[0].value == embed.fields[0].value

    def assert_file_equals(self, file):
        assert (file is None and self.response.file is None) or self.response.file.fp.read() == file.fp.read() and \
            self.response.file.filename == file.filename
