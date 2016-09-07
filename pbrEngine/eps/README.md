# libeps - python adapter api

This module is a python adapter-API for libeps, a C library for editing Pokemon Battle Revolution savefiles.
For further information on libeps, visit: [github.com/TwitchPlaysPokemon/pokerevo/tree/master/utils/libeps](https://github.com/TwitchPlaysPokemon/pokerevo/tree/master/utils/libeps).

There are two classes offered by this module: `Savefile` and `Pokemon`. For the most part these just wrap the underlying C-API functions for reading or writing data in python properties. For details on which methods and properties are offered, please skim through [adapter.py](adapter.py). Or just take a look at some [example code](__init__.py).

### Usage of the `Savefile` class

The `Savefile` class' constructor takes exactly 1 arguments: `filepath`, which is a `PbrSaveData` file to load the object from.
* Raises a `FileNotFoundError` if the file does not exist.
* Raises an `IOError` if there way an error reading the file.
* Raises an [`IntegrityError`](errors.py) if the file is corrupted.

Modifications to this object can be saved with the `save()` method, which optionally takes another `filepath` argument. If it is omitted, overwrites the file this object was originally created from.

### Usage of the `Pokemon` class

The `Pokemon` class' constructor takes 3 optional arguments: `filepath_or_save`, `box` and `pos`.
* If `filepath_or_save` is a `Savefile` object, `box` and `pos` are mandatory (a `ValueError` is raised if they are missing). Loads the `Pokemon`-object from the given `Savefile`-object by reading the pokemon stored in `box` at position `pos`.
* If `filepath_or_save` is a filepath, loads this `Pokemon`-object from that file. Can raise the same errors as above.
* If `filepath_or_save` is None, creates a new, blank `Pokemon`-object.

Modifications to this object can be saved with the `save()` method, which takes the same arguments as the constructor. If `filepath_or_save` is omitted, either overwrites the file this object was created from, or overwrites the pokemon in the given `box` and `pos` in the savefile this object was loaded from, depending on what this object was loaded from. Note that if `filepath_or_save` is omitted, `box` and `pos` can still be supplied to write the Pokémon onto a different spot of the same savefile.
