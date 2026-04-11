from textwrap import dedent

from urt30discord import mapcycle


def test_parse_map_cycle_simple() -> None:
    s = """\
    ut4_abbey
    ut4_casa
    ut4_paris
    """
    result = mapcycle.parse_map_entries(dedent(s))
    assert len(result) == 3
    assert result[0].map_name == "ut4_abbey"
    assert result[0].map_options is None
    assert result[2].map_name == "ut4_paris"
    assert result[2].map_options is None


def test_parse_map_cycle_complex() -> None:
    s = """\
    ut4_abbey
    {
      g_gametype "7"
      g_gear KQS
      timelimit "10"
    }
    ut4_casa
    ut4_paris
    {
      g_gametype    "8"
      g_gear        "0"
      timelimit     "10"
    }
    """
    result = mapcycle.parse_map_entries(dedent(s))
    assert len(result) == 3
    assert result[0].map_name == "ut4_abbey"
    assert result[0].map_options is not None
    assert result[0].map_options["g_gear"] == "KQS"
    assert result[1].map_name == "ut4_casa"
    assert result[1].map_options is None
    assert result[2].map_name == "ut4_paris"
    assert result[2].map_options is not None
    assert result[2].map_options["timelimit"] == "10"
    assert result[2].map_options["g_gametype"] == "8"
