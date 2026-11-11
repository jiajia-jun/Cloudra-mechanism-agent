import pytest

from cloudra.tools.core.md_box_density import lookup_density_reference

WATER = 'XLYOFNOQVPJJNP-UHFFFAOYSA-N'
METHANOL = 'OKKJLVBELUTLKV-UHFFFAOYSA-N'
ETHANOL = 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N'
ACETONITRILE = 'WEVYAHXRMPXWCK-UHFFFAOYSA-N'
DMSO = 'IAZDPXIOMUYVGZ-UHFFFAOYSA-N'


@pytest.mark.parametrize(('identity', 'density'), [
    (WATER, 0.99706),
    (METHANOL, 0.78687),
    (ETHANOL, 0.78514),
    (ACETONITRILE, 0.77669),
    (DMSO, 1.09529),
])
def test_pure_liquid_reference_has_conditions_and_source(identity, density):
    reference = lookup_density_reference([(identity, 20), (identity, 30)])

    assert reference['density_g_cm3'] == pytest.approx(density)
    assert reference['temperature_k'] == 298.15
    assert 'pressure_kpa' in reference
    assert reference['source'].startswith('https://')


def test_water_ethanol_interpolation_uses_actual_mole_fractions():
    reference = lookup_density_reference([(ETHANOL, 10), (WATER, 2), (WATER, 8)])

    assert reference['density_g_cm3'] == pytest.approx(0.85883)
    assert reference['temperature_k'] == 298.15
    assert reference['pressure_kpa'] == 101.0
    assert reference['mole_fractions'] == {WATER: 0.5, ETHANOL: 0.5}
    assert reference['interpolated'] is True


def test_water_acetonitrile_at_a_measured_composition_keeps_its_conditions():
    reference = lookup_density_reference([(WATER, 496), (ACETONITRILE, 504)])

    assert reference['density_g_cm3'] == pytest.approx(0.84971)
    assert reference['temperature_k'] == 293.15
    assert reference['pressure_kpa'] == 81.5
    assert reference['interpolated'] is False


@pytest.mark.parametrize('components', [
    [(WATER, 10), (METHANOL, 10)],
    [(WATER, 10), (None, 1)],
    [(WATER, 10), (ETHANOL, 10), (ACETONITRILE, 10)],
    [('XLYOFNOQVPJJNP-UHFFFAOYSA-M', 10)],
])
def test_unavailable_references_are_not_substituted(components):
    assert lookup_density_reference(components) is None
