import base64
from email import message_from_bytes

from core.providers.google.gmail import GmailClient


class FakeExecutable:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeMessages:
    def __init__(self):
        self.list_kwargs = None
        self.get_calls = []

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return FakeExecutable({"messages": [{"id": "m1"}, {"id": "m2"}]})

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        msg_id = kwargs["id"]
        return FakeExecutable({
            "id": msg_id,
            "snippet": f"snippet for {msg_id}",
            "payload": {
                "headers": [
                    {"name": "From", "value": f"sender-{msg_id}@example.com"},
                    {"name": "Subject", "value": f"Subject {msg_id}"},
                    {"name": "Date", "value": "Tue, 7 Jul 2026 10:00:00 -0400"},
                ]
            },
        })


class FakeDrafts:
    def __init__(self):
        self.create_kwargs = None

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return FakeExecutable({"id": "draft-99"})


class FakeUsers:
    def __init__(self, messages, drafts):
        self._messages = messages
        self._drafts = drafts

    def messages(self):
        return self._messages

    def drafts(self):
        return self._drafts


class FakeService:
    def __init__(self, messages=None, drafts=None):
        self._users = FakeUsers(messages or FakeMessages(), drafts or FakeDrafts())

    def users(self):
        return self._users


def test_search_messages_normalizes_headers_and_passes_query():
    fake_messages = FakeMessages()
    client = GmailClient(FakeService(messages=fake_messages))

    results = client.search_messages("from:recruiter newer_than:7d", limit=2)

    assert fake_messages.list_kwargs["userId"] == "me"
    assert fake_messages.list_kwargs["q"] == "from:recruiter newer_than:7d"
    assert fake_messages.list_kwargs["maxResults"] == 2
    assert results == [
        {
            "from_": "sender-m1@example.com",
            "subject": "Subject m1",
            "date": "Tue, 7 Jul 2026 10:00:00 -0400",
            "snippet": "snippet for m1",
        },
        {
            "from_": "sender-m2@example.com",
            "subject": "Subject m2",
            "date": "Tue, 7 Jul 2026 10:00:00 -0400",
            "snippet": "snippet for m2",
        },
    ]


def test_search_messages_returns_empty_for_no_matches():
    fake_messages = FakeMessages()
    fake_messages.list = lambda **kwargs: FakeExecutable({})
    client = GmailClient(FakeService(messages=fake_messages))

    assert client.search_messages("nothing") == []


def test_create_draft_builds_rfc822_message():
    fake_drafts = FakeDrafts()
    client = GmailClient(FakeService(drafts=fake_drafts))

    created = client.create_draft(
        to="recruiter@example.com",
        subject="Following up",
        body="Hi — just following up on our conversation.",
    )

    assert created == {"draft_id": "draft-99", "to": "recruiter@example.com", "subject": "Following up"}
    raw = fake_drafts.create_kwargs["body"]["message"]["raw"]
    decoded = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert decoded["To"] == "recruiter@example.com"
    assert decoded["Subject"] == "Following up"
    assert "following up on our conversation" in decoded.get_payload()
