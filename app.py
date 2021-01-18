"""
Simple 2d world where the player can interact with the items in the world.
"""

__author__ = "Youngsu Choi"
__date__ = "2019-05-31"
__version__ = "1.1.0"
__copyright__ = "The University of Queensland, 2019"

import tkinter as tk
from tkinter import messagebox
import random
from collections import namedtuple

import pymunk
import cmath

from block import Block, ResourceBlock, BREAK_TABLES, LeafBlock, TrickCandleFlameBlock
from grid import Stack, Grid, SelectableGrid, ItemGridView
from item import Item, SimpleItem, HandItem, BlockItem, MATERIAL_TOOL_TYPES, TOOL_DURABILITIES
from player import Player
from dropped_item import DroppedItem
from crafting import GridCrafter, CraftingWindow
from world import World
from core import positions_in_range, EffectID
from game import GameView, WorldViewRouter
from mob import Mob, Bird
from physical_thing import BoundaryWall

BLOCK_SIZE = 2 ** 5
GRID_WIDTH = 2 ** 5
GRID_HEIGHT = 2 ** 4

GameData = namedtuple('GameData', ['world', 'player'])
# Break table for crafted/other blocks
CRAFTED_BLOCKS = {
    "wood_plank": {
        "hand": (3, True),
        "wood_axe": (2, True),
        "stone_axe": (1, True),
        "golden_axe": (0.6, True),
        "iron_axe": (0.5, True),
        "diamond_axe": (0.1, True)
    },
    "refined_stone": {
        "hand": (5, False),
        "wood_pickaxe": (2, True),
        "stone_pickaxe": (1, True),
        "golden_pickaxe": (0.6, True),
        "iron_pickaxe": (0.5, True),
        "diamond_pickaxe": (0.1, True)
    },
    "stone_slab": {
        "hand": (5, False),
        "wood_pickaxe": (2, True),
        "stone_pickaxe": (1, True),
        "golden_pickaxe": (0.6, True),
        "iron_pickaxe": (0.5, True),
        "diamond_pickaxe": (0.1, True)
    },
    "bed": {
        "hand": (1, True)
    },
    "hive":{
        "hand": (1, True)
    },
    "honey":{
        "hand": (1, True)
    },
    "wool":{
        "hand": (1, True)
    }
}
# Block/Item colours
BLOCK_COLOURS = {
    'diamond': 'blue',
    'dirt': '#552015',
    'stone': 'grey',
    'wood': '#723f1c',
    'leaves': 'green',
    'crafting_table': 'pink',
    'furnace': 'black',
    'refined_stone': 'ivory2',
    'stone_slab': 'orange',
    'wood_plank': 'navajo white',
    'wool': 'white',
    'bed': 'red',
    'hive': 'yellow',
    'honey': 'orange'
}

ITEM_COLOURS = {
    'diamond': 'blue',
    'dirt': '#552015',
    'stone': 'grey',
    'wood': '#723f1c',
    'apple': '#ff0000',
    'leaves': 'green',
    'crafting_table': 'pink',
    'furnace': 'black',
    'cooked_apple': 'red4',
    'stick': 'navajo white',
    'stone_slab': 'orange',
    'refined_stone': 'ivory2',
    'wool': 'white',
    'bed': 'red',
    'honey': 'orange'
}
# Bee movement constants
BEE_GRAVITY = 100
BEE_X_SCALE = 2.5

class Sheep(Mob):
    """A friendly sheep, drops wool when attacked"""
    def take_damage(self, damage):
        """Sheeps cannot take damage..."""
        pass

    def is_dead(self):
        """(bool) Returns True for sheep always as they cannot die"""
        return True

    def get_drops(self, luck):
        """Places wools into the world"""
        return [('item', 'wool')]

    def step(self, time_delta, game_data):
        """Advance sheep by one time step"""
        movement = random.randint(-50, 50)
        x, y = self.get_velocity()

        if self._steps % 50 == 0:
            velocity = x + movement, -150
            self.set_velocity(velocity)

        super().step(time_delta, game_data)

