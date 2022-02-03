#  ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
#  MIT License
#
#  Copyright (c) 2021 Nathan Juraj Michlo
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#  ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~

import logging
from typing import Any
from typing import Callable
from typing import Dict
from typing import NoReturn
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import TypeVar
from typing import Union

from disent.util.function import wrapped_partial
from disent.util.imports import import_obj_partial
from disent.util.imports import _check_and_split_path


# ========================================================================= #
# Basic Cached Item                                                        #
# ========================================================================= #


T = TypeVar('T')


class LazyValue(object):
    """
    A lazy value uses a function to generate a value only when this value is retrieved.
    - The value is only ever generated once
    - The function is deleted when the value is generated
    - The value is cached forever
    """

    def __init__(self, generate_fn: Callable[[], T]):
        assert callable(generate_fn)
        self._is_generated = False
        self._generate_fn = generate_fn
        self._value = None

    def generate(self) -> T:
        # replace value -- we don't actually need caching of the
        # values since the registry replaces these items automatically,
        # but LazyValue is exposed so it might be used unexpectedly.
        if not self._is_generated:
            self._is_generated = True
            self._value = self._generate_fn()
            self._generate_fn = None
        # return value
        return self._value

    def __repr__(self):
        return f'{self.__class__.__name__}({repr(self._generate_fn)})'


# ========================================================================= #
# Import Helper                                                             #
# ========================================================================= #


class LazyImport(LazyValue):

    # TODO: improve the docs!

    def __init__(self, import_path: str, *partial_args, **partial_kwargs):
        super().__init__(
            generate_fn=lambda: import_obj_partial(import_path, *partial_args, **partial_kwargs),
        )


# ========================================================================= #
# Registry                                                                  #
# ========================================================================= #


_NONE = object()


