from textwrap import dedent

from urt30discord import mapfiles


def test_map_cycle_txt_add_map() -> None:
    s = """\
    ut4_abbey
    ut4_casa
    ut4_paris
    """
    expect = """\
    ut4_abbey
    ut4_casa
    ut4_tohunga_b8
    ut4_paris
    """
    actual = mapfiles.map_cycle_txt_add(
        dedent(s), "ut4_tohunga_b8", "after", "ut4_casa"
    )
    assert actual.strip() == dedent(expect).strip()


def test_map_cycle_txt_remove_map() -> None:
    s = """\
    ut4_abbey
    ut4_casa
    ut4_paris
    """
    actual = mapfiles.map_cycle_txt_remove(dedent(s), "ut4_tohunga_b8")
    assert actual.strip() == dedent(s).strip()

    expect = """\
    ut4_abbey
    ut4_paris
    """
    actual = mapfiles.map_cycle_txt_remove(dedent(s), "ut4_casa")
    assert actual.strip() == dedent(expect).strip()
