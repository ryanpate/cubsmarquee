"""Quarter-by-quarter linescore parsing for the NFL final-score screen"""

from __future__ import annotations


def _competitor(*period_values):
    """An ESPN competitor in the shape the scoreboard payload returns."""
    return {'linescores': [{'value': float(v)} for v in period_values]}


def test_returns_one_string_per_quarter():
    import bears_display as bd

    assert bd.extract_linescores(_competitor(0, 3, 0, 0)) == ['0', '3', '0', '0']


def test_collapses_overtime_periods_into_a_single_column():
    import bears_display as bd

    # Two OT periods sum into one trailing column so the grid stays 5 wide
    assert bd.extract_linescores(
        _competitor(7, 0, 10, 3, 3, 6)) == ['7', '0', '10', '3', '9']


def test_returns_empty_when_linescores_are_absent():
    import bears_display as bd

    assert bd.extract_linescores({}) == []


def test_prefers_display_value_when_present():
    import bears_display as bd

    competitor = {'linescores': [{'value': 7.0, 'displayValue': '7'},
                                 {'value': 0.0, 'displayValue': '0'}]}
    assert bd.extract_linescores(competitor) == ['7', '0']


def test_score_pair_parses_display_strings_to_ints():
    import bears_display as bd

    assert bd._score_pair('3', '9') == (3, 9)


def test_score_pair_returns_none_pair_for_unparseable_scores():
    import bears_display as bd

    assert bd._score_pair('', '9') == (None, None)


# Advance width per font, for turning a draw_text call into an x-extent
_ADVANCE = {'ultra_micro': 4, 'micro': 4, 'tiny': 5, 'tiny_bold': 5,
            'small_bold': 6, 'standard_bold': 7}


def _final_draws(linescore_len):
    """Every draw_text call the final screen makes, as (font, x, y, text)."""
    from unittest.mock import MagicMock
    import teams
    import bears_display
    teams.load_user_config = lambda: {}
    d = bears_display.BearsDisplay(MagicMock())
    d.manager = MagicMock()
    # Two-digit quarters are the crowding case that must stay legible
    values = ['14', '7', '10', '3', '7'][:linescore_len]
    d._draw_final_content(
        {'bears_score': '41', 'opp_score': '24', 'opponent_abbr': 'MIN',
         'team_linescores': values, 'opp_linescores': values},
        frame_count=0)
    return [(c.args[0], c.args[1], c.args[2], c.args[4])
            for c in d.manager.draw_text.call_args_list]


def _extent(font, x, text):
    return x, x + len(text) * _ADVANCE[font]


def test_box_score_stays_on_panel_and_clear_of_the_badge():
    for length in (4, 5):
        for font, x, y, text in _final_draws(length):
            left, right = _extent(font, x, text)
            assert left >= 0, (text, left)
            assert right <= 96, (f'{text} overflows the panel', right, length)


def test_box_score_cells_never_touch_on_a_row():
    """A 2-digit quarter beside another must keep a readable ink gap."""
    for length in (4, 5):
        rows = {}
        for font, x, y, text in _final_draws(length):
            rows.setdefault(y, []).append(_extent(font, x, text))
        for y, spans in rows.items():
            spans.sort()
            for (_, prev_right), (next_left, _) in zip(spans, spans[1:]):
                assert next_left - prev_right >= 2, (
                    f'row y={y} columns collide at {prev_right}->{next_left} '
                    f'with {length} columns')
