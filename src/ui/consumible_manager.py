import numpy as np
from typing import List
import keyboard
import itertools
import cv2

from utils.misc import cut_roi, wait, color_filter
from utils.custom_mouse import mouse

from logger import Logger
from config import Config
from screen import Screen
from template_finder import TemplateFinder

class ConsumibleManager:
    def __init__(self, screen: Screen, template_finder: TemplateFinder):
        self._config = Config()
        self._screen = screen
        self._template_finder = template_finder
        self._consumible_needs = {"rejuv": 0, "health": 0, "mana": 0, "tp": 0, "id": 0, "key": 0}
        self._item_consumible_map = {
            "misc_rejuvenation_potion": "rejuv",
            "misc_full_rejuvenation_potion": "rejuv",
            "misc_super_healing_potion": "health",
            "misc_greater_healing_potion": "health",
            "misc_super_mana_potion": "mana",
            "misc_greater_mana_potion": "mana",
            "misc_scroll_of_town_portal": "tp",
            "misc_scroll_of_identify": "id",
            "misc_key": "key"
        }

    def get_consumible_needs(self):
        return self._consumible_needs

    def should_buy(self, item_name: str = None, minimum: int = 2):
        if item_name is None:
            Logger.error("should_buy: param item_name is required")
            return False
        return self._consumible_needs[item_name] >= minimum

    def _potion_type(self, img: np.ndarray) -> str:
        """
        Based on cut out image from belt, determines what type of potion it is.
        :param img: Cut out image of a belt slot
        :return: Any of ["empty", "rejuv", "health", "mana"]
        """
        h, w, _ = img.shape
        roi = [int(w * 0.4), int(h * 0.3), int(w * 0.4), int(h * 0.7)]
        img = cut_roi(img, roi)
        avg_brightness = np.average(img)
        if avg_brightness < 47:
            return "empty"
        score_list = []
        # rejuv
        mask, _ = color_filter(img, self._config.colors["rejuv_potion"])
        score_list.append((float(np.sum(mask)) / mask.size) * (1/255.0))
        # health
        mask1, _ = color_filter(img, self._config.colors["health_potion_0"])
        mask2, _ = color_filter(img, self._config.colors["health_potion_1"])
        mask_health = cv2.bitwise_or(mask1, mask2)
        score_list.append((float(np.sum(mask_health)) / mask_health.size) * (1/255.0))
        # mana
        mask, _ = color_filter(img, self._config.colors["mana_potion"])
        score_list.append((float(np.sum(mask)) / mask.size) * (1/255.0))
        # find max score
        max_val = np.max(score_list)
        if max_val > 0.28:
            idx = np.argmax(score_list)
            types = ["rejuv", "health", "mana"]
            return types[idx]
        else:
            return "empty"

    def _cut_potion_img(self, img: np.ndarray, column: int, row: int) -> np.ndarray:
        roi = [
            self._config.ui_pos["potion1_x"] - (self._config.ui_pos["potion_width"] // 2) + column * self._config.ui_pos["potion_next"],
            self._config.ui_pos["potion1_y"] - (self._config.ui_pos["potion_height"] // 2) - int(row * self._config.ui_pos["potion_next"] * 0.92),
            self._config.ui_pos["potion_width"],
            self._config.ui_pos["potion_height"]
        ]
        return cut_roi(img, roi)

    def drink_potion(self, potion_type: str, merc: bool = False, stats: List = []) -> bool:
        img = self._screen.grab()
        for i in range(4):
            potion_img = self._cut_potion_img(img, i, 0)
            if self._potion_type(potion_img) == potion_type:
                key = f"potion{i+1}"
                if merc:
                    Logger.debug(f"Give {potion_type} potion in slot {i+1} to merc. HP: {(stats[0]*100):.1f}%")
                    keyboard.send(f"left shift + {self._config.char[key]}")
                else:
                    Logger.debug(f"Drink {potion_type} potion in slot {i+1}. HP: {(stats[0]*100):.1f}%, Mana: {(stats[1]*100):.1f}%")
                    keyboard.send(self._config.char[key])
                self.adjust_consumible_need(potion_type, 1)
                return True
        return False

    def adjust_consumible_need(self, consumible_type: str = None, quantity: int = 1)
        """
        Adjust the _consumible_needs of a specific consumible
        :param consumible_type: Name of item in pickit or in consumible_map 
        :param quantity: Increase the need (+int) or decrease the need (-int)
        """
        if consumible_type is None:
            Logger.error("adjust_consumible_need: required param consumible_type not given")
        if consumible_type in self._item_consumible_map:
            consumible_type = self._item_consumible_map[consumible_type]
        elif consumible_type in _item_consumible_map.values():
            continue
        else:
            Logger.warning(f"ConsumibleManager does not know about item: {consumible_type}")
        self._consumible_needs[consumible_type] = max(0, self._consumible_needs[consumible_type] + quantity)

    def calc_all_needs(self, img: np.ndarray = None, consumible_type: list = []): 
        rejuv, health, mana = self.calc_pot_needs()
        tp, ids, key = self.calc_tp_id_key_quantity()
        return {
            "rejuv": rejuv, 
            "health": health, 
            "mana": mana, 
            "tp": 20 - tp, 
            "id": 20 - ids, 
            "key": 12 - key,
        }

    def calc_pot_needs(self) -> List[int]:
        """
        Check how many pots are needed
        :return: [need_rejuv_pots, need_health_pots, need_mana_pots]
        """
        self._consumible_needs = {"rejuv": 0, "health": 0, "mana": 0}
        rows_left = {
            "rejuv": self._config.char["belt_rejuv_columns"],
            "health": self._config.char["belt_hp_columns"],
            "mana": self._config.char["belt_mp_columns"],
        }
        # In case we are in danger that the mouse hovers the belt rows, move it to the center
        screen_mouse_pos = self._screen.convert_monitor_to_screen(mouse.get_position())
        if screen_mouse_pos[1] > self._config.ui_pos["screen_height"] * 0.72:
            center_m = self._screen.convert_abs_to_monitor((-200, -120))
            mouse.move(*center_m, randomize=100)
        keyboard.send(self._config.char["show_belt"])
        wait(0.5)
        # first clean up columns that might be too much
        img = self._screen.grab()
        for column in range(4):
            potion_type = self._potion_type(self._cut_potion_img(img, column, 0))
            if potion_type != "empty":
                rows_left[potion_type] -= 1
                if rows_left[potion_type] < 0:
                    rows_left[potion_type] += 1
                    key = f"potion{column+1}"
                    for _ in range(5):
                        keyboard.send(self._config.char[key])
                        wait(0.2, 0.3)
        # calc how many potions are needed
        img = self._screen.grab()
        current_column = None
        for column in range(4):
            for row in range(self._config.char["belt_rows"]):
                potion_type = self._potion_type(self._cut_potion_img(img, column, row))
                if row == 0:
                    if potion_type != "empty":
                        current_column = potion_type
                    else:
                        for key in rows_left:
                            if rows_left[key] > 0:
                                rows_left[key] -= 1
                                self._consumible_needs[key] += self._config.char["belt_rows"]
                                break
                        break
                elif current_column is not None and potion_type == "empty":
                    self._consumible_needs[current_column] += 1
        wait(0.2)
        Logger.debug(f"Will pickup: {self._consumible_needs}")
        keyboard.send(self._config.char["show_belt"])

    def calc_tp_id_key_quantity(self, img: np.ndarray = None, item_type: str = "tp"):
        if img is None:
            self.toggle_inventory("open")
            img = self._screen.grab()
        if item_type.lower() in ["tp", "id"]:
            state, pos = self._tome_state(img, item_type)
            if not state:
                return -1
            if state == "empty":
                return 0
            # else the tome exists and is not empty, continue
        elif item_type.lower() in ["key", "keys"]:
            result = self._template_finder.search("INV_KEY", img, roi=self._config.ui_roi["inventory"], threshold=0.9)
            if not result.valid:
                return -1
            pos = self._screen.convert_screen_to_monitor(result.position)
        else:
            Logger.error(f"get_quantity failed, item_type:{item_type} not supported")
            return -1
        mouse.move(pos[0], pos[1], randomize=4, delay_factor=[0.5, 0.7])
        wait(0.2, 0.4)
        hovered_item = self._screen.grab()
        # get the item description box
        try:
            item_box = self._item_cropper.crop_item_descr(hovered_item, ocr_language="engd2r_inv_th_fast")[0]
            result = parse.search("Quantity: {:d}", item_box.ocr_result.text).fixed[0]
            return result
        except:
            Logger.error(f"get_consumible_quantity: Failed to capture item description box for {item_type}")
            return -1


if __name__ == "__main__":
    keyboard.wait("f11")
    config = Config()
    screen = Screen(config.general["monitor"])
    template_finder = TemplateFinder(screen)
    consumible_manager = ConsumibleManager(screen, template_finder)
    consumible_manager.update_consumible_needs()
    print(consumible_manager._consumible_needs)