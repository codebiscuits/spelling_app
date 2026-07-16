import os
from datetime import datetime
from fastapi.templating import Jinja2Templates

PALETTES = [
    {"name": "Monday",    "colours": ["#FF6B6B", "#FFE66D", "#4ECDC4", "#45B7D1", "#96CEB4"]},
    {"name": "Tuesday",   "colours": ["#A8E6CF", "#DCEDC1", "#FFD3B6", "#FFAAA5", "#FF8B94"]},
    {"name": "Wednesday", "colours": ["#6C5CE7", "#A29BFE", "#FD79A8", "#FDCB6E", "#00CEC9"]},
    {"name": "Thursday",  "colours": ["#E17055", "#D63031", "#FDCB6E", "#00B894", "#0984E3"]},
    {"name": "Friday",    "colours": ["#FFC8DD", "#FFAFCC", "#BDE0FE", "#A2D2FF", "#CDB4DB"]},
    {"name": "Saturday",  "colours": ["#F9C74F", "#F8961E", "#F3722C", "#F94144", "#90BE6D"]},
    {"name": "Sunday",    "colours": ["#48CAE4", "#90E0EF", "#ADE8F4", "#CAF0F8", "#023E8A"]},
]

MINI_GAMES = [
    {"file": "circles.html",       "name": "Circles",       "description": "Satisfying bouncing circles", "tier": "classic"},
    {"file": "fireworks.html",     "name": "Fireworks",     "description": "Colourful fireworks display", "tier": "classic"},
    {"file": "gravity-balls.html", "name": "Gravity Balls", "description": "Balls with gravity physics", "tier": "classic"},
    {"file": "lightning.html",     "name": "Lightning",     "description": "Electric lightning effects", "tier": "classic"},
    {"file": "metaballs.html",     "name": "Metaballs",     "description": "Wobbly metaball shapes", "tier": "classic"},
    {"file": "particles.html",     "name": "Particles",     "description": "Particle fountain", "tier": "classic"},
    {"file": "starfield.html",     "name": "Starfield",     "description": "Fly through the stars", "tier": "classic"},
    {"file": "worms.html",         "name": "Generative Worms", "description": "Wriggly worms", "tier": "classic"},
    {"file": "flow.html",          "name": "Generative Flow", "description": "Flowing particles", "tier": "classic"},
    {"file": "ink_drops.html",     "name": "Ink Drops",     "description": "Fluid diffusion blobs", "tier": "classic"},
    {"file": "worm_trails.html",   "name": "Worm Trails",   "description": "Organic, snake-like motion", "tier": "classic"},
    {"file": "magnetic_lines.html","name": "Magnetic Field Lines", "description": "Particles aligning to invisible forces", "tier": "classic"},
    {"file": "gravity_well.html",  "name": "Gravity Well",  "description": "Particles orbit your cursor", "tier": "classic"},
    {"file": "cloth.html",         "name": "Cloth",         "description": "Tear and blow a colourful fabric", "tier": "classic"},
    {"file": "boids.html",         "name": "Boids",         "description": "A flocking swarm with food and predators", "tier": "classic"},
    {"file": "lava_lamp.html",     "name": "Lava Lamp",     "description": "Gooey blobs rising and sinking", "tier": "classic"},
    {"file": "sand.html",          "name": "Sand",          "description": "Pour sand and water", "tier": "classic"},
    {"file": "liquid_pour.html",   "name": "Liquid Pour",   "description": "Pour water and build platforms", "tier": "classic"},
    {"file": "orbits.html",        "name": "Orbits",        "description": "Place planets and watch them orbit", "tier": "classic"},
    {"file": "smoke.html",         "name": "Smoke",         "description": "Swirling smoke with deflectors", "tier": "classic"},
    {"file": "circles_2.html",     "name": "Circles 2",     "description": "Colourful circles that react to your mouse", "tier": "classic"},
    {"file": "ball_pit.html",      "name": "Ball Pit",      "description": "Physics sandbox — spawn, throw and explode balls", "tier": "classic"},
    {"file": "jelly.html",         "name": "Jelly Buddies", "description": "Squishy soft-body blobs to poke and fling", "tier": "classic"},
    {"file": "lens_lab.html",      "name": "Lens Lab",      "description": "Drag magical lenses to bend light into kaleidoscopes", "tier": "classic"},

    {"file": "pond.html",          "name": "Pond",          "description": "Ripple the water, splash rain and float ducks", "tier": "reward", "release_order": 1},
    {"file": "puppet_pets.html",   "name": "Puppet Pets",   "description": "Drag slinky crayon creatures around", "tier": "reward", "release_order": 2},
    {"file": "ink_garden.html",    "name": "Ink Garden",    "description": "Paint with swirling living ink", "tier": "reward", "release_order": 3},
    {"file": "mandala.html",       "name": "Mandala Maker", "description": "Every scribble becomes a glowing rose window", "tier": "reward", "release_order": 4},
    {"file": "firefly_field.html", "name": "Firefly Field", "description": "Watch fireflies learn to blink together", "tier": "reward", "release_order": 5},
    {"file": "big_dig.html",       "name": "Big Dig",       "description": "Dig and pour sand, water, plants and fire", "tier": "reward", "release_order": 6},
    {"file": "goo_lamp.html",      "name": "Goo Lamp",      "description": "Heat gooey blobs that merge, split and rise", "tier": "reward", "release_order": 7},
    {"file": "shadow_maze.html",   "name": "Shadow Maze",   "description": "Explore a dark maze with your lantern", "tier": "reward", "release_order": 8},
    {"file": "splash_bath.html",   "name": "Splash Bath",   "description": "Pour and splash real sloshing water", "tier": "reward", "release_order": 9},
    {"file": "particle_life.html", "name": "Particle Life Zoo", "description": "Tiny creatures that chase, flee and self-organise", "tier": "reward", "release_order": 10},
    {"file": "fireflies.html",     "name": "Firefly Playground", "description": "Conduct a meadow of fireflies learning to blink as one", "tier": "reward", "release_order": 11},
    {"file": "reaction_diffusion.html", "name": "Pattern Grower", "description": "Grow coral and leopard patterns under your cursor", "tier": "reward", "release_order": 12},
    {"file": "wrecking_yard.html", "name": "Wrecking Yard", "description": "Swing a wrecking ball and smash towers", "tier": "reward", "release_order": 13},
    {"file": "topple_tower.html",  "name": "Topple Tower",  "description": "Topple a block tower with explosions and gravity wells", "tier": "reward", "release_order": 14},
]

REWARD_GAMES = sorted(
    [g for g in MINI_GAMES if g["tier"] == "reward"],
    key=lambda g: g["release_order"],
)
CLASSIC_GAMES = [g for g in MINI_GAMES if g["tier"] == "classic"]


def current_palette():
    return PALETTES[datetime.today().weekday()]


def static_version(path: str) -> str:
    """Returns the file mtime as a cache-busting version string."""
    try:
        return str(int(os.path.getmtime(os.path.join("static", path))))
    except OSError:
        return "0"


templates = Jinja2Templates(directory="templates")
templates.env.globals["current_palette"] = current_palette
templates.env.globals["static_version"] = static_version
