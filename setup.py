
from setuptools import setup
setup(
    name="pbrEngine",
    version="0.1",
    packages=["pbrEngine"],
    setup_requires=['dolphinWatch'],
    install_requires=['dolphinWatch'],
    dependency_links=['https://github.com/TwitchPlaysPokemon/PyDolphinWatch/tarball/master#egg=dolphinWatch'],

    author="Felk",
    description="Library based on DolphinWatch to offer automation of Pokemon Battle Revolution matches for TwitchPlaysPokemon.",
    url="https://github.com/TwitchPlaysPokemon/pbrEngine",
)