class Bee(Mob):
    """Bees, swarms players and honey blocks"""

    def take_damage(self, damage):
        """
            Parameters:
                damage(int): Damage taken by the bee

        """
        self._health += damage

    def get_drops(self, luck):
        """Bees don't drop anything..."""
        return None

    def step(self, time_delta, game_data):
        """Advance bee by one time step"""
        honey = []
        honey_positions = []
        all_things = game_data[0].get_all_things()

        # Bees positions [(x,y) & grid] and velocity
        b_x, b_y = self.get_position()
        x, y = self.get_velocity()
        bee_grid_x, bee_grid_y = game_data[0].xy_to_grid(b_x, b_y)

        # Player/position
        player = game_data[1]
        p_x, p_y = game_data[1].get_position()

        # Searches for all instances of honey blocks in world
        for thing in all_things:
            if isinstance(thing, Block):
                if thing.get_id() == "honey":
                    honey.append(thing)
        # Searches for honey blocks that are within 10 blocks of range to the bee
        for honeyblock in honey:
            h_x, h_y = honeyblock.get_position()
            g_x, g_y = game_data[0].xy_to_grid(h_x, h_y)

            if abs(g_x - bee_grid_x) <= 10 or abs(g_y - bee_grid_y) <= 10:
                honey_positions.append((h_x, h_y))
        # If there are honey blocks within a 10 block range of the bee,
        # the bees will swarm the block, otherwise swarm player
        if honey_positions != []:
            honey_positions = sorted(honey_positions)
            honey_x, honey_y = honey_positions[0]
            xdist = (honey_x - b_x)
            ydist = (honey_y - b_y)
        else:
            ydist = (p_y - b_y)
            xdist = (p_x - b_x)

        if self._steps % 7 == 0:
            z = cmath.rect(1, random.uniform(0, 0.5*cmath.pi))
            # stretch that random point onto an ellipse that is wider on the x-axis
            dx, dy = z.real * BEE_X_SCALE, z.imag
            velocity = x + xdist + dx, y + ydist + dy - BEE_GRAVITY
            self.set_velocity(velocity)

        super().step(time_delta, game_data)

class Router(WorldViewRouter):
    "Subclass of WorldViewRouter, handles all the drawing of physical things on a canvas"
    def __init__(self, block_colours, item_colours, player_colour='red'):
        """Constructor

                Parameters:
                     block_colours (dict<str: str>): A mapping of block ids to their respective colours
                     item_colours (dict<str: str>): A mapping of item ids to their respective colours
                """
        super().__init__(block_colours, item_colours, player_colour)

    _routing_table = [
        (Block, '_draw_block'),
        (TrickCandleFlameBlock, '_draw_mayhem_block'),
        (DroppedItem, '_draw_physical_item'),
        (Player, '_draw_player'),
        (Bird, '_draw_bird'),
        (BoundaryWall, '_draw_undefined'),
        (Sheep, '_draw_sheep'),
        (Bee, '_draw_bee'),
        (None.__class__, '_draw_undefined')
    ]

    # All methods follow the following signature:
    #   instance (PhysicalThing): The physical thing to draw
    #   shape (pymunk.Shape): The physical thing's shape in the world
    #   view (tk.Canvas): The canvas on which to draw the thing

    def _draw_sheep(self, instance, shape, view):
        bb = shape.bb

        return [view.create_oval(shape.bb.left, shape.bb.top, shape.bb.right, shape.bb.bottom,
                          fill='white', tags=('mob','sheep'))]

    def _draw_bee(self, instance, shape, view):
        bb = shape.bb

        centre_x = (bb.left + bb.right) // 2
        centre_y = (bb.top + bb.bottom) // 2

        return [
            view.create_polygon((centre_x, bb.top), (bb.right, centre_y), (centre_x, bb.bottom), (bb.left, centre_y),
                                fill='Black', tags=('mob', 'bee'))]

class ToolItem(Item):
    """Tools to be made within the sandbox game"""

    def __init__(self, id_ : str, tool_type : str, durability: float):
        """Constructor

                Parameters:
                    id_ (str): The id representation of a certain tool
                    tool_type(str): The type of tool (pickaxe, sword, etc.)
                    durability(str): The durability of a tool depending on the material
        """
        super().__init__(id_, max_stack = 1)
        self._tool_type = tool_type
        self._max_durability = self._durability = durability

    def get_type(self):
        """(str) Returns the type of a certain tool"""
        return self._tool_type

    def get_durability(self):
        """(int) Returns the durability of a certain tool"""
        return self._durability

    def get_max_durability(self):
        """(int) Returns the maximum (starting) durability of a certain tool"""
        return self._max_durability

    def can_attack(self):
        """(bool) Returns True if the tool has durability left, else returns False"""
        if self._durability == 0:
            return False
        else:
            return True

    def attack(self, successful : bool):
        """Deals with the decrement of the durability of a certain tool"""
        if successful == False:
            self._durability -= 1

