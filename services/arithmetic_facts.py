"""The arithmetic fact list, the table ladder, and the method clues.

Vocabulary (see the learning-practice design):

* A *direction* is one exact question: ``a x b`` (ordered) or ``p / d``
  where p = a x b. Its key is a stable text: ``m:3x4`` or ``d:12/3``.
* A *family* is the unordered pair {a, b}: up to four directions
  (``a x b``, ``b x a``, ``ab / a``, ``ab / b``). A square family (a = b)
  has two (``a x a``, ``aa / a``).
* The *ladder* is the order in which tables are opened for a child.

Factors run from 2 to 12. There is no x0, /0, x1 or /1.
Everything is generated in code and is deterministic.
"""
from dataclasses import dataclass
from html import escape

FACTORS = tuple(range(2, 13))

# Rung number = index + 1. Each rung lists the table(s) it adds.
LADDER: tuple[tuple[int, ...], ...] = (
    (2, 10), (5,), (4,), (3,), (6,), (8,), (9,), (7,), (11,), (12,),
)
RUNG_OF_TABLE = {t: i + 1 for i, tables in enumerate(LADDER) for t in tables}
LAST_RUNG = len(LADDER)


def rung_name(rung: int) -> str:
    """'2 and 10' or '5', for the trophy message."""
    return " and ".join(str(t) for t in LADDER[rung - 1])


@dataclass(frozen=True)
class Fact:
    key: str
    kind: str          # 'm' multiplication, 'd' division
    left: int          # m: first factor; d: the number being divided (p)
    right: int         # m: second factor; d: the divisor
    answer: int
    family: str        # e.g. 'f:3x4' (smaller factor first)

    @property
    def text(self) -> str:
        """The question without its answer: '3 × 4' or '12 ÷ 3'."""
        sign = "×" if self.kind == "m" else "÷"
        return f"{self.left} {sign} {self.right}"

    @property
    def factors(self) -> frozenset[int]:
        """The tables a direction belongs to: for division, divisor and quotient."""
        return frozenset({self.left, self.right}) if self.kind == "m" \
            else frozenset({self.right, self.answer})


def family_key(a: int, b: int) -> str:
    a, b = min(a, b), max(a, b)
    return f"f:{a}x{b}"


def family_rung(a: int, b: int) -> int:
    """A family belongs to the earliest rung at which one of its factors
    is an active table."""
    return min(RUNG_OF_TABLE[a], RUNG_OF_TABLE[b])


def _mult(a: int, b: int) -> Fact:
    return Fact(f"m:{a}x{b}", "m", a, b, a * b, family_key(a, b))


def _div(a: int, b: int) -> Fact:
    """p / b where p = a x b; the answer is a."""
    return Fact(f"d:{a * b}/{b}", "d", a * b, b, a, family_key(a, b))


def family_facts(a: int, b: int) -> list[Fact]:
    a, b = min(a, b), max(a, b)
    if a == b:
        return [_mult(a, a), _div(a, a)]
    return [_mult(a, b), _mult(b, a), _div(b, a), _div(a, b)]


def _build() -> tuple[list[tuple[int, int]], dict[str, list[Fact]], dict[str, Fact]]:
    pairs = [(a, b) for a in FACTORS for b in FACTORS if a <= b]
    # Fixed order: rung, then the smaller factor, then the larger.
    pairs.sort(key=lambda p: (family_rung(*p), p[0], p[1]))
    fams: dict[str, list[Fact]] = {}
    facts: dict[str, Fact] = {}
    for a, b in pairs:
        fl = family_facts(a, b)
        fams[family_key(a, b)] = fl
        for f in fl:
            facts[f.key] = f
    return pairs, fams, facts


_PAIRS, FAMILIES, FACTS = _build()
FAMILY_ORDER: list[str] = list(FAMILIES)                  # fixed introduction order
FAMILY_RUNG: dict[str, int] = {family_key(a, b): family_rung(a, b) for a, b in _PAIRS}
# Every direction in fixed order (family order, then direction order)
FACT_ORDER: list[str] = [f.key for k in FAMILY_ORDER for f in FAMILIES[k]]


def get_fact(key: str) -> Fact:
    return FACTS[key]


def families_up_to_rung(rung: int) -> list[str]:
    """Families available to a child whose latest rung is `rung`."""
    return [k for k in FAMILY_ORDER if FAMILY_RUNG[k] <= rung]


def facts_of_rung(rung: int) -> list[str]:
    """Directions that belong to the table(s) of this rung: those with one
    of the tables as a factor (for division, the divisor or the quotient)."""
    tables = set(LADDER[rung - 1])
    return [k for k in FACT_ORDER if FACTS[k].factors & tables]


# ── Method clues ───────────────────────────────────────────────────────────

def multiplication_clue_lines(fact: Fact) -> list[str]:
    """Count in b's: '1 x b = b' ... up to 'a x b = ?'. The product is
    never printed."""
    a, b = fact.left, fact.right
    lines = [f"{k} × {b} = {k * b}" for k in range(1, a)]
    lines.append(f"{a} × {b} = ?")
    return lines


def division_clue_text(fact: Fact) -> str:
    return (f"Let's divide {fact.left} into {fact.right} equal groups. "
            "How many in each group?")


def division_alt_text(fact: Fact) -> str:
    """Accessible description. Names the counters and groups, not the answer."""
    return f"{fact.left} counters in {fact.right} equal groups"


def division_clue_svg(fact: Fact) -> str:
    """Inline SVG of p counters in d outlined groups of p/d. Exact by
    construction: d <g class="group"> elements, each with one outline and
    p/d circles."""
    d, q = fact.right, fact.answer
    cols = q if q <= 6 else (q + 1) // 2
    rows = -(-q // cols)
    pitch, pad, gap = 22, 8, 14
    gw, gh = cols * pitch + 2 * pad - (pitch - 16), rows * pitch + 2 * pad - (pitch - 16)
    per_row = min(d, 4)
    grows = -(-d // per_row)
    width = per_row * gw + (per_row - 1) * gap + 4
    height = grows * gh + (grows - 1) * gap + 4
    label = escape(division_alt_text(fact))
    parts = [
        f'<svg class="division-clue" role="img" aria-label="{label}" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{label}</title>",
    ]
    for g in range(d):
        gx = 2 + (g % per_row) * (gw + gap)
        gy = 2 + (g // per_row) * (gh + gap)
        parts.append('<g class="group">')
        parts.append(
            f'<rect class="group-outline" x="{gx}" y="{gy}" width="{gw}" height="{gh}" '
            'rx="10" fill="none" stroke="currentColor" stroke-width="2"/>'
        )
        for i in range(q):
            cx = gx + pad + 8 + (i % cols) * pitch
            cy = gy + pad + 8 + (i // cols) * pitch
            parts.append(f'<circle class="counter" cx="{cx}" cy="{cy}" r="8" fill="currentColor"/>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)
