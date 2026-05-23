from app.repositories.conversation_repository import (
    CONVERSATION_SHARE_CODE_ALPHABET,
    CONVERSATION_SHARE_CODE_PREFIX,
    CONVERSATION_SHARE_CODE_RANDOM_LENGTH,
    ConversationRepository,
)


def test_generate_share_code_uses_readable_short_format():
    share_code = ConversationRepository.generate_share_code()

    assert share_code.startswith(CONVERSATION_SHARE_CODE_PREFIX)
    suffix = share_code[len(CONVERSATION_SHARE_CODE_PREFIX):]
    assert len(suffix) == CONVERSATION_SHARE_CODE_RANDOM_LENGTH
    assert set(suffix).issubset(set(CONVERSATION_SHARE_CODE_ALPHABET))
