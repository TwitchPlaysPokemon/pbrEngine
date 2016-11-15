
from setuptools import setup, find_packages
setup(
    name="pbrengine",
    version="0.6.4",
    packages=find_packages(),
    package_dir={"pbrEngine": "pbrEngine"},
    package_data={"pbrEngine": ["eps/libeps.dll", "eps/template_pokemon.epsd"]},
    install_requires=['dolphinWatch'],

    author="Felk",
    description="Library based on DolphinWatch to offer automation of Pokemon Battle Revolution matches for TwitchPlaysPokemon.",
    url="https://github.com/TwitchPlaysPokemon/pbrEngine",
)
