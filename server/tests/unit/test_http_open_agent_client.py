from app.libs.open_agent.providers.http import HTTPOpenAgentClient


def test_build_agent_detail_url_respects_api_v1_base_path():
    assert (
        HTTPOpenAgentClient._build_agent_detail_url("https://new.example.com/api/v1", 12)
        == "https://new.example.com/api/v1/agents/12"
    )
    assert (
        HTTPOpenAgentClient._build_agent_detail_url("https://new.example.com", 12)
        == "https://new.example.com/api/v1/agents/12"
    )


def test_parse_agent_welcome_message_reads_conversation_settings():
    payload = {
        "engine_config": {
            "conversation_settings": {
                "welcome_message": {
                    "enabled": True,
                    "blocks": [
                        {"type": "markdown", "content": "Hi **there**"},
                        {"type": "embed", "embed_code": "<div>Card</div>", "height": "240"},
                    ],
                }
            }
        }
    }

    assert HTTPOpenAgentClient._parse_agent_welcome_message(payload) == {
        "enabled": True,
        "blocks": [
            {"type": "markdown", "content": "Hi **there**"},
            {"type": "embed", "embed_code": "<div>Card</div>", "height": 240},
        ],
    }


def test_parse_agent_faq_reads_valid_categories():
    payload = {
        "engine_config": {
            "conversation_settings": {
                "faq": {
                    "enabled": True,
                    "title": " FAQ ",
                    "categories": [
                        {
                            "name": " Account ",
                            "questions": [
                                {"text": " How do I reset my password? "},
                                {"text": ""},
                                {"text": "How do I update billing?"},
                            ],
                        },
                        {"name": "Empty", "questions": []},
                        {"name": "", "questions": [{"text": "Ignored"}]},
                    ],
                }
            }
        }
    }

    assert HTTPOpenAgentClient._parse_agent_faq(payload) == {
        "enabled": True,
        "title": "FAQ",
        "categories": [
            {
                "name": "Account",
                "questions": [
                    {"text": "How do I reset my password?"},
                    {"text": "How do I update billing?"},
                ],
            }
        ],
    }