class FoodItem(Item):
    """Food items within the sandbox game"""
    def __init__(self, id_ : str, strength : float):
        """Constructor

                Parameters:
                   id_ (str): The id representation of a certain food item
                   strength (int): The amount of healing that will be provided by a certain food item
                """
        self._strength = strength

        super().__init__(id_)

    def get_strength(self) -> float:
        """(int) Returns the the strength of a certain food item"""
        return self._strength

    def place(self):
        """Places item into the world"""
        return [('effect', ('food', self._strength))]

    def can_attack(self):
        """(bool) Returns False as food items cannot be used to attack"""
        return False

def create_block(*block_id):
    """(Block) Creates a block (this function can be thought of as a block factory)

    Parameters:
        block_id (*tuple): N-length tuple to uniquely identify the block,
        often comprised of strings, but not necessarily (arguments are grouped
        into a single tuple)
    """
    if len(block_id) == 1:
        block_id = block_id[0]
        if block_id == "leaf":
            return LeafBlock()
        elif block_id == "crafting_table":
            return CraftingTableBlock()
        elif block_id == "furnace":
            return Furnace()
        elif block_id in CRAFTED_BLOCKS:
            return ResourceBlock(block_id, CRAFTED_BLOCKS[block_id])
        elif block_id in BREAK_TABLES:
            return ResourceBlock(block_id, BREAK_TABLES[block_id])

    elif block_id[0] == 'mayhem':
        return TrickCandleFlameBlock(block_id[1])

    raise KeyError(f"No block defined for {block_id}")

def create_item(*item_id):
    """(Item) Creates an item (this function can be thought of as a item factory)

    Parameters:
        item_id (*tuple): N-length tuple to uniquely identify the item,
        often comprised of strings, but not necessarily (arguments are grouped
        into a single tuple)

    """
    block_item = ["dirt", "stone", "wood", "wood_plank", "stone_slab", "refined_stone",
                  "crafting_table", "wool", "bed", "furnace"]

    if len(item_id) == 2:

        if item_id[0] in MATERIAL_TOOL_TYPES and item_id[1] in TOOL_DURABILITIES:
            item_type, item_material = item_id
            return ToolItem(f"{item_material}_{item_type}", item_material, TOOL_DURABILITIES[item_material])

    elif len(item_id) == 1:

        item_type = item_id[0]

        if item_type == "hands":
            return HandItem("hands")

        elif item_type == "honey":
            return FoodItem(item_type, 5)

        elif item_type in block_item:
            return BlockItem(item_type)

        elif item_type == "apple":
            return FoodItem(item_type, 2)

        elif item_type == "stick":
            return SimpleItem(item_type)

        elif item_type == "cooked_apple":
            return FoodItem(item_type, 4)

    raise KeyError(f"No item defined for {item_id}")

# All recipes for crafting and cooking/smelting
CRAFTING_RECIPES_2x2 = [
    (
        (
            (None, None),
            ('wood', None)
        ),
        Stack(create_item('wood_plank'), 4)
    ),
    (
        (
            ('stone', 'stone'),
            (None, None)
        ),
        Stack(create_item('stone_slab'), 2)
    ),
    (
        (
            ('stone', 'stone'),
            ('stone', 'stone')
        ),
        Stack(create_item('refined_stone'), 1)
    ),
    (
        (
            ('wood', None),
            ('wood', None)
        ),
        Stack(create_item('stick'), 4)
    ),
    (
        (
            ('wood', 'wood'),
            ('wood', 'wood')
        ),
        Stack(create_item('crafting_table'), 1)
    )

]
CRAFTING_RECIPES_3x3 = [
    (
        (
            ('stone', 'stone', 'stone'),
            ('stone', None, 'stone'),
            ('stone', 'stone', 'stone')
        ),
        Stack(create_item('furnace'), 1)
    ),
    (
        (
            ("wood", "wood", "wood"),
            (None , "stick", None),
            (None, "stick", None)
        ),
        Stack(create_item("pickaxe", "wood"), 1)
    ),
    (
        (
            ("wood", "wood", None),
            ("wood" , "stick", None),
            (None, "stick", None)
        ),
        Stack(create_item("axe", "wood"), 1)
    ),
    (
        (
            ("wool", "wool", "wool"),
            ("wood" , "wood", "wood"),
            (None, None, None)
        ),
        Stack(create_item("axe", "wood"), 1)
    )

]

