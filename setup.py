
from setuptools import setup, find_packages
setup(
    name="pbrengine",
    version="0.9.7.4",
    packages=find_packages(),
    package_dir={"pbrEngine": "pbrEngine"},
    package_data={"pbrEngine": ["eps/libeps32.dll", "eps/libeps64.dll", "eps/libeps.so", "eps/template_pokemon.epsd"]},
    install_requires=['dolphinWatch>=0.3'],

    author="Felk",
    description="Library based on DolphinWatch to offer automation of Pokemon Battle Revolution matches for TwitchPlaysPokemon.",
    url="https://github.com/TwitchPlaysPokemon/pbrEngine",
)
