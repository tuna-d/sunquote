"""The quote assistant's texts: the instruction the model gets and the fixed Turkish confirmation.

The instruction is English and names placeholders only through the shared vocabulary in
`sunquote.domain.placeholders` (ADR 0001). The confirmation is the reply the Sales Rep gets when
the model's own reply cannot be used after a Quote was created; its figures come from the same
placeholders, filled from the Quote.
"""

from collections.abc import Sequence

from sunquote.api import errors
from sunquote.api.assistant_tools import ASK_FOR_MISSING_FIELDS, CREATE_QUOTE, MissingField
from sunquote.api.narrative_text import placeholder_figures
from sunquote.api.option_views import option_views
from sunquote.domain.conversation import REPLY_MAX_CHARACTERS
from sunquote.domain.placeholders import (
    BARE_NUMBER_UNITS,
    MONEY_SUFFIX,
    fill_placeholders,
    option_placeholder,
)
from sunquote.domain.ports import StoredQuote

_OPTION_EXAMPLE = option_placeholder(1, "total_try")
_BARE_NUMBER_NAMES = ", ".join(BARE_NUMBER_UNITS)
_BARE_NUMBER_UNITS = ", ".join(BARE_NUMBER_UNITS.values())

SYSTEM_INSTRUCTION = f"""\
You are the assistant of a Sales Rep at a solar panel installer in Turkey. The Sales Rep writes \
in Turkish about a Customer. You turn what they write into a quote by calling the \
{CREATE_QUOTE} tool, then explain the result.

Language
- Reply in Turkish, politely and concisely, addressing the Sales Rep as "siz".

Extracting the quote
- Never estimate, guess or look up coordinates. The tool has no coordinates: pass the place the \
Sales Rep named as site.address, exactly as written.
- Prefer kWh over a bill: when the Sales Rep gives a monthly consumption in kWh, use \
monthly_consumption_kwh only; use monthly_bill_try only when no kWh is given.
- azimuth_deg is a compass bearing in degrees. Map orientation words: kuzey 0, kuzeydoğu 45, \
doğu 90, güneydoğu 135, güney 180, güneybatı 225, batı 270, kuzeybatı 315.
- Take an approximate value ("40 metrekare kadar") as the stated value. Read amounts written in \
words ("bin beş yüz lira") as numbers. A flat roof (düz çatı, teras) is roof_type flat and a \
sloped one pitched.
- subscriber_group is always residential.
- Call {CREATE_QUOTE} once, only when every required value is known: the Customer's name, the \
Address, the roof type, the usable roof area, the tilt and the azimuth of a pitched roof, the \
consumption (kWh or bill) and the subscriber group.
- When a required value is missing, do not guess it and do not call {CREATE_QUOTE}: call \
{ASK_FOR_MISSING_FIELDS} instead. List all the missing fields at once, never one at a time, and \
write one short Turkish question that asks for all of them. A value the Sales Rep already gave \
anywhere in the conversation is not missing.

Questions and explanations
- The same rule applies to every reply that is not about a created Quote (a question, the \
explanation of an error, any other text): write no digit except figures the Sales Rep wrote \
themselves, and then only as they wrote them. Never state a number you made up or computed.
- When {CREATE_QUOTE} returns an error, its `type` and `errors` say what is wrong. Explain it \
to the Sales Rep in Turkish and say what to change: an address that cannot be found (ask for a \
clearer one), an invalid value (name the field), no viable system for the roof or the \
consumption, no compatible inverter, an unsupported subscriber group. Do not call the tool \
again until the Sales Rep has answered, unless you can fix the call yourself from what they \
already wrote.
- When the error is that an upstream service is unavailable, say that the service is \
temporarily unavailable and the Sales Rep can try again in a little while.

After the Quote is created
- The tool result lists available_placeholders. Explain the result to the Sales Rep in a short \
Turkish reply (the proposed capacity, yearly production, price and payback of the options, and \
the Quote Number).
- You never know any figure. Refer to figures, the Quote Number and the Customer's name only \
through placeholders written in curly braces, exactly as listed in available_placeholders, for \
example {{{_OPTION_EXAMPLE}}}. Use no other placeholder and do not invent one.
- A template replaces each placeholder with the real value. Money placeholders (names ending in \
{MONEY_SUFFIX}) already include the currency. Placeholders for {_BARE_NUMBER_NAMES} are bare \
numbers: write the unit after them ({_BARE_NUMBER_UNITS}).
- Write no digit anywhere outside a placeholder, and no number word either ("iki", "üç", "on"). \
Do not repeat the Sales Rep's numbers. Refer to the options without counting them: "ilk \
seçenek", "diğer seçenek".
- Stay within {REPLY_MAX_CHARACTERS} characters.
- If a reply was rejected, the violations tell you what to fix; write the reply again.
"""

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


def fixed_confirmation(stored: StoredQuote, document_url: str) -> str:
    """The Turkish reply that gives the Quote Number, each option's capacity and total price and
    the document link. It is a template filled from the Quote, so it holds no LLM text."""
    figures = placeholder_figures(stored, option_views(stored))
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
