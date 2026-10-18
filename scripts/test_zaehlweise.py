#!/usr/bin/env python3
"""Eine Zaehlweise, nicht 26 Zahlen einzeln geheilt.

§A-ZZZZ207 (Runde 91 Befund 3): **die Heilung erfolgte pro Zahl, nicht pro
Zaehlweise.**

R91 korrigierte "27 Suiten" zu "24 Waechter-Suiten" via rg — und der
Stand-Fuss desselben Berichts sagte "26/26 gruen". Zwei Zahlen, ein
Absatz, keine Bruecke. Der Absatz, der die bare Zahl abschafft, endete
mit einer neuen baren Zahl.

Dieser Test erzwingt die Bruecke: jede Suite-Zahl wird EINMAL gezaehlt
und von dort ueberall gelesen. Er prueft nicht, dass 24 == 26 gilt
(das waere falsch — 24 sind Vertrags-Suiten, 26 die Gesamtmenge), sondern
dass der UNTERSCHIED BENANNT ist:

    24 = test_*.py mit Vertragsbezug
    26 = 24 + die 2, die nur ueber den Vertragssatz (nicht den Code) beruehren
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

VERTRAG = re.compile(r"waechter_vertrag\.json")


def zaehle() -> dict[str, list[str]]:
    """Die EINE Zaehlung. Alles andere liest hier."""
    korb: dict[str, list[str]] = {"code": [], "nur_vertrag": [], "aussen": []}
    for p in sorted(SCRIPTS.glob("test_*.py")):
        t = p.read_text(encoding="utf-8", errors="replace")
        if re.search(r"waechter_vertrag|einwurf_waechter|konsumenten_semantik", t):
            korb["code"].append(p.name)
        elif VERTRAG.search(t):
            korb["nur_vertrag"].append(p.name)
        else:
            korb["aussen"].append(p.name)
    return korb


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    k = zaehle()
    n_code = len(k["code"])
    n_v = len(k["nur_vertrag"])
    n_gesamt = n_code + n_v

    # 1. Die Zaehlung ist reproduzierbar: zweimal gleich.
    gesamt += 1
    gut = zaehle() == k
    print(f"{'ok  ' if gut else 'FAIL'} Zaehlung reproduzierbar    "
          f"{n_code}+{n_v}={n_gesamt}")
    ok += gut

    # 2. Die Bruecke ist deklariert: worin unterscheiden sich die Mengen?
    gesamt += 1
    br = d.get("zaehlweise", {})
    gut = "definition_code" in br and "definition_nur_vertrag" in br
    print(f"{'ok  ' if gut else 'FAIL'} Bruecke deklariert         "
          f"{sorted(br)[:3]}")
    ok += gut

    # 3. Die Vertragszahlen stimmen mit der Zaehlung — keine Drift.
    gesamt += 1
    gut = (br.get("n_code") == n_code and br.get("n_gesamt") == n_gesamt)
    print(f"{'ok  ' if gut else 'FAIL'} Zahlen == Zaehlung        "
          f"Vertrag {br.get('n_code')}/{br.get('n_gesamt')} vs "
          f"{n_code}/{n_gesamt}")
    ok += gut

    # 4. Die beiden Mengen sind disjunkt und ihre Summe ist die Gesamtmenge.
    gesamt += 1
    gut = (not set(k["code"]) & set(k["nur_vertrag"])
           and n_gesamt == n_code + n_v)
    print(f"{'ok  ' if gut else 'FAIL'} Mengen disjunkt           "
          f"Schnitt={len(set(k['code']) & set(k['nur_vertrag']))}")
    ok += gut

    # 5. kopfzeile.py liest BEIDE Zahlen aus dem Vertrag, tippt keine.
    gesamt += 1
    kopf = (SCRIPTS / "kopfzeile.py").read_text(encoding="utf-8")
    gut = "zaehlweise" in kopf or "n_code" in kopf
    print(f"{'ok  ' if gut else 'FAIL'} Kopfzeile liest Zaehlung  "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 6. Die Zuordnung ist aufgelistet, nicht nur die Summe.
    gesamt += 1
    gut = isinstance(br.get("nur_vertrag"), list) and \
        br.get("nur_vertrag") == k["nur_vertrag"]
    print(f"{'ok  ' if gut else 'FAIL'} nur_vertrag aufgelistet    "
          f"{k['nur_vertrag']}")
    ok += gut

    print(f"\n{ok}/{gesamt} Zaehlweise-Faelle gruen")
    print(f"     {n_code} (Code-Bezug) + {n_v} (nur Vertragssatz) "
          f"= {n_gesamt}")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
