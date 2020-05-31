'''
Created on 10.09.2015

@author: Felk

This module represents the big "switch", which is supposed to
turn all those weird and separated dolphinWatch state/gui events
into uniform abstracted PBR states and events.
'''

from .states import PbrGuis
from .memorymap.values import GuiStateMenu, GuiStateBP, GuiStateRules, GuiStateBpSelection
from .memorymap.values import GuiStateOrderSelection, GuiStateMatch, StatePopupBox
from .util import bytesToString


class Distinguisher(object):
    def __init__(self, callback):
        self._callback = callback

    def distinguishMenu(self, val):
        self._callback(_map_menu.get(val))

    def distinguishBp(self, val):
        self._callback(_map_bps.get(val))

    def distinguishRules(self, val):
        self._callback(_map_rules.get(val))

    def distinguishBpSelect(self, val):
        self._callback(_map_bp_select.get(val))

    def distinguishOrder(self, val):
        self._callback(_map_order.get(val))

    def distinguishMatch(self, val):
        self._callback(_map_match.get(val))

    def distinguishPopup(self, val):
        if val == StatePopupBox.AWAIT_INPUT:
            self._callback(PbrGuis.MATCH_POPUP)

    def distinguishStart(self, data):
        self._callback(_map_start.get(bytesToString(data)))

# Main Menu
_map_menu = {
    GuiStateMenu.PRE_MAIN_MENU : PbrGuis.PRE_MENU_MAIN,
    GuiStateMenu.MAIN_MENU     : PbrGuis.MENU_MAIN,
    GuiStateMenu.BATTLE_PASS   : PbrGuis.MENU_BATTLE_PASS,
    GuiStateMenu.BATTLE_TYPE   : PbrGuis.MENU_BATTLE_TYPE,
    GuiStateMenu.BATTLE_PLAYERS: PbrGuis.MENU_BATTLE_PLAYERS,
    GuiStateMenu.BATTLE_REMOTES: PbrGuis.MENU_BATTLE_REMOTES,
    GuiStateMenu.SAVE          : PbrGuis.MENU_SAVE,
    GuiStateMenu.SAVE_CONFIRM  : PbrGuis.MENU_SAVE_CONFIRM,
    GuiStateMenu.SAVE_CONTINUE : PbrGuis.MENU_SAVE_CONTINUE,
    GuiStateMenu.SAVE_TYP2     : PbrGuis.MENU_SAVE_TYP2,
}

# Battle Pass Menu
_map_bps = {
    GuiStateBP.CONFIRM       : PbrGuis.BPS_PKMN_CONFIRM,
    GuiStateBP.BP_SELECTION  : PbrGuis.BPS_SELECT,
    GuiStateBP.SLOT_SELECTION: PbrGuis.BPS_SLOTS,
    GuiStateBP.BOX_SELECTION : PbrGuis.BPS_BOXES,
    GuiStateBP.PKMN_SELECTION: PbrGuis.BPS_PKMN,
    GuiStateBP.PKMN_GRABBED  : PbrGuis.BPS_PKMN_GRABBED,
}

# Rules Menu
_map_rules = {
    GuiStateRules.STAGE_SELECTION: PbrGuis.RULES_STAGE,
    GuiStateRules.OVERVIEW       : PbrGuis.RULES_SETTINGS,
    GuiStateRules.RULESET        : PbrGuis.RULES_RULESETS,
    GuiStateRules.BATTLE_STYLE   : PbrGuis.RULES_BATTLE_STYLE,
    GuiStateRules.BP_CONFIRM     : PbrGuis.RULES_BPS_CONFIRM,
}

# Battle Pass Selection Menu (before match)
_map_bp_select = {
    GuiStateBpSelection.BP_SELECTION_CUSTOM: PbrGuis.BPSELECT_SELECT,
    GuiStateBpSelection.BP_CONFIRM         : PbrGuis.BPSELECT_CONFIRM,
}

