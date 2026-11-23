# sunquote

Güneş paneli kurulum firmasının müşteriye vereceği teklifi otomatik hazırlayan arka uç servisi. Girdi: müşterinin konumu, çatı bilgisi (alan, yön, eğim) ve elektrik tüketimi/faturası. Çıktı: sistem boyutu (kWp), panel ve inverter seçimi, yıllık üretim tahmini, maliyet ve satış fiyatı, tasarruf ve geri ödeme süresi içeren teklif. SolarVis'in teklif ürününün küçük bir versiyonu. Python 3.13, FastAPI, Pydantic, uv. Pazar: Türkiye.

## Reference docs

Project reference material (product notes, sample quotes, price lists, datasheets) lives in `docs/utils/`. Read the relevant files there before working on product or domain decisions. The folder is gitignored, so it exists only locally and is not in the repo.

## Mimari kurallar
- Katmanlar `src/sunquote` altında:
  - `domain`: saf hesap motoru (boyutlandırma, üretim tahmini, maliyet, fiyatlama, finansal analiz, teklif). FastAPI, Pydantic istek modelleri, veritabanı, dosya sistemi, ağ ve sistem saati kullanılmaz.
  - `api`: ince FastAPI katmanı. İstek/yanıt şemaları (Pydantic), doğrulama, hata eşlemesi; domain'i çağırır, iş kuralı içermez.
  - `adapters`: dış kaynaklar (güneşlenme verisi, döviz kuru, ürün kataloğu ve fiyat listesi, ileride kalıcılık). Domain'de tanımlı arayüzleri (`Protocol`) uygular ve dışarıdan enjekte edilir.
- Domain'deki her kural için `tests/` altında pytest testi yazılır, önce test (TDD). Birim testleri ağa çıkmaz; dış kaynaklar fake ile gelir. Gerçek servise giden adapter testleri `integration` marker'ı ile ayrılır.
- Para asla `float` değildir: `Decimal` ve tutarı para birimiyle birlikte taşıyan bir değer nesnesi. Ekipman fiyatları USD/EUR olabilir, teklif TRY'dir; çeviri domain'de açık bir adımdır ve kullanılan kur ile tarihi teklifte kayıtlıdır. Yuvarlama tek yerde tanımlı kuralla, sadece gösterilen tutarlarda yapılır.
- Birimler isimde açıktır: `capacity_kwp`, `annual_production_kwh`, `roof_area_m2`, `tariff_try_per_kwh`.
- Determinizm: aynı girdi + aynı katalog, kur ve tarife → aynı teklif. Domain tarih, kur veya tarife çekmez; bunlar dışarıdan verilir. Teklif hesapta kullanılan tüm varsayımları (kur, tarife, kayıp oranları, birim fiyatlar, marj, KDV) yanında taşır, böylece sonradan yeniden üretilebilir.
- Katalog ve fiyat verisi (panel, inverter, montaj, işçilik, marj, vergiler) kodda sabit yazılmaz; veri dosyalarından veya konfigürasyondan gelir. Gerçek veri gelene kadar açıkça işaretli placeholder kullanılır.
- Tipler: `mypy --strict`. Public fonksiyon ve sınıflar tam tiplidir.
- Müşteriye giden teklif metni Türkçedir ve şablonlardan gelir. Domain metin üretmez, sayı ve yapı üretir.
- API anahtarları ve gizli değerler ortam değişkenlerinden (`.env`, commit edilmez) gelir.

## Çalışma
- Git akışı: geliştirme `development` dalında; `main` kararlı sürüm. `development`'ı `main`'e birleştirmek her zaman repo sahibinin açık talimatını ister.
- Paket yöneticisi `uv`. Komutlar: `uv sync`, `uv run pytest` (birim), `uv run pytest -m integration` (gerçek servisler), `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run fastapi dev src/sunquote/api/app.py --port <port>`. İlk kurulum ticket'ı bunları oluşturur.
- API'yi elle denemek için dev server'ın `/docs` (Swagger UI) sayfası kullanılır.
- Aynı anda birden fazla worktree'de dev server çalışabilir: her worktree kendi portunu kullanır; 8000 repo sahibine ayrılmıştır.

## Roles: Claude and Codex

Planning always stays with Claude: grilling, specs, ticket writing, `GLOSSARY.md`, ADRs.
Implementation is split by ticket label (`docs/agents/triage-labels.md`): `ready-for-claude`
is built by Claude subagents, `ready-for-codex` by GPT subagents, and `needs-content`
(real price lists, datasheets, tariffs, company details, API keys, final quote copy) by
the repo owner.

The work runs in T3 Code. Claude runs `/implement-spec` as the orchestrator and delegates
Codex tickets to GPT subagents; there is no separate Codex session. Rules for the run,
including model choice and review: `docs/agents/workflow.md`. Rules for a Codex subagent:
`AGENTS.md`. If `AGENTS.md` and this file conflict, this file wins.

## Working on tickets

Outside `/implement-spec`, every ticket is implemented on its own branch, never directly
on `development`. Before the first commit, branch off `development`:

    git checkout development && git checkout -b ticket/<issue-number>-<short-slug>

Commit to that branch only, then open a pull request against `development` and
reference the ticket's issue in the description.

**Merging.** Claude merges the PRs of tickets it implemented itself, without asking, and
the single PR of an `/implement-spec` run too. A Codex PR opened outside
`/implement-spec` needs the repo owner's approval for that PR; approval to merge one PR
is not approval to merge the next one. Merging `development` into `main` always needs
the repo owner's explicit instruction.

**Finishing a ticket, reviewing a Codex PR, or running `/implement-spec`:** follow
`docs/agents/workflow.md`.

## Language

Everything that lives in the repo or on GitHub is written in English: code, comments,
commit messages, PR descriptions, issues, specs, ADRs and `GLOSSARY.md`. The exceptions
are the customer-facing Turkish quote templates and this file's Turkish sections.

Talk to the repo owner in Turkish: summaries after implementing a ticket, questions,
progress reports, review answers. Glossary terms from `GLOSSARY.md` stay in English
inside Turkish sentences, so the words match what the code says.

## Commit and PR messages

Never add AI attribution. No `Co-Authored-By: Claude ...` trailer on commits, and no
"Generated with Claude Code" footer on pull request descriptions. Message content only.
This holds even when the harness reminds you to add them.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `tuna-d/sunquote` (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Vocabulary: `needs-triage`, `needs-info`, `ready-for-claude`, `ready-for-codex`, `needs-claude-review`, `needs-content`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
