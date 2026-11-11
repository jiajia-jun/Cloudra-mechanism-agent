"""Look up reference liquid densities for a verified box composition."""

import json
from functools import cache
from importlib.resources import files
from itertools import pairwise


@cache
def _density_references() -> dict:
    return json.loads(files(__package__).joinpath('md_box_densities.json').read_text(encoding='utf-8'))


def lookup_density_reference(components: list[tuple[str | None, int]]) -> dict | None:
    """Use verified molecule counts and full InChIKeys to match reference data."""
    counts: dict[str, int] = {}
    for identity, count in components:
        if identity is None:
            return None
        counts[identity] = counts.get(identity, 0) + count

    references = _density_references()
    if len(counts) == 1:
        reference = references['pure'].get(next(iter(counts)))
        return dict(reference, interpolated=False) if reference is not None else None
    if len(counts) != 2:
        return None

    for series in references['binary']:
        first, second = series['components']
        if first not in counts or second not in counts:
            continue
        # Each point pairs the first component's mole fraction with its mixture density.
        mole_fraction = counts[first] / (counts[first] + counts[second])
        for (left_x, left_density), (right_x, right_density) in pairwise(series['points']):
            if left_x <= mole_fraction <= right_x:
                fraction = (mole_fraction - left_x) / (right_x - left_x)
                density = left_density + fraction * (right_density - left_density)
                return {
                    'density_g_cm3': round(density, 5),
                    'temperature_k': series['temperature_k'],
                    'pressure_kpa': series['pressure_kpa'],
                    'source': series['source'],
                    'mole_fractions': {first: mole_fraction, second: 1 - mole_fraction},
                    'interpolated': mole_fraction not in (left_x, right_x),
                }
    return None
