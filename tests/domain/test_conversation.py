"""The digit rule for assistant replies that give no Quote figures."""

import pytest

from sunquote.domain.conversation import ChatMessage, MessageRole, validate_echoed_digits
from sunquote.domain.narrative import ViolationKind

USER = MessageRole.USER
ASSISTANT = MessageRole.ASSISTANT


def check(text: str, *messages: ChatMessage) -> list[str]:
    violations = validate_echoed_digits(text, field="reply", messages=messages)
    assert all(v.kind is ViolationKind.DIGIT_NOT_IN_USER_MESSAGES for v in violations)
    return [v.detail for v in violations]


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("Hangi ilde oturuyorlar?", "Etimesgut"),
        ("40 m² çatının eğimi kaç derece?", "Etimesgut'ta 40 m² çatı"),
        ("Aylık 1500 TL fatura mı?", "faturam 1500 TL"),
        ("40,5 m² mi?", "40,5 metrekare"),
        ("30 ve 40 derece mi?", "40 m², 30 derece"),
    ],
)
def test_digit_sequences_the_sales_rep_wrote_are_allowed(text: str, said: str) -> None:
    assert check(text, ChatMessage(USER, said)) == []


def test_a_figure_the_sales_rep_did_not_write_is_a_violation_naming_it() -> None:
    (detail,) = check("35 m² mi?", ChatMessage(USER, "40 m² çatı"))

    assert "35" in detail
    assert "40" not in detail


def test_only_whole_digit_sequences_count_as_echoed() -> None:
    # "4" and "0" are digits of "40", but the sequence "4" was never written.
    assert check("4 m² mi?", ChatMessage(USER, "40 m² çatı")) != []
    # "1.500" is the sequences "1" and "500", not the "1500" the Sales Rep wrote.
    assert check("1.500 TL mi?", ChatMessage(USER, "faturam 1500 TL")) != []


def test_each_foreign_sequence_is_named_once() -> None:
    (detail,) = check("35 35 36", ChatMessage(USER, "çatı var"))

    assert detail.count("35") == 1
    assert "36" in detail


def test_figures_in_the_assistants_own_messages_are_not_the_sales_reps() -> None:
    messages = (
        ChatMessage(USER, "çatı var"),
        ChatMessage(ASSISTANT, "Kaç m²? Örneğin 12 m²"),
        ChatMessage(USER, "bilmiyorum"),
    )

    assert check("12 m² mi?", *messages) != []


def test_a_superscript_is_not_a_digit() -> None:
    assert check("m² cinsinden alan nedir?") == []