FURNACE_RECIPE = [
    (
        (
            ("apple",),
            (None,),
            ("wood",),
        ),
        Stack(create_item("cooked_apple"), 1)
    )

]

class Statusview(tk.Frame):
    """Shows the player's health/food (status) within the sandbox game"""
    def __init__(self, master, player):
        """Constructor

                Parameters:
                    master (tk.Tk): tkinter root widget
                    player(instance): The player object
                """
        super().__init__(master)
        self._player = player

        # All tkinter widgets needed to show the player's status
        self._heart = tk.PhotoImage(file="heart.ppm")
        self._chicken = tk.PhotoImage(file="chicken.ppm")

        self._heart_view = tk.Label(self, image=self._heart)
        self._heart_view.pack(side = tk.LEFT)

        self._label_health = tk.Label(self, text=f"Health: {self._player.get_health()}")
        self._label_health.pack(side=tk.LEFT, expand=True)

        self._chicken_view = tk.Label(self, image=self._chicken)
        self._chicken_view.pack(side = tk.LEFT)

        self._label_food = tk.Label(self, text = f"Food: {self._player.get_food()}")
        self._label_food.pack(side=tk.LEFT, expand=True)

    def set_food(self, food):
        """Change the player's food status and updates statusview"""
        self._player.change_food(food)
        self._label_food.configure(text = f"Food: {self._player.get_food()}")

    def set_health(self, health):
        """Change the player's health status and updates statusview"""
        self._player.change_health(health)
        self._label_health.configure(text = f"Health: {self._player.get_health()}")

    def update_view(self):
        """Updates statusview only"""
        self._label_food.configure(text=f"Food: {round(self._player.get_food()*2) / 2}")
        self._label_health.configure(text=f"Health: {round(self._player.get_health()*2) / 2}")

def load_simple_world(world):
    """Loads blocks and mobs into a world

    Parameters:
        world (World): The game world to load with blocks
    """
    block_weights = [
        (100, 'dirt'),
        (30, 'stone'),
    ]

    cells = {}

    ground = []

    width, height = world.get_grid_size()

    for x in range(width):
        for y in range(height):
            if x < 22:
                if y <= 8:
                    continue
            else:
                if x + y < 30:
                    continue

            ground.append((x, y))

    weights, blocks = zip(*block_weights)
    kinds = random.choices(blocks, weights=weights, k=len(ground))

    for cell, block_id in zip(ground, kinds):
        cells[cell] = create_block(block_id)

    # Loads Tree
    trunks = [(3, 8), (3, 7), (3, 6), (3, 5)]

    for trunk in trunks:
        cells[trunk] = create_block('wood')

    leaves = [(3, 3), (2, 3), (3, 2), (4, 3), (2, 2), (4, 4), (3, 4), (2, 4)]

    for leaf in leaves:
        cells[leaf] = create_block('leaf')

    for cell, block in cells.items():
        # cell -> box
        i, j = cell

        world.add_block_to_grid(block, i, j)

    # Load starting hives, honey, mayhem blocks and mobs
    world.add_block_to_grid(create_block("honey"), 4, 2)
    world.add_block_to_grid(create_block("hive"), 2, 5)
    world.add_block_to_grid(create_block("hive"), 4, 5)

    world.add_block_to_grid(create_block("mayhem", 0), 14, 8)

    world.add_mob(Bird("friendly_bird", (12, 12)), 400, 100)

    world.add_mob(Sheep("Sheep", (40, 25)), 600, 270)

    world.add_mob(Bee("Bee", (5, 5)), 500, 275)

