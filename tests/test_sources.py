from pathlib import Path

from reg_to_jdm.sources import load_sources, split_paragraph, subsection_key

ROOT = Path(__file__).resolve().parents[1]


def test_trid_sources_split_into_six_sentences():
    sources = load_sources(ROOT, ["sources/reg-z-1026-2-a-6.txt", "sources/trid-1026-19f.txt"])
    ids = [s.id for src in sources for s in src.sentences]
    assert ids == ["1026.2(a)(6)", "1026.2(a)(6).s2", "1026.19(f)(1)(i)",
                   "1026.19(f)(1)(ii)(A)", "1026.19(f)(1)(ii)(B)", "1026.19(f)(1)(iii)"]


def test_heading_is_kept_apart_and_italics_dropped():
    s = split_paragraph("x", "_Scope._ The creditor shall _not_ do it.", "f")[0]
    assert s.heading == "Scope."
    assert s.text == "The creditor shall not do it."


def test_no_split_after_abbreviations_or_inside_section_numbers():
    text = ("Holidays in 5 U.S.C. 6103(a), such as the Birthday of Martin Luther King, Jr., "
            "Washington's Birthday, under § 1026.38 apply. Next sentence.")
    parts = [s.text for s in split_paragraph("x", text, "f")]
    assert len(parts) == 2
    assert parts[1] == "Next sentence."


def test_subsection_key():
    assert subsection_key("1026.19(f)(1)(ii)(A)") == "s1026_19_f_1_ii_A"
