### Direction 2c — Financial report, Slate sun palette — design tokens

Mockup: `mockups/2c-slate-sun.html`. Same direction 2 as `2-financial-report.html` (type, layout, radius, copy, figures), colour changed only. Slate-blue ink on cool white; a dark teal second series; solar gold only as a highlighter fill behind ink text: a utility company's annual report. Option 1 and Option 2 stay distinguishable without colour: Option 2 bars are hatched (45° paper stripes) and its cumulative line is dashed `10 4`; payback markers are a circle (Option 1) and a square (Option 2); the two options also sit in separate, headed figures.

**Typefaces** (unchanged from direction 2)

- **Headings, body, figures:** Newsreader (Google Fonts, variable, optical size 6–72, upright 400–700 and italic 400–600). Lining tabular figures. H1 44 px / 1.1 at opsz 72; H2 28; lede 22/1.5; body and table 17/1.55; captions italic 15.
- **Labels, buttons, chart ticks:** Hanken Grotesk (Google Fonts) 400–700. Labels are uppercase 11–12 px, tracking `.12–.14em`.

**Colour scale**

| Token | Value | Role |
| --- | --- | --- |
| `--desk` | `#E5EAF0` | page (the desk behind the sheet) |
| `--paper` | `#FAFCFE` | the printed sheet |
| `--wash` | `#EDF2F7` | input fill, total row |
| `--ink` | `#16212F` | slate-blue near-black: text, heavy rules, axes, price line, text on gold |
| `--ink-2` | `#4A5669` | secondary text, captions, consumption line |
| `--rule` | `#D2DAE4` | hairlines (decorative) |
| `--rule-strong` | `#76869A` | input underline, outlined controls (3:1+) |
| `--grid` | `#DAE1E9` | chart gridlines (decorative) |
| `--primary` | `#284E7E` | steel blue: links, selected state, focus ring, Option 1 text |
| `--accent` | `#064B4E` | dark teal: Option 2 text, section numbers |
| `--err` | `#A7182B` | errors and error borders |
| `--gold` | `#F4C400` | solar gold: FILL ONLY, always with `ink` text and an `ink` border where it forms a control (primary button, demo banner, logotype chip, payback highlighter). Never used as text, a line, a chart series or the sole boundary of a control |
| `--series-1` | `#5A94C8` | Option 1 chart marks and swatch (lighter steel; text uses primary) |
| `--series-2` | `#064B4E` | Option 2 chart marks and swatch (same value as accent) |

**Spacing:** 8 px base: 8 · 16 · 24 · 32 · 48 · 56 · 64. Sheet max width 960 px, padding 64 / 80 px. Sections 56 px apart. Form: 150 px legend column, 36 px gutter, 22 px between fields.

**Radius and borders:** 0 px everywhere (print). Rules instead of boxes: 1 px `ink` above and below tables, 1 px `rule` between rows, 3 px double `ink` rule under the letterhead and above the closing row. Input is a 2 px bottom rule on `wash`. Shadow only under the sheet (`rgba(22,33,47,.34)`).

**Chart palette**

| Use | Value |
| --- | --- |
| Option 1 | `#5A94C8`, solid bars, 2.5 px solid line, circle payback marker |
| Option 2 | `#064B4E`, bars hatched with 45° `#FAFCFE` stripes (2 px of 5 px), 2.5 px line dashed `10 4`, square payback marker |
| Total price | `#16212F` dashed `5 4`, 1.3 px |
| Monthly consumption | `#4A5669` dotted `2 4`, 1.8 px |
| Grid | `#DAE1E9` 1 px (decorative), axis `#16212F` 1 px |
| Price line vs series | Each cumulative figure holds one series and the price line, which cross once at the payback point. They are told apart by dash pattern, weight (1.3 px vs 2.5 px) and a direct label, not by a luminance gap, so no series-vs-price-line ratio is claimed |
| Layout | One grouped-bar figure; the cumulative chart is two small multiples, one per option, each on its own scale, captioned like a printed report (Şekil 1, 2–3) |

**Gold rule.** `--gold` on `--paper` is only 1.60:1, so it never carries meaning or a boundary by itself. It is a fill behind `--ink` text (9.86:1) and every gold control also has a 2 px `--ink` border (15.80:1 on paper). Gold is not used for text, lines or chart series.

**Notes:** Focus ring: 3 px `primary` outline, 3 px offset. Single centred column; below 800 px the sheet padding shrinks and the two-column blocks stack. Smallest interactive target 38 px high. Error and warning states never rely on colour: error text is bold with a message, the field gets a 3 px underline, and the banner is labelled "Herkese açık demo".

**WCAG 2.1 AA contrast** (token pairs; normal text ≥ 4.5:1; UI borders, focus rings and chart marks ≥ 3:1): all pass. Lowest ratio: 3.06:1 (Chart: Option 1 vs Option 2 series (adjacent bars, key swatches)).

