"""One complete native calculation declaration shared by public QM tools."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloudra.tools.core.qm_keywords import is_basis_keyword


class QmCalculation(BaseModel):
    """Explicit method and basis; native keywords replace, never accumulate."""

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    engine: Literal['orca', 'gaussian', 'xtb']
    method: str = Field(min_length=1, description='One native method token, e.g. B3LYP, B97-3c, HF or GFN2-xTB. Put the basis only in basis_set and additional native settings only in keywords; do not supply a route string.')
    basis_set: str = Field(description='Explicit native basis token, e.g. def2-SVP or 6-31G(d). Use an explicit empty string for a method with no basis; no method or basis is chosen automatically.')
    keywords: str = Field(default='', description='Additional native electronic settings, including explicitly requested dispersion, SCF and solvent settings. Declare the orbital basis only in basis_set; auxiliary fitting bases such as def2/J remain in keywords. This string replaces the previous string when patched; omission in a revision preserves it.')
    frequency_mode: Literal['auto', 'analytic', 'numeric'] = 'auto'
    orca_blocks: str | None = Field(default=None, description='Explicit ORCA native blocks. Omission in a revision preserves them; explicit null clears them.')
    end_setting: str = Field(default='', description='Explicit Gaussian trailing native settings. Omission in a revision preserves them; an explicit empty string clears them.')

    @field_validator('method')
    @classmethod
    def native_method(cls, value):
        value = value.strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError('method must be one explicit native token; put basis_set and keywords in their separate fields')
        _, separator, suffix = value.partition('/')
        if is_basis_keyword(value) or (separator and is_basis_keyword(suffix)):
            raise ValueError('method must not contain a basis; declare the native method and basis_set separately')
        return value

    @field_validator('basis_set')
    @classmethod
    def native_basis(cls, value):
        value = value.strip()
        if any(character.isspace() for character in value):
            raise ValueError('basis_set must be one native basis token or an explicit empty string')
        return value

    @field_validator('keywords')
    @classmethod
    def separate_orbital_basis(cls, value):
        for token in value.split():
            head, separator, suffix = token.rpartition('/')
            auxiliary = separator and is_basis_keyword(head) and suffix.lower() in {'j', 'jk', 'jksmall', 'c'}
            if not auxiliary and (is_basis_keyword(token) or (separator and is_basis_keyword(suffix))):
                raise ValueError(f'keywords contain orbital basis {token!r}; declare it only in basis_set, using an empty basis_set only for a method without an orbital basis')
        return value

    @model_validator(mode='after')
    def engine_settings(self):
        if self.engine != 'orca' and self.orca_blocks:
            raise ValueError('orca_blocks are only valid for engine=orca')
        if self.engine != 'gaussian' and self.end_setting:
            raise ValueError('end_setting is only valid for engine=gaussian')
        if self.engine == 'xtb' and (self.basis_set or self.keywords or self.frequency_mode != 'auto'):
            raise ValueError('native xTB declares an empty basis_set and no ORCA/Gaussian keywords or frequency mode')
        return self