class Registry(object):

    """
    This is a lazy registry.
    - Functions and values can be registered to this class under specific keys and aliases.
    - If the value is an instance of `LazyValue` then it is computed only once when the
      key is retreived, and the computed value is returned instead!
    """

    def __init__(
        self,
        name: str,
        assert_valid_key: Optional[Callable[[str], NoReturn]] = None,
        assert_valid_value: Optional[Callable[[T], NoReturn]] = None,
    ):
        # checks!
        assert str.isidentifier(name), f'The given name for the registry is not a valid identifier: {repr(name)}'
        self._name = name
        assert (assert_valid_key is None) or callable(assert_valid_key), f'assert_valid_key must be None or callable'
        assert (assert_valid_value is None) or callable(assert_valid_value), f'assert_valid_value must be None or callable'
        self._assert_valid_key = assert_valid_key
        self._assert_valid_value = assert_valid_value
        # storage
        self._keys_to_values: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self._name

    # TODO: split this into subclass
    def _get_aliases(self, name, aliases, auto_alias: bool):
        if auto_alias:
            if name not in self:
                aliases = (name, *aliases)
            elif not aliases:
                raise RuntimeError(f'automatic alias: {repr(name)} already exists but no alternative aliases were specified.')
        return aliases

    # TODO: split this into subclass
    def register(
        self,
        fn=_NONE,
        aliases: Sequence[str] = (),
        auto_alias: bool = True,
        partial_args: Tuple[Any, ...] = None,
        partial_kwargs: Dict[str, Any] = None,
    ) -> Callable[[T], T]:
        """
        Register a function or object to this registry.
        - can be used as a decorator @register(...)
        - automatically chooses an alias based on the function name
        - specify defaults for the function with the args and kwargs
        """
        def _decorator(orig_fn):
            # try add the name of the object
            keys = self._get_aliases(orig_fn.__name__, aliases=aliases, auto_alias=auto_alias)
            # wrap function
            new_fn = orig_fn
            if (partial_args is not None) or (partial_kwargs is not None):
                new_fn = wrapped_partial(
                    orig_fn,
                    *(() if partial_args is None else partial_args),
                    **({} if partial_kwargs is None else partial_kwargs),
                )
            # register the function
            self.register_value(value=new_fn, aliases=keys)
            return orig_fn
        # handle case
        if fn is _NONE:
            return _decorator
        else:
            return _decorator(fn)

    # TODO: split this into subclass
    def register_import(
        self,
        import_path: str,
        aliases: Sequence[str] = (),
        auto_alias: bool = True,
        *partial_args,
        **partial_kwargs,
    ) -> 'Registry':
        (*_, name) = _check_and_split_path(import_path)
        return self.register_value(
            value=LazyImport(import_path=import_path, *partial_args, **partial_kwargs),
            aliases=self._get_aliases(name, aliases=aliases, auto_alias=auto_alias),
        )

    def register_value(self, value: T, aliases: Sequence[str]) -> 'Registry':
        # check keys
        if len(aliases) < 1:
            raise ValueError(f'aliases must be specified, got an empty sequence')
        for k in aliases:
            if not str.isidentifier(k):
                raise ValueError(f'alias is not a valid identifier: {repr(k)}')
            if k in self._keys_to_values:
                raise RuntimeError(f'registry already contains key: {repr(k)}')
            self.assert_valid_key(k)
        # handle lazy values -- defer checking if a lazy value
        if not isinstance(value, LazyValue):
            self.assert_valid_value(value)
        # register keys
        for k in aliases:
            self._keys_to_values[k] = value
        return self

    def _normalise_aliases(self, aliases: Union[str, Tuple[str]]) -> Tuple[str]:
        if isinstance(aliases, str):
            aliases = (aliases,)
        if not isinstance(aliases, tuple):
            raise ValueError(f'multiple aliases must be provided as a Tuple[str], got: {repr(aliases)}')
        if len(aliases) < 1:
            raise ValueError(f'At least one alias must be specified, got: {repr(aliases)}')
        return aliases

    def __setitem__(self, alias: Union[str, Tuple[str]], value: T):
        aliases = self._normalise_aliases(alias)
        self.register_value(value=value, aliases=aliases)

    def __contains__(self, key: str):
        return key in self._keys_to_values

    def __getitem__(self, key: str):
        if key not in self._keys_to_values:
            raise KeyError(f'registry does not contain the key: {repr(key)}, valid keys include: {sorted(self._keys_to_values.keys())}')
        # get the value
        value = self._keys_to_values[key]
        # replace lazy value
        # TODO: split this into subclass
        if isinstance(value, LazyValue):
            value = value.generate()
            # check value & run deferred checks
            if isinstance(value, LazyValue):
                raise RuntimeError(f'{LazyValue.__name__} should never return other lazy values.')
            self.assert_valid_value(value)
            # update the value
            self._keys_to_values[key] = value
        # return the value
        return value

    def __iter__(self):
        yield from self._keys_to_values.keys()

    def assert_valid_value(self, value: T) -> T:
        if self._assert_valid_value is not None:
            self._assert_valid_value(value)
        return value

    def assert_valid_key(self, key: str) -> str:
        if self._assert_valid_key is not None:
            self._assert_valid_key(key)
        return key

    def __repr__(self):
        return f'{self.__class__.__name__}({repr(self._name)}, ...)'

    def setdefault(self, alias: Union[str, Tuple[str]], value: T) -> NoReturn:
        # only modify unset aliases, ignoring the rest!
        # - filter out names that have already been registered!
        aliases = self._normalise_aliases(alias)
        missing = tuple(alias for alias in aliases if (alias not in self))
        # - register aliases
        if missing:
            self.register_value(value=value, aliases=missing)
        else:
            logging.debug(f'skipped registering aliases for: {self.name} as the keys already exist: {repr(aliases)}')

    @property
    def setd(self) -> '_RegistrySetDefault':
        # instead of checking values manually, at the cost of some efficiency,
        # this allows us to register values multiple times with hardly modified notation!
        # -- only modifies unset values
        # set once:    `REGISTRY['key'] = val`
        # set default: `REGISTRY.sd['key'] = val`
        return _RegistrySetDefault(self)


class _RegistrySetDefault(object):
    def __init__(self, registry: Registry):
        self._registry: Registry = registry

    def __setitem__(self, aliases: str, value: T) -> NoReturn:
        self._registry.setdefault(aliases, value)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
