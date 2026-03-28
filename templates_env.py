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
    {"file": "circles.html",       "name": "Circles",       "description": "Satisfying bouncing circles"},
    {"file": "fireworks.html",     "name": "Fireworks",     "description": "Colourful fireworks display"},
    {"file": "gravity-balls.html", "name": "Gravity Balls", "description": "Balls with gravity physics"},
    {"file": "lightning.html",     "name": "Lightning",     "description": "Electric lightning effects"},
    {"file": "metaballs.html",     "name": "Metaballs",     "description": "Wobbly metaball shapes"},
    {"file": "particles.html",     "name": "Particles",     "description": "Particle fountain"},
    {"file": "starfield.html",     "name": "Starfield",     "description": "Fly through the stars"},
    {"file": "worms.html",         "name": "Generative Worms", "description": "Wriggly worms"},
    {"file": "flow.html",          "name": "Generative Flow", "description": "Flowing particles"},
    {"file": "ink_drops.html", "name": "Ink Drops", "description": "Fluid diffusion blobs"},
    {"file": "worm_trails.html", "name": "Worm Trails", "description": "Organic, snake-like motion"},
    {"file": "magnetic_lines.html", "name": "Magnetic Field Lines", "description": "Particles aligning to invisible forces"},
]


def current_palette():
    return PALETTES[datetime.today().weekday()]


templates = Jinja2Templates(directory="templates")
templates.env.globals["current_palette"] = current_palette
