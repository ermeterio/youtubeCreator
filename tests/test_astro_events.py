from datetime import date

from pipeline import astro_events


def test_no_event_returns_none_on_ordinary_day():
    # 1º de fevereiro de 2026 não está na janela de nenhum evento (próximo é
    # o eclipse anular em 17/02, com lookahead de 5 dias).
    assert astro_events.upcoming_event(date(2026, 2, 1)) is None


def test_event_detected_at_start_of_lookahead_window():
    # Perseidas: pico 13/08/2026, lookahead 4 dias -> janela abre em 09/08.
    # No dia 13/08 o eclipse de 12/08 já passou (fora da janela dele), então
    # só Perseidas qualifica - evita a sobreposição de janelas entre 09-12/08
    # (coberta separadamente em test_overlapping_windows_picks_the_nearer_event).
    event = astro_events.upcoming_event(date(2026, 8, 13))
    assert event is not None
    assert event.label == "A chuva de meteoros Perseidas"


def test_event_detected_on_the_exact_day():
    event = astro_events.upcoming_event(date(2026, 1, 10))
    assert event is not None
    assert event.label == "Júpiter em oposição"


def test_event_not_detected_one_day_before_window_opens():
    # Lua do Caçador: 26/10, lookahead 2 dias -> janela abre em 24/10.
    assert astro_events.upcoming_event(date(2026, 10, 23)) is None


def test_event_not_detected_after_it_already_happened():
    assert astro_events.upcoming_event(date(2026, 1, 11)) is None


def test_overlapping_windows_picks_the_nearer_event():
    # Eclipse solar total (12/08, lookahead 7 -> janela abre 05/08) e
    # Perseidas (13/08, lookahead 4 -> janela abre 09/08) se sobrepõem em
    # 09-12/08 - no dia 10/08 as duas janelas estão abertas, deve escolher
    # o evento mais próximo no tempo (eclipse, 12/08, antes de Perseidas 13/08).
    event = astro_events.upcoming_event(date(2026, 8, 10))
    assert event is not None
    assert event.label == "Eclipse solar total"


def test_all_events_have_required_fields_and_valid_lookahead():
    for event in astro_events.EVENTS:
        assert event.label
        assert event.image_query
        assert event.facts
        assert event.lookahead_days > 0
        assert isinstance(event.event_date, date)