class Ninedraft:
    """High-level app class for Ninedraft, a 2d sandbox game"""

    def __init__(self, master):
        """Constructor

        Parameters:
            master (tk.Tk): tkinter root widget
        """

        self._master = master
        self._master.title("Ninedraft")
        self._world = World((GRID_WIDTH, GRID_HEIGHT), BLOCK_SIZE)

        self._player = Player()
        self._world.add_player(self._player, 250, 150)

        self._world.add_collision_handler("player", "item", on_begin=self._handle_player_collide_item)
        self._world.add_collision_handler("player", "mob", on_begin=self._handle_player_collision_bees)

        load_simple_world(self._world)
        self._hot_bar = SelectableGrid(rows=1, columns=10)
        self._hot_bar.select((0, 0))

        starting_hotbar = [
            Stack(create_item("dirt"), 20),
            Stack(create_item("apple"), 4),
            Stack(create_item("furnace"), 1),
            Stack(create_item("stone"), 20),
        ]

        for i, item in enumerate(starting_hotbar):
            self._hot_bar[0, i] = item

        self._hands = create_item('hands')

        starting_inventory = [
            ((1, 5), Stack(Item('dirt'), 10)),
            ((0, 2), Stack(Item('wood'), 10)),
        ]

        self._inventory = Grid(rows=3, columns=10)
        for position, stack in starting_inventory:
            self._inventory[position] = stack

        self._crafting_window = None
        self._master.bind("e",
                          lambda e: self.run_effect(('crafting', 'basic')))

        self._view = GameView(master, self._world.get_pixel_size(), Router(BLOCK_COLOURS, ITEM_COLOURS))
        self._view.pack()

        # Mouse Controls
        self._view.bind("<Motion>", self._mouse_move)
        self._view.bind("<Leave>", self._mouse_leave)
        self._view.bind("<Button-1>", self._left_click)
        self._view.bind("<Button-3>", self._right_click)

        # Statusview instance
        self._statusview = Statusview(self._master, self._player)
        self._statusview.pack(side=tk.TOP)
        self._reset_player = True

        self._player_food_max = False
        self._gain_food = False
        self._toggle_craft = False
        self._crafter_view = None

        self._hot_bar_view = ItemGridView(master, self._hot_bar.get_size())
        self._hot_bar_view.pack(side=tk.TOP, fill=tk.X)

        # Keyboard Controls
        self._master.bind("<space>", lambda e: self._jump())

        self._master.bind("a", lambda e: self._move(-1, 0))
        self._master.bind("<Left>", lambda e: self._move(-1, 0))
        self._master.bind("d", lambda e: self._move(1, 0))
        self._master.bind("<Right>", lambda e: self._move(1, 0))
        self._master.bind("s", lambda e: self._move(0, 1))
        self._master.bind("<Down>", lambda e: self._move(0, 1))

        for key in range(10):
            self._master.bind(str((key + 1) % 10), lambda e, i = key: self._activate_item(i))

        # File Menus & Dialogs
        self._menu = tk.Menu(master)
        filemenu = tk.Menu(self._menu, tearoff = 0)
        filemenu.add_command(label="New Game", command = self.restart)
        filemenu.add_command(label="Exit", command = self.quit)
        self._menu.add_cascade(label="File", menu = filemenu)
        self._master.config(menu = self._menu)

        self._target_in_range = False
        self._target_position = 0, 0

        self.redraw()

        self.step()

    def reset_inventory(self):
        "Resets the player's inventory to the starting inventory"
        starting_inventory = [
            ((1, 5), Stack(Item('dirt'), 10)),
            ((0, 2), Stack(Item('wood'), 10)),
        ]
        self._inventory = Grid(rows=3, columns=10)
        for position, stack in starting_inventory:
            self._inventory[position] = stack

    def reset_hot_bar(self):
        "Resets the player's hot bar to the starting hotbar"
        self._hot_bar = SelectableGrid(rows=1, columns=10)
        self._hot_bar.select((0, 0))

        starting_hotbar = [
            Stack(create_item("dirt"), 20),
            Stack(create_item("apple"), 4),
        ]

        for i, item in enumerate(starting_hotbar):
            self._hot_bar[0, i] = item

    def reset_player(self):
        """Resets player's food and health (status)"""
        self._player.change_health(20)
        self._player.change_food(20)

    def restart(self):
        """Resets the whole game"""
        self._world = World((GRID_WIDTH, GRID_HEIGHT), BLOCK_SIZE)

        self._player = Player()
        self._world.add_player(self._player, 250, 150)

        load_simple_world(self._world)

        self.reset_inventory()
        self.reset_hot_bar()
        self._reset_player = True

    def quit(self):
        """Prompts the user to verify they want to quit.
           Quits is the user presses "yes" otherwise goes back to the game """
        msg_box = tk.messagebox.askquestion("Exit Application", "Are you sure you want to exit?", icon = "warning")
        if msg_box == 'yes':
            self._master.destroy()

    def player_dead(self):
        """Notifies the player that their character has died and asks if they would like to restart"""
        msg_box = tk.messagebox.askquestion("DEAD!", "Oopsies, Your player died. Would you like to restart?", icon="warning")
        if msg_box == 'yes':
            self.restart()
        else:
            self._master.destroy()

    def redraw(self):
        """Handles all visual updates"""
        self._view.delete(tk.ALL)

        # physical things
        self._view.draw_physical(self._world.get_all_things())

        # target
        target_x, target_y = self._target_position
        target = self._world.get_block(target_x, target_y)
        cursor_position = self._world.grid_to_xy_centre(*self._world.xy_to_grid(target_x, target_y))

        # Target show
        if self._target_in_range:
            self._view.show_target(self._player.get_position(), cursor_position)
        else:
            self._view.hide_target()

        # Statusview update
        if self._reset_player:
            self._statusview.set_health(20)
            self._statusview.set_food(20)
            self._reset_player = False

        self._statusview.update_view()

        # hot bar
        self._hot_bar_view.render(self._hot_bar.items(), self._hot_bar.get_selected())

    def step(self):
        """Advances the game by one step"""
        data = GameData(self._world, self._player)
        self._world.step(data)
        self.redraw()

        # Handles player death
        if self._player.get_health() == 0:
            self.player_dead()

        self._master.after(15, self.step)

    def _move(self, dx, dy):
        """Handles the movement of player (Arrow keys or W, A, S, D keys)"""
        velocity = self._player.get_velocity()
        self.check_target()
        self._player.set_velocity((velocity.x + dx * 80, velocity.y + dy * 80))

    def _jump(self):
        """Handles space bar actions (Jumping)"""
        velocity = self._player.get_velocity()
        self.check_target()

        x, y = velocity
        if x < 0:
            self._player.set_velocity((x + 50, -200))
        elif x > 0:
            self._player.set_velocity((x - 50, -200))
        else:
            self._player.set_velocity((0, -200))

    def mine_block(self, block, x, y):
        """Mines the block (block) that is in the (x, y) coordinates"""
        luck = random.random()

        active_item, effective_item = self.get_holding()

        was_item_suitable, was_attack_successful = block.mine(effective_item, active_item, luck)

        effective_item.attack(was_attack_successful)

        if block.is_mined():
            # Decrease player's food when mining
            player_food = self._player.get_food()
            if player_food == 0:
                self._player.change_health(-0.5)
            else:
                self._player.change_food(-0.1)

            # Removes block when mined and gets its drops
            self._world.remove_block(block)

            x0, y0 = block.get_position()

            # When hives are mined they spawn bees!
            if block.get_id() == "hive":
                for i in range(5):
                    self._world.add_mob(Bee("Bee", (5, 5)), x0 - i, y0 + i)

            else:
                drops = block.get_drops(luck, was_item_suitable)

                if not drops:
                    return

                for i, (drop_category, drop_types) in enumerate(drops):
                    print(f'Dropped {drop_category}, {drop_types}')

                    if drop_category == "item":
                        physical = DroppedItem(create_item(*drop_types))

                        x = x0 - BLOCK_SIZE // 2 + 5 + (i % 3) * 11 + random.randint(0, 2)
                        y = y0 - BLOCK_SIZE // 2 + 5 + ((i // 3) % 3) * 11 + random.randint(0, 2)

                        self._world.add_item(physical, x, y)
                    elif drop_category == "block":
                        self._world.add_block(create_block(*drop_types), x, y)
                    else:
                        raise KeyError(f"Unknown drop category {drop_category}")

    def get_holding(self):
        """Returns the item that the player is using"""
        active_stack = self._hot_bar.get_selected_value()
        active_item = active_stack.get_item() if active_stack else self._hands

        effective_item = active_item if active_item.can_attack() else self._hands

        return active_item, effective_item

    def check_target(self):
        """Checks if target is in range"""
        # select target block, if possible
        active_item, effective_item = self.get_holding()

        pixel_range = active_item.get_attack_range() * self._world.get_cell_expanse()

        self._target_in_range = positions_in_range(self._player.get_position(),
                                                   self._target_position,
                                                   pixel_range)

    def _mouse_move(self, event):
        """Handles mouse movement events"""
        self._target_position = event.x, event.y
        self.check_target()

    def _mouse_leave(self, event):
        """Handles the event where mouse leaves window"""
        self._target_in_range = False

    def mob_drops(self, mobs, is_sheep):
        """Places mob drops into the world"""
        luck = random.random()

        drops = mobs.get_drops(luck)

        x0, y0 = mobs.get_position()

        mob_dead = mobs.is_dead()

        if is_sheep == False and mob_dead:
            self._world.remove_mob(mobs)

        if drops is None:
            return

        if mob_dead:
            for i, (drop_category, drop_types) in enumerate(drops):
                print(f'Dropped {drop_category}, {drop_types}')

                if drop_category == "item":
                    physical = DroppedItem(create_item(drop_types))
                    # The drops are placed next to the mobs...
                    x = x0 - 10
                    y = y0
                    self._world.add_item(physical, x, y)
                else:
                    raise KeyError(f"Unknown drop category {drop_category}")

    def mob_attack(self, mob):
        """Damages a certain mob (mob)"""
        mobs = mob[0]
        is_sheep = None
        damage = -20

        if mobs.get_id() == "Sheep":
            is_sheep = True
        else:
            mobs.take_damage(damage)
            print(f"Did {damage} damage to {mobs})")
            is_sheep = False

        self.mob_drops(mobs, is_sheep)


    def _left_click(self, event):
        "Handles all left click (mouse) events"
        # Invariant: (event.x, event.y) == self._target_position
        #  => Due to mouse move setting target position to cursor
        x, y = self._target_position

        if self._target_in_range:
            block = self._world.get_block(x, y)
            mob = self._world.get_mobs(x, y, 10)
            if block:
                self.mine_block(block, x, y)
            elif mob != []:
                self.mob_attack(mob)
            else:
                pass

    def _trigger_crafting(self, craft_type):
        """Triggers the crafting windows depending on craft_type also handles toggling of craft window"""
        if self._toggle_craft == False:
            if craft_type == "basic":
                crafter = GridCrafter(CRAFTING_RECIPES_2x2)
                self._crafter_view = CraftingWindow(self._master, "Basic Crafter", self._hot_bar, self._inventory, crafter)
                self._toggle_craft = True
            elif craft_type == "crafting_table":
                crafter = GridCrafter(CRAFTING_RECIPES_3x3, 3, 3)
                self._crafter_view = CraftingWindow(self._master, "Crafting Table", self._hot_bar, self._inventory, crafter)
            elif craft_type == "furnace":
                crafter = GridCrafter(FURNACE_RECIPE, 3, 1)
                self._crafter_view = CraftingWindow(self._master, "Furnace", self._hot_bar, self._inventory, crafter)

        elif self._toggle_craft:
            self._crafter_view.destroy()
            self._toggle_craft = False

    def run_effect(self, effect):
        """Handles the effects (effect) of right click actions on certain blocks and items"""
        if len(effect) == 2:
            if effect[0] == "crafting":
                # Handles all the activation of crafting/furnace
                craft_type = effect[1]

                if craft_type == "basic":
                    print("Can't craft much with 2x2")

                elif craft_type == "crafting_table":
                    print("Let's get our kraft® on! King of the brands")

                self._trigger_crafting(craft_type)
                return
            elif effect[0] == "furnace":
                print("Let's get cooking")

                self._trigger_crafting('furnace')
                return
            elif effect[0] in ("food", "health"):
                # Handles the changing of player's food/health due to fooditems
                stat, strength = effect
                print(f"Gaining {strength} {stat}!")

                if self._player.get_food() == 20:
                    stat = "health"
                else:
                    stat = "food"

                getattr(self._player, f"change_{stat}")(strength)

                return

        raise KeyError(f"No effect defined for {effect}")

    def _right_click(self, event):
        """Handles all right click (mouse) events"""
        print("Right click")

        x, y = self._target_position
        target = self._world.get_thing(x, y)


        if target:
            # use this thing
            print(f'using {target}')
            effect = target.use()
            print(f'used {target} and got {effect}')

            if effect:
                self.run_effect(effect)

        elif self._target_in_range:
            # place active item
            selected = self._hot_bar.get_selected()

            if not selected:
                return

            stack = self._hot_bar[selected]

            if stack is not None:
                drops = stack.get_item().place()
                stack.subtract(1)

                if stack.get_quantity() == 0:
                    # remove from hotbar
                    self._hot_bar[selected] = None

            if not drops:
                return

            # handling multiple drops would be somewhat finicky, so prevent it
            if len(drops) > 1:
                raise NotImplementedError("Cannot handle dropping more than 1 thing")

            drop_category, drop_types = drops[0]

            x, y = event.x, event.y

            if drop_category == "block":
                existing_block = self._world.get_block(x, y)

                if not existing_block:
                    self._world.add_block(create_block(drop_types[0]), x, y)
                else:
                    raise NotImplementedError(
                        "Automatically placing a block nearby if the target cell is full is not yet implemented")

            elif drop_category == "effect":
                self.run_effect(drop_types)

            else:
                raise KeyError(f"Unknown drop category {drop_category}")

    def _activate_item(self, index):
        """Toggles hot bar depending on the key pressed (index)"""
        print(f"Activating {index}")

        self._hot_bar.toggle_selection((0, index))

    def _handle_player_collide_item(self, player: Player, dropped_item: DroppedItem, data,
                                    arbiter: pymunk.Arbiter):
        """Callback to handle collision between the player and a (dropped) item. If the player has sufficient space in
        their to pick up the item, the item will be removed from the game world.

        Parameters:
            player (Player): The player that was involved in the collision
            dropped_item (DroppedItem): The (dropped) item that the player collided with
            data (dict): data that was added with this collision handler (see data parameter in
                         World.add_collision_handler)
            arbiter (pymunk.Arbiter): Data about a collision
                                      (see http://www.pymunk.org/en/latest/pymunk.html#pymunk.Arbiter)
                                      NOTE: you probably won't need this
        Return:
             bool: False (always ignore this type of collision)
                   (more generally, collision callbacks return True iff the collision should be considered valid; i.e.
                   returning False makes the world ignore the collision)
        """

        item = dropped_item.get_item()

        if self._hot_bar.add_item(item):
            print(f"Added 1 {item!r} to the hotbar")
        elif self._inventory.add_item(item):
            print(f"Added 1 {item!r} to the inventory")
        else:
            print(f"Found 1 {item!r}, but both hotbar & inventory are full")
            return True

        self._world.remove_item(dropped_item)
        return False

    def _handle_player_collision_bees(self, player: Player, dropped_item: Mob, data, arbiter: pymunk.Arbiter):
        """Callback to handle collision between the player mobs. If the player comes in contact with
            bees then the player will take damage."""

        if dropped_item.get_id() == "Bee":
            self._player.change_health(-0.5)
            return True
        else:
            return True

