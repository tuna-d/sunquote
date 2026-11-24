"""The quote assistant's fixed Turkish texts: the confirmation, the question, the error
explanation and the request to restate.

The confirmation is the reply the Sales Rep gets when the model's own reply cannot be used after
a Quote was created; its figures come from the shared placeholder vocabulary
(`sunquote.domain.placeholders`, ADR 0001), filled from the Quote. The others are the replies
when there is no Quote and the model's own text cannot be used. None holds model text.
"""

from collections.abc import Mapping, Sequence

from sunquote.api import errors
from sunquote.domain.conversation import MissingField
from sunquote.domain.placeholders import fill_placeholders, option_placeholder
from sunquote.domain.ports import StoredQuote

_ORDINAL_WORDS = ("İlk", "İkinci")


def _confirmation_template(option_count: int) -> str:
    lines = ["Teklifiniz oluşturuldu. Teklif numarası: {quote_number}."]
    for number in range(1, option_count + 1):
        lines.append(
            f"{_ORDINAL_WORDS[number - 1]} seçenek: "
            f"{{{option_placeholder(number, 'capacity_kwp')}}} kWp, "
            f"toplam {{{option_placeholder(number, 'total_try')}}} (KDV dahil)."
        )
    return "\n".join(lines)


def fixed_confirmation(stored: StoredQuote, document_url: str, figures: Mapping[str, str]) -> str:
    """The Turkish reply that gives the Quote Number, each option's capacity and total price and
    the document link. It is a template filled from the Quote's `figures`, so it holds no LLM
    text."""
    options = len(stored.quote.system_options)
    text = fill_placeholders(_confirmation_template(options), figures)
    return f"{text}\nTeklif belgesi: {document_url}"


# The fixed Turkish replies for when there is no Quote and the model's own text cannot be used.
# They hold no digit and no model text.
RESTATE_REPLY = (
    "İsteğinizi tamamlayamadım. Lütfen müşteri, adres, çatı ve tüketim bilgilerini yeniden "
    "yazar mısınız?"
)

FIELD_LABELS: dict[MissingField, str] = {
    MissingField.CUSTOMER_NAME: "Müşteri adı",
    MissingField.SITE_ADDRESS: "Adres",
    MissingField.ROOF_TYPE: "Çatı tipi (eğimli veya düz)",
    MissingField.ROOF_TILT: "Çatı eğimi",
    MissingField.ROOF_AZIMUTH: "Çatının baktığı yön",
    MissingField.ROOF_USABLE_AREA: "Çatının kullanılabilir alanı",
    MissingField.CONSUMPTION: "Aylık elektrik tüketimi (kWh) veya fatura tutarı",
    MissingField.SUBSCRIBER_GROUP: "Abone grubu",
}

PROBLEM_LABELS: dict[str, str] = {
    errors.VALIDATION_ERROR.type_uri: "geçersiz değer",
    errors.ADDRESS_NOT_FOUND.type_uri: "adres bulunamadı",
    errors.NO_VIABLE_SYSTEM.type_uri: "uygun bir sistem bulunamadı",
    errors.NO_COMPATIBLE_INVERTER.type_uri: "uyumlu bir inverter bulunamadı",
    errors.UNSUPPORTED_SUBSCRIBER_GROUP.type_uri: "desteklenmeyen abone grubu",
    errors.LOCATION_NOT_SUPPORTED.type_uri: "konum desteklenmiyor",
    errors.UPSTREAM_UNAVAILABLE.type_uri: "harici bir hizmet geçici olarak kullanılamıyor",
}


def fixed_question(fields: Sequence[MissingField]) -> str:
    """The Turkish question that lists the missing fields with their labels."""
    lines = [f"- {FIELD_LABELS[field]}" for field in fields]
    return "Teklifi hazırlamak için şu bilgileri yazar mısınız?\n" + "\n".join(lines)


def fixed_error_explanation(problem_type: str) -> str | None:
    """The generic Turkish "the Quote could not be created, check the information" sentence
    naming the problem, or None for a problem type it has no name for."""
    label = PROBLEM_LABELS.get(problem_type)
    if label is None:
        return None
    return f"Teklif oluşturulamadı ({label}). Lütfen bilgileri kontrol edip yeniden yazar mısınız?"