| Pair | Foreground | Background | Ratio | Needs | Result |
| --- | --- | --- | --- | --- | --- |
| Body text on paper | `#16212F` | `#FAFCFE` | 15.80:1 | 4.5:1 | pass |
| Body text on desk (masthead) | `#16212F` | `#E5EAF0` | 13.43:1 | 4.5:1 | pass |
| Body text on wash (table total row, inputs) | `#16212F` | `#EDF2F7` | 14.42:1 | 4.5:1 | pass |
| Muted text on paper | `#4A5669` | `#FAFCFE` | 7.23:1 | 4.5:1 | pass |
| Muted text on desk | `#4A5669` | `#E5EAF0` | 6.14:1 | 4.5:1 | pass |
| Muted text on wash (placeholder, captions) | `#4A5669` | `#EDF2F7` | 6.60:1 | 4.5:1 | pass |
| Primary text / links on paper | `#284E7E` | `#FAFCFE` | 8.23:1 | 4.5:1 | pass |
| Primary text on desk (nav hover) | `#284E7E` | `#E5EAF0` | 7.00:1 | 4.5:1 | pass |
| Primary text on wash | `#284E7E` | `#EDF2F7` | 7.51:1 | 4.5:1 | pass |
| Accent text (Option 2 kicker, section numbers) on paper | `#064B4E` | `#FAFCFE` | 9.61:1 | 4.5:1 | pass |
| Accent text on wash | `#064B4E` | `#EDF2F7` | 8.78:1 | 4.5:1 | pass |
| Error text on paper | `#A7182B` | `#FAFCFE` | 7.27:1 | 4.5:1 | pass |
| Error text on wash | `#A7182B` | `#EDF2F7` | 6.64:1 | 4.5:1 | pass |
| Input underline / outlined control on paper (1.4.11) | `#76869A` | `#FAFCFE` | 3.62:1 | 3.0:1 | pass |
| Input underline on wash | `#76869A` | `#EDF2F7` | 3.30:1 | 3.0:1 | pass |
| Primary outline: segmented control border, focus ring on paper | `#284E7E` | `#FAFCFE` | 8.23:1 | 3.0:1 | pass |
| Error underline (3 px) on paper | `#A7182B` | `#FAFCFE` | 7.27:1 | 3.0:1 | pass |
| Selected segment: paper text on primary | `#FAFCFE` | `#284E7E` | 8.23:1 | 4.5:1 | pass |
| Skip link: paper text on primary | `#FAFCFE` | `#284E7E` | 8.23:1 | 4.5:1 | pass |
| Primary button: ink text on gold fill | `#16212F` | `#F4C400` | 9.86:1 | 4.5:1 | pass |
| Demo banner: ink text on gold fill | `#16212F` | `#F4C400` | 9.86:1 | 4.5:1 | pass |
| Logotype chip on desk: ink text on gold fill | `#16212F` | `#F4C400` | 9.86:1 | 4.5:1 | pass |
| Payback highlighter: ink text on gold fill | `#16212F` | `#F4C400` | 9.86:1 | 4.5:1 | pass |
| Gold button boundary: ink border on paper (1.4.11) | `#16212F` | `#FAFCFE` | 15.80:1 | 3.0:1 | pass |
| Gold button hover: ink text on paper | `#16212F` | `#FAFCFE` | 15.80:1 | 4.5:1 | pass |
| Logotype accent text: ink on desk | `#16212F` | `#E5EAF0` | 13.43:1 | 4.5:1 | pass |
| Chart: Option 1 series on paper | `#5A94C8` | `#FAFCFE` | 3.14:1 | 3.0:1 | pass |
| Chart: Option 2 series on paper | `#064B4E` | `#FAFCFE` | 9.61:1 | 3.0:1 | pass |
| Chart: Option 1 vs Option 2 series (adjacent bars, key swatches) | `#5A94C8` | `#064B4E` | 3.06:1 | 3.0:1 | pass |
| Chart: Option 2 hatch stripe (paper) on Option 2 fill | `#FAFCFE` | `#064B4E` | 9.61:1 | 3.0:1 | pass |
| Chart: price line (ink) on paper | `#16212F` | `#FAFCFE` | 15.80:1 | 3.0:1 | pass |
| Chart: consumption line (ink-2) on paper | `#4A5669` | `#FAFCFE` | 7.23:1 | 3.0:1 | pass |

Rendered-text audit in a browser (computed colour against the effective background of every visible text node, detail and form views): 332 text nodes checked in Microsoft Edge (headless), 0 failures, lowest rendered text ratio 6.14:1.

```css
:root {
  --desk: #E5EAF0;
  --paper: #FAFCFE;
  --wash: #EDF2F7;
  --ink: #16212F;
  --ink-2: #4A5669;
  --rule: #D2DAE4;
  --rule-strong: #76869A;
  --grid: #DAE1E9;
  --primary: #284E7E;
  --accent: #064B4E;
  --err: #A7182B;
  --gold: #F4C400;
  --series-1: #5A94C8;
  --series-2: #064B4E;
}
```
