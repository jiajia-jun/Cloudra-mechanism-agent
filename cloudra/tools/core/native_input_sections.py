"""Native section boundaries shared by structure and calculation inspection."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GaussianSections:
    route: list[str]
    charge: tuple[int, int] | None
    geometry: list[str]
    trailing: list[str]


def gaussian_option(token: str) -> tuple[str, set[str]]:
    key, separator, value = token.partition('=')
    if not separator and '(' in token:
        key, _, value = token.partition('(')
    return key, {option.strip() for option in value.strip('()').split(',')}


def gaussian_coordinate_units(route: list[str]) -> Literal['angstrom', 'bohr', 'unknown']:
    """Read declared coordinate units without choosing unknown/conflicting units."""
    unit_names = {'angstrom': 'angstrom', 'angstroms': 'angstrom', 'ang': 'angstrom',
                  'bohr': 'bohr', 'au': 'bohr', 'a.u.': 'bohr'}
    declared = set()
    for key, options in map(gaussian_option, route):
        if key != 'units':
            continue
        unit = unit_names.get(next(iter(options))) if len(options) == 1 else None
        if unit is None:
            return 'unknown'
        declared.add(unit)
    if len(declared) > 1:
        return 'unknown'
    return declared.pop() if declared else 'angstrom'


def gaussian_code(text: str) -> str:
    """Ignore Gaussian ! line comments while retaining quoted native values."""
    lines = []
    quote = ''
    for line in text.splitlines():
        code = []
        for char in line:
            if quote:
                code.append(char)
                if char == quote:
                    quote = ''
            elif char in ('"', "'"):
                quote = char
                code.append(char)
            elif char == '!':
                break
            else:
                code.append(char)
        lines.append(''.join(code))
    return '\n'.join(lines)


def gaussian_sections(text: str) -> list[GaussianSections]:
    """Read route/title/molecule boundaries without requiring explicit geometry.

    Inspection also reads checkpoint-only and Link1 jobs. Only structure callers
    impose the narrower requirement of one explicit Cartesian molecule.
    """
    from cloudra.tools.core.calculation_intent import native_tokens

    segments = [[]]
    for line in text.lstrip('\ufeff').splitlines():
        line = line.strip()
        if line.lower() == '--link1--':
            segments.append([])
        else:
            segments[-1].append(line)
    sections = []
    for lines in segments:
        index = next((i for i, line in enumerate(lines) if line.startswith('#') and not line.startswith('#!')), None)
        if index is None:
            continue
        route_lines = []
        while index < len(lines) and lines[index]:
            # A whole comment line is not the blank line ending the route.
            route_lines.append(lines[index])
            index += 1
        route_text = gaussian_code('\n'.join(route_lines)).replace('\n', ' ')[1:]
        head = route_text.split(None, 1)
        if head and head[0].lower() in {'p', 'n', 't'}:
            route_text = head[1] if len(head) > 1 else ''
        try:
            route = native_tokens(route_text)
        except ValueError:
            # A malformed calculation option cannot hide the molecule section.
            # Intent inspection still tokenizes this route strictly; these words
            # only let structure readers identify explicit geometry controls.
            route = route_text.lower().split()
        while index < len(lines) and not lines[index]:
            index += 1
        # Geom=AllCheck omits the title and molecule specification altogether.
        if any(key == 'geom' and options & {'allcheck', 'allcheckpoint'}
               for key, options in map(gaussian_option, route)):
            sections.append(GaussianSections(route, None, [], lines[index:]))
            continue
        while index < len(lines) and lines[index]:
            index += 1  # The entire title section, even titles such as "7 9".
        while index < len(lines) and not lines[index]:
            index += 1
        charge = None
        if index < len(lines):
            tokens = lines[index].split()
            if len(tokens) == 2:
                try:
                    charge = int(tokens[0]), int(tokens[1])
                except ValueError:
                    pass
        if charge is None:
            sections.append(GaussianSections(route, None, [], []))
            continue
        index += 1
        end = index
        while end < len(lines) and lines[end]:
            end += 1
        sections.append(GaussianSections(route, charge, lines[index:end], lines[end:]))
    return sections


def orca_xyz_sections(text: str) -> list[tuple[tuple[int, int], list[str]]]:
    """Read ORCA's equivalent *xyz and * xyz Cartesian molecule sections."""
    from cloudra.tools.core.calculation_intent import _orca_code

    lines = _orca_code(text.lstrip('\ufeff')).splitlines()
    sections = []
    for index, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('*'):
            continue
        tokens = line[1:].split()
        if len(tokens) != 3 or tokens[0].lower() != 'xyz':
            continue
        try:
            charge = int(tokens[1]), int(tokens[2])
        except ValueError:
            continue
        end = index + 1
        while end < len(lines) and lines[end].strip() not in {'', '*'}:
            end += 1
        sections.append((charge, lines[index + 1:end]))
    return sections


def orca_coordinate_units(text: str) -> Literal['angstrom', 'bohr', 'unknown']:
    """Read inline Cartesian units from simple input or the native %coords block."""
    from cloudra.tools.core.calculation_intent import _orca_code

    unit_names = {'angs': 'angstrom', 'angstrom': 'angstrom', 'angstroms': 'angstrom',
                  'bohrs': 'bohr', 'bohr': 'bohr', 'au': 'bohr'}
    declared = set()
    in_coords = False
    for line in _orca_code(text).splitlines():
        tokens = line.lower().split()
        if not tokens:
            continue
        if tokens[0] == '!':
            declared.update(unit_names[token] for token in tokens[1:] if token in unit_names)
        elif tokens[0].startswith('!'):
            declared.update(unit_names[token] for token in [tokens[0][1:], *tokens[1:]] if token in unit_names)
        if tokens[0] == '%coords':
            in_coords = True
            tokens = tokens[1:]
        if in_coords:
            for index, token in enumerate(tokens):
                if token != 'units':
                    continue
                unit = unit_names.get(tokens[index + 1]) if index + 1 < len(tokens) else None
                if unit is None:
                    return 'unknown'
                declared.add(unit)
            if 'end' in tokens:
                in_coords = False
    if len(declared) > 1:
        return 'unknown'
    return declared.pop() if declared else 'angstrom'
