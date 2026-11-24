"""The quote assistant's texts: the instruction the model gets and the fixed Turkish confirmation.

The instruction is English and names placeholders only through the shared vocabulary in
`sunquote.domain.placeholders` (ADR 0001). The confirmation is the reply the Sales Rep gets when
the model's own reply cannot be used after a Quote was created; its figures come from the same
placeholders, filled from the Quote.
"""

from sunquote.api.assistant_tools import CREATE_QUOTE
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
- If a required value is missing, ask the Sales Rep for it in one short Turkish question and do \
not call the tool. Call the tool once, when everything it needs is known.

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