# Order Selection Menu
_map_order = {
    GuiStateOrderSelection.SELECT : PbrGuis.ORDER_SELECT,
    GuiStateOrderSelection.CONFIRM: PbrGuis.ORDER_CONFIRM,
}

# Match Gui
_map_match = {
    GuiStateMatch.FADE_IN: PbrGuis.MATCH_FADE_IN,
    GuiStateMatch.IDLE   : PbrGuis.MATCH_IDLE,
    GuiStateMatch.MOVES  : PbrGuis.MATCH_MOVE_SELECT,
    GuiStateMatch.PKMN   : PbrGuis.MATCH_PKMN_SELECT,
    GuiStateMatch.GIVE_IN: PbrGuis.MATCH_GIVE_IN,
}

# start menu
_map_start = {
    "Wii Remote Control Sideways":
        PbrGuis.START_WIIMOTE_INFO,
    "Configuración horizontal del mando de Wii":
        PbrGuis.START_WIIMOTE_INFO,  # es
    "Type de commandes horizontal":
        PbrGuis.START_WIIMOTE_INFO,  # fr
    "Steuerung C":
        PbrGuis.START_WIIMOTE_INFO,  # de
    "Telecomando Wii - Orizzontale":
        PbrGuis.START_WIIMOTE_INFO,  # it
    "Ｗｉｉリモコン「よこ」":
        PbrGuis.START_WIIMOTE_INFO,  # ja

    # This is the only one currently needed
    "Choose a Game Mode":
        PbrGuis.START_MENU,
    "Selección de modo de juego":
        PbrGuis.START_MENU,  # es
    "Choisir un mode de jeu":
        PbrGuis.START_MENU,  # fr
    "Spielmodus wählen":
        PbrGuis.START_MENU,  # de
    "Scegli una modalità di gioco":
        PbrGuis.START_MENU,  # it
    "ゲームモードを　えらんでください":
        PbrGuis.START_MENU,  # ja

    "Choose Options":
        PbrGuis.START_OPTIONS,
    "Selección de opciones":
        PbrGuis.START_OPTIONS,  # es
    "Options":
        PbrGuis.START_OPTIONS,  # fr
    "Optionen wählen":
        PbrGuis.START_OPTIONS,  # de
    "Scegli opzione":
        PbrGuis.START_OPTIONS,  # it
    "せっていを　えらんでください":
        PbrGuis.START_OPTIONS,  # ja

    "Save the changed options settings?":
        PbrGuis.START_OPTIONS_SAVE,
    "¿Guardar la nueva configuración?":
        PbrGuis.START_OPTIONS_SAVE,  # es
    "Sauvegarder les nouveaux paramètres?":
        PbrGuis.START_OPTIONS_SAVE,  # fr
    "Änderungen übernehmen?":
        PbrGuis.START_OPTIONS_SAVE,  # de
    "Vuoi salvare le modifiche alle impostazioni?":
        PbrGuis.START_OPTIONS_SAVE,  # it
    "せっていが　へんこうされました。\nゲームデータをセーブしますか？":
        PbrGuis.START_OPTIONS_SAVE,  # ja
    
    "Colosseum Mode":
        PbrGuis.START_MODE,
    "Modo Reto Coliseo":
        PbrGuis.START_MODE,  # es
    "Mode Colosseum":
        PbrGuis.START_MODE,  # fr
    "Colosseum-Modus":
        PbrGuis.START_MODE,  # de
    "Modalità Arena":
        PbrGuis.START_MODE,  # it
    "コロシアムモード":
        PbrGuis.START_MODE,  # ja

    # todo verify if it actually doesn't work
    # doesn't work, but relying on unstucker anyway
    "Continue":
        PbrGuis.START_SAVEFILE,
    "Continuar":
        PbrGuis.START_SAVEFILE,  # es
    "Continuer":
        PbrGuis.START_SAVEFILE,  # fr
    "Fortfahren":
        PbrGuis.START_SAVEFILE,  # de
    "Continua":
        PbrGuis.START_SAVEFILE,  # it
    "つづきから　はじめる":
        PbrGuis.START_SAVEFILE,  # ja

}
