
from os import path
try:
    from adapter import Pokemon
except ImportError:
    from .adapter import Pokemon

_root_path = path.abspath(path.dirname(__file__))

def get_pokemon_from_data(data):
    p = Pokemon(path.join(_root_path, "template_pokemon.epsd"))
    p.species_number = data["species"]["id"]
    p.item = data["item"]["id"]
    p.level = data["level"]
    p.name = data["ingamename"]
    p.ability = data["ability"]["id"]
    p.held_item = data["item"]["id"]
    p.shiny = data["shiny"]
    gender_number = {"m": 0, "f": 1}.get(data["gender"], 2)
    p.gender = gender_number
    p.nature = data["nature"]["id"]
    p.form = data["form"]
    p.friendship = data["happiness"]
    p.ball = data["ball"]["id"]
    p.individual_values.hp      = data["ivs"]["hp"]
    p.individual_values.attack  = data["ivs"]["atk"]
    p.individual_values.defense = data["ivs"]["def"]
    p.individual_values.speed   = data["ivs"]["spe"]
    p.individual_values.special_attack  = data["ivs"]["spA"]
    p.individual_values.special_defense = data["ivs"]["spD"]
    p.effort_values.hp = data["evs"]["hp"]
    p.effort_values.attack  = data["evs"]["atk"]
    p.effort_values.defense = data["evs"]["def"]
    p.effort_values.speed   = data["evs"]["spe"]
    p.effort_values.special_attack  = data["evs"]["spA"]
    p.effort_values.special_defense = data["evs"]["spD"]
    for i in range(4):
        p.moves[i].id = 0
    for i, move in enumerate(data["moves"]):
        p.moves[i].id = move["id"]
        p.moves[i].pp = move.get("pp", 5)  # todo remove optionality
        p.moves[i].pp_ups = move.get("pp_ups", 0)
    p.fateful_encounter = True
    p.fix_checksum()
    return p

