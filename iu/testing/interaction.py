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

    async def send_message(self, message, embed=None, file=None):
        self.message = message
        self.embed = embed
        self.file = file
        self.bot_response = MockMessage()

class MockUser():
    """Mock for a discord.User"""
    def __init__(self, name):
        self.mention = name

class MockInteraction():
    """Mock for a discord.Interaction"""
    def __init__(self, username=""):
        self.response = MockResponder()
        self.user = MockUser(username)

    async def original_response(self):
        return self.response.bot_response

    def assert_message_equals(self, message):
        assert self.response.message == message

    def assert_embed_equals(self, embed):
        assert self.response.embed == embed

    def assert_file_equals(self, file):
        assert self.response.file.fp.read() == file.fp.read() and \
            self.response.file.filename == file.filename
