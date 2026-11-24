"""The assistant's texts: the instruction's vocabulary and the fixed confirmation's rules."""

from sunquote.api.assistant_text import SYSTEM_INSTRUCTION
from sunquote.domain.conversation import REPLY_MAX_CHARACTERS
from sunquote.domain.placeholders import PLACEHOLDER_PATTERN, known_placeholders

ORIENTATION_BEARINGS = {
    "kuzey": 0,
    "kuzeydoğu": 45,
    "doğu": 90,
    "güneydoğu": 135,
    "güney": 180,
    "güneybatı": 225,
    "batı": 270,
    "kuzeybatı": 315,
}


def test_the_instruction_is_english_and_states_the_assistants_rules() -> None:
    lowered = SYSTEM_INSTRUCTION.lower()

    assert "reply in turkish" in lowered
    assert "never estimate" in lowered
    assert "coordinates" in lowered
    assert "kwh over a bill" in lowered
    assert "placeholder" in lowered
    assert f"{REPLY_MAX_CHARACTERS} characters" in SYSTEM_INSTRUCTION


def test_the_instruction_maps_every_orientation_word_to_its_compass_bearing() -> None:
    for word, bearing in ORIENTATION_BEARINGS.items():
        assert f"{word} {bearing}" in SYSTEM_INSTRUCTION


def test_the_instruction_names_only_placeholders_of_the_vocabulary() -> None:
    named = set(PLACEHOLDER_PATTERN.findall(SYSTEM_INSTRUCTION))

    assert named
    assert named <= known_placeholders()
