"""Mocks for unit testing interactions"""

class MockMessage:
    """Mock for the response message"""
    def __init__(self, content="", mention_everyone=False):
        self.content = content
        self.mention_everyone = mention_everyone
        self.reactions = []
        self.responses = []
        self.response_files = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def reply(self, message, file=None):
        self.responses.append(message)
        self.response_files.append(file)

    def assert_reply_message_equals(self, message):
        if message is None:
            assert not self.responses
        else:
            assert message in self.responses

    def assert_reply_file_equals(self, file):
        if file is None:
            assert not self.response_files
        else:
            assert len(list(
                filter(lambda x: x is not None and \
                        x.filename == file.filename and \
                        x.fp.read() == file.fp.read(),
                       self.response_files))) > 0

class MockChannel:
    """Mock for a Discord text channel"""
    def __init__(self, name):
        self.name = name
        self.mention = f'<@!{name}>'
        self.message = None
        self.embed = None
        self.file = None

    async def send(self, message, embed=None, file=None):
        self.message = message
        self.embed = embed
        self.file = file

    def assert_message_equals(self, message):
        print(message)
        print(self.message)
        assert self.message == message

    def assert_embed_equals(self, embed):
        if embed is None:
            assert self.embed is None
        else:
            assert self.embed.title == embed.title and \
                self.embed.type == embed.type and \
                self.embed.image.url == embed.image.url and \
                self.embed.color == embed.color and \
                self.embed.fields[0].value == embed.fields[0].value

    def assert_file_equals(self, file):
        assert file is None and self.file is None or \
            self.file.fp.read() == file.fp.read() and \
            self.file.filename == file.filename

class MockRole:
    """Mock for a Discord role"""
    def __init__(self, name):
        self.name = name

class MockGuild:
    """Mock for the HallyU guild"""
    def __init__(self):
        self.text_channels = [
            MockChannel("welcome"),
            MockChannel("roles"),
            MockChannel("rules"),
            MockChannel("introductions"),
        ]
        self.roles = [
            MockRole("Trainee")
        ]

class MockResponder:
    """Mock for a discord.InteractionResponse"""
    def __init__(self):
        self.message = None
        self.ephemeral = False
        self.embed = None
        self.file = None
        self.bot_response = None

    async def send_message(self, message, embed=None, file=None, ephemeral=False):
        self.message = message
        self.embed = embed
        self.ephemeral = ephemeral
        self.file = file
        self.bot_response = MockMessage()

class MockUser(): # pylint: disable=too-many-instance-attributes
    """Mock for a discord.User"""
    def __init__(self, user_id = "", name = "", nick = "", display_name = "", global_name = ""):
        self.direct_message = ""
        self.mention = name
        self.id = user_id  # pylint: disable=invalid-name
        self.nick = nick
        self.display_name = display_name
        self.global_name = global_name
        self.guild = MockGuild()
        self.roles = []

    async def send(self, message):
        self.direct_message = message

    async def add_roles(self, role):
        self.roles = self.roles + list(filter(lambda x: x.name == role.name, self.guild.roles))

    def assert_dm_equals(self, message):
        assert self.direct_message == message

    def assert_has_role(self, role):
        print(self.roles)
        assert len(list(filter(lambda x: x.name == role, self.roles))) > 0

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
            assert self.response.embed.title == embed.title and \
                self.response.embed.type == embed.type and \
                self.response.embed.image.url == embed.image.url and \
                self.response.embed.color == embed.color and \
                self.response.embed.fields[0].value == embed.fields[0].value

    def assert_file_equals(self, file):
        assert file is None and self.response.file is None or \
            self.response.file.fp.read() == file.fp.read() and \
            self.response.file.filename == file.filename