class CraftingTableBlock(ResourceBlock):
    """Crafting tables, very useful for crafting advanced items"""
    def __init__(self):
        """Constructor"""
        super().__init__("crafting_table", {
        "hand": (3, False),
        "wood_axe": (2, True),
        "stone_axe": (1, True),
        "golden_axe": (0.6, True),
        "iron_axe": (0.5, True),
        "diamond_axe": (0.1, True)})

    def use(self):
        """Uses the crafting table"""
        return ('crafting', 'crafting_table')

    def get_drops(self, luck, correct_item_used):
        """Drops a form of itself when mined with correct tool"""
        if correct_item_used:
            return [('item', ('crafting_table',))]

class Furnace(ResourceBlock):
    """Furnaces, useful for smelting and cooking even tastier foods"""
    def __init__(self):
        """Constructor"""
        super().__init__('furnace',{
        "hand": (5, False),
        "wood_pickaxe": (2, True),
        "stone_pickaxe": (1, True),
        "golden_pickaxe": (0.6, True),
        "iron_pickaxe": (0.5, True),
        "diamond_pickaxe": (0.1, True)})

    def use(self):
        """Uses the furnace"""
        return ('furnace', 'furnace')

    def get_drops(self, luck, correct_item_used):
        """Drops a form of itself when mined with correct tool"""
        if correct_item_used:
            return [('item', ('furnace',))]

class Hive(ResourceBlock):
    """Seems innocent but has a nasty suprise inside"""
    def __init__(self, block_id, break_table):
        """Constructor
                        Parameters:
                            block_id (str): The unique id of this block
                            break_table (dict<str, tuple<float, bool>>):
                                refer to the description of break_table in block.py
        """
        super().__init__(block_id, break_table)

    def use(self):
        """Cannot use hives"""
        pass

    def get_drops(self, luck, correct_item_used):
        """Hives spawns bees however this is handled in the class NineDraft"""
        pass

# Instatiates the GUI
def main():
    root = tk.Tk()
    app = Ninedraft(root)
    root.mainloop()

if __name__ == "__main__":
    main()
