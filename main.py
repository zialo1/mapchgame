#!python
# mapchgame
# benötigt: pyshp, pygame, pygame_gui
# pip install pyshp pygame pygame_gui
# (C) 2025 Alex Hanselmann
# Lizenz: MIT
# Geo-Daten: swisstopo (swissBOUNDARIES3D)
# https://www.swisstopo.admin.ch/de/geodata/landscape/boundaries

import shapefile
import pygame
import pygame_gui
import math
import time


# -------- Konfiguration --------
SHP_PATH = "swissBOUNDARIES3D_1_5_TLM_KANTONSGEBIET.shp"
MAP_PATH = "swissmap770.png"
mappos=(29,-29)

kantone =[
'Genf',
'Thurgau',
'Wallis',
'Aargau',
'Schwyz',
'Zürich',
'Obwalden',
'Freiburg',
'Glarus',
'Uri',
'Nidwalden',
'Solothurn',
'Appenzell Ausserrhoden',
'Jura',
'Graubünden',
'Waadt',
'Luzern',
'Tessin',
'Zug',
'Baselland',
'Sankt Gallen',
'Schaffhausen',
'Bern',
'Baselstadt',
'Neuenburg',
'Appenzell Innerrhoden'
]


WINDOW_SIZE = (800, 600)
BG_COLOR = (255, 255, 255)
NORMAL_FILL = (0, 150, 200)
HOVER_FILL = (135, 206, 250)
OUTLINE = (0, 0, 0)

# Skala / Offset anpassen
SCALE = 0.002
OFFSET = (-4900, 2600)

# -------- Animation-Parameter --------
ANIM_DURATION = 0.2  # sek
SCALE_UP = 1.2
SCALE_DOWN = 1

def start_animation(shape_data, new_target):
    shape_data["anim_from"] = shape_data["current_scale"]
    shape_data["target_scale"] = new_target
    shape_data["anim_start"] = time.time()

def update_animations():
    now = time.time()
    for s in shapes_data:
        if s["anim_start"] is not None:
            t = (now - s["anim_start"]) / ANIM_DURATION
            if t >= 1.0:
                s["current_scale"] = s["target_scale"]
                s["anim_start"] = None
            else:
                # lineare Interpolation
                f = s["anim_from"] + (s["target_scale"] - s["anim_from"]) * t
                s["current_scale"] = f

def draw_shape(surface, shape_data, fill_color, bg_color=BG_COLOR):
    scale = shape_data["current_scale"]
    # Skaliere jedes Teil um seinen Schwerpunkt
    for p in shape_data["parts"]:
        if p["area"] < float('inf') and len(p["points"]) >= 3:
            cx, cy = polygon_centroid(p["points"])
            scaled_pts = [
                (cx + (x - cx) * scale, cy + (y - cy) * scale)
                for (x, y) in p["points"]
            ]
            if p["type"] == "outer":
                pygame.draw.polygon(surface, fill_color, scaled_pts, 0)
                pygame.draw.polygon(surface, OUTLINE, scaled_pts, 1)
            else:
                pygame.draw.polygon(surface, bg_color, scaled_pts, 0)
                pygame.draw.polygon(surface, OUTLINE, scaled_pts, 1)

# -------- Utility-Funktionen --------
def transform_coords(points, scale=SCALE, offset=OFFSET):
    ox, oy = offset
    return [(int(x * scale + ox), int(-y * scale + oy)) for x, y in points]

def polygon_area(poly):
    # Shoelace (gibt absolute Fläche zurück)
    area = 0.0
    n = len(poly)
    if n < 3:
        return 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0

def polygon_centroid(poly):
    # Flächen-gewichteter Schwerpunkt (kann bei sehr konkaven Formen außerhalb liegen)
    n = len(poly)
    A = 0.0
    Cx = 0.0
    Cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        A += cross
        Cx += (x0 + x1) * cross
        Cy += (y0 + y1) * cross
    A *= 0.5
    if abs(A) < 1e-8:
        # Degenerat: fallback auf Mittelwert
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    Cx /= (6.0 * A)
    Cy /= (6.0 * A)
    return (Cx, Cy)

def point_in_polygon(pt, poly):
    # Ray casting robust implementation (pt = (x,y), poly = list of (x,y))
    x, y = pt
    inside = False
    n = len(poly)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and \
                    (x < (xj - xi) * (y - yi) / (yj - yi + 1e-20) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

def find_interior_point(poly):
    # Versuche: erst Centroid, falls nicht drin -> Kanten-Mittelpunkte durchsuchen -> Fallback Mittelwert
    c = polygon_centroid(poly)
    if point_in_polygon(c, poly):
        return c
    # midpoints of edges
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        mid = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        if point_in_polygon(mid, poly):
            return mid
    # fallback: average of verts
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (sum(xs) / len(xs), sum(ys) / len(ys))

# Zeichnungsreihenfolge: größere Shapes zuerst, kleine shapes zuletzt (damit kleine oben liegen)
def shape_sort_key(s):
    outer_areas = [p["area"] for p in s["parts"] if p["type"] == "outer" and p["area"] < float('inf')]
    return min(outer_areas) if outer_areas else float('inf')

# -------- Funktionen für Hit-Testing und Zeichnen --------
def shape_min_containing_part(shape_data, point):
    """Gibt das kleinste Teil (part) im shape zurück, das den Punkt enthält (oder None)."""
    parts_containing = [p for p in shape_data["parts"] if p["points"] and point_in_polygon(point, p["points"])]
    if not parts_containing:
        return None
    return min(parts_containing, key=lambda p: p["area"])

def point_is_inside_shape(shape_data, point):
    """True wenn der Punkt in der Füllfläche (nicht in einem Loch) des Shapes liegt."""
    min_part = shape_min_containing_part(shape_data, point)
    if min_part is None:
        return False
    return (min_part["type"] == "outer")

# -------- Laden & Vorverarbeiten (einmal) --------
sf = shapefile.Reader(SHP_PATH)
raw_shapes = sf.shapes()
scale = SCALE
offset = OFFSET

shapes_data = []  # Liste mit Metadaten pro Shape
for idx, shape in enumerate(raw_shapes):
    pts = shape.points
    parts_idx = list(shape.parts) + [len(pts)]
    parts = []
    for i in range(len(parts_idx) - 1):
        s, e = parts_idx[i], parts_idx[i+1]
        ring = pts[s:e]
        scaled = transform_coords(ring, scale, offset)
        # ensure it's a closed polygon for algorithms (pyshp may or may not repeat first point)
        if len(scaled) >= 1 and scaled[0] != scaled[-1]:
            # don't force duplicate, algorithm works without explicit closure
            pass
        area = polygon_area(scaled)
        interior = find_interior_point(scaled) if area > 0 else None
        parts.append({
            "points": scaled,
            "area": area if area > 0 else float('inf'),
            "interior": interior,
            "type": None  # wird gleich bestimmt
        })

    # Klassifikation: für jedes Teil die Anzahl Eltern (wie oft liegt dessen interior in anderen Teilen)
    for i, p in enumerate(parts):
        if p["interior"] is None:
            p["type"] = "outer"  # defensiv
            continue
        parent_count = 0
        for j, q in enumerate(parts):
            if i == j: continue
            if q["points"] and point_in_polygon(p["interior"], q["points"]):
                parent_count += 1
        p["type"] = "outer" if (parent_count % 2 == 0) else "hole"

    # Fallback: wenn keine "outer" gefunden (weird data), markiere alle als outer
    if not any(p["type"] == "outer" for p in parts):
        for p in parts:
            p["type"] = "outer"

    shape_oid = getattr(shape, "oid", idx)
    shapes_data.append({
        "shape_obj": shape,
        "parts": parts,
        "oid": shape_oid
    })

# Shapes bekommen Animationsstatus
for s in shapes_data:
    s["current_scale"] = 1
    s["target_scale"] = 1
    s["anim_start"] = None
    s["anim_from"] = 1

selected_shape = None
shapes_data.sort(key=shape_sort_key)  # kleine oben (werden später gezeichnet)

# -------- Pygame / GUI Setup --------
pygame.init()
screen = pygame.display.set_mode(WINDOW_SIZE)
pygame.display.set_caption("Kennst du die Schweizer Kantone?")

manager = pygame_gui.UIManager(WINDOW_SIZE, theme_path='theme.json')

label = pygame_gui.elements.UILabel(
    relative_rect=pygame.Rect((10, WINDOW_SIZE[1] - 30), (400, 25)),
    text="Klicke auf einen Kanton",
    manager=manager
)

# Buttons nahe den vier Ecken
btn_top_left = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((30, 120), (120, 50)),
    text="Frankreich",
    manager=manager,
    object_id="#btn_tl"
)
btn_top_right = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((WINDOW_SIZE[0]-140, 120), (120, 50)),
    text="Österreich",
    manager=manager,
    object_id="#btn_tr"
)
btn_bottom_left = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((250, 0), (120, 50)),
    text="Deutschland",
    manager=manager,
    object_id="#btn_bl"
)
btn_bottom_right = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((WINDOW_SIZE[0]-240, WINDOW_SIZE[1]-200), (120, 50)),
    text="Italien",
    manager=manager,
    object_id="#btn_br"
)

# Hilfe-Button in der Mitte
btn_help = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((WINDOW_SIZE[0]-140, 120), (120, 50)),
    text="Liechtenstein",
    manager=manager,
    object_id="#btn_help"
)

# Textbox für Hilfe (zuerst versteckt)
help_box = None

# Alte Standardgröße
BASE_FONT_SIZE = 28

# Neues Label für OID in der Mitte
mid_label = pygame_gui.elements.UILabel(
    relative_rect=pygame.Rect((-1000, -1000), (200, int(BASE_FONT_SIZE*1.4))),
    text="",
    manager=manager,
    object_id = pygame_gui.core.ObjectID(class_id='@friendly',
                     object_id='#hello_button')
#    text_color=(0, 100, 0),          # dunkelgrün
#    font_size=int(BASE_FONT_SIZE * 1.4)  # 1.4x größer
)

# Schriftgröße über den Font-Manager anpassen (falls nötig)
#mid_label.set_font(pygame.font.SysFont(None, int(BASE_FONT_SIZE * 1.4)))

mapimg=pygame.image.load(MAP_PATH)

clock = pygame.time.Clock()
selected_oid = None


# -------- Hauptschleife --------
running = True
while running:
    time_delta = clock.tick(60) / 1000.0

    events = pygame.event.get()
    for event in events:
        if event.type == pygame.QUIT:
            running = False

        manager.process_events(event)

        # -------- Klick-Handler anpassen --------
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            click_pos = event.pos

            if False and event.ui_element in [btn_top_left, btn_top_right, btn_bottom_left, btn_bottom_right]:
                # Alle Buttons außer den geklickten verschwinden
                for btn in [btn_top_left, btn_top_right, btn_bottom_left, btn_bottom_right]:
                    if btn != event.ui_element:
                        btn.hide()

            elif False and event.ui_element == btn_help:
                if help_box is None:
                    # Textbox einblenden
                    help_box = pygame_gui.elements.UITextBox(
                        html_text="<b>Hilfe:</b><br>"
                                  "Klicke auf einen Eck-Button,<br>"
                                  "um die anderen auszublenden.<br><br>"
                                  "Der Hilfe-Button blendet diesen Text ein.",
                        relative_rect=pygame.Rect((200, 150), (400, 300)),
                        manager=manager
                    )
                else:
                    # Wenn schon vorhanden, toggeln
                    if help_box.visible:
                        help_box.hide()
                    else:
                        help_box.show()



            candidates = []
            for s in shapes_data:
                min_part = shape_min_containing_part(s, click_pos)
                if min_part and min_part["type"] == "outer":
                    candidates.append((s, min_part["area"]))

            if candidates:
                chosen_shape = min(candidates, key=lambda c: c[1])[0]

                # altes Shape zurückskalieren
                if selected_shape and selected_shape is not chosen_shape:
                    start_animation(selected_shape, SCALE_DOWN)

                # neues Shape hochskalieren
                selected_shape = chosen_shape
                start_animation(chosen_shape, SCALE_UP)

                # Label-Text setzen
                selected_oid = chosen_shape["oid"]
                mid_label.set_text(f"{kantone[selected_oid]}")

                # Label in die Mitte des Shapes verschieben
                # Berechne Durchschnitt aller Centroids der outer-parts
                outer_centroids = [polygon_centroid(p["points"]) for p in chosen_shape["parts"] if p["type"] == "outer"]
                if outer_centroids:
                    avg_x = sum(c[0] for c in outer_centroids) / len(outer_centroids)
                    avg_y = sum(c[1] for c in outer_centroids) / len(outer_centroids)
                    # Label verschieben
                    mid_label.set_relative_position((avg_x - mid_label.rect.width // 2,
                                                     avg_y - mid_label.rect.height // 2))

    # Hover: finde oberstes Shape unter Maus (kleinstes enthaltendes outer-Teil)
    mouse_pos = pygame.mouse.get_pos()
    hover_candidate = None
    hover_area = None
    for s in shapes_data:
        min_part = shape_min_containing_part(s, mouse_pos)
        if min_part and min_part["type"] == "outer":
            if hover_candidate is None or min_part["area"] < hover_area:
                hover_candidate = s
                hover_area = min_part["area"]

    # Zeichnen (Shapes in sortierter Reihenfolge)

    screen.fill(BG_COLOR)
    screen.blit(mapimg, mappos)
    for s in shapes_data:
        if s is hover_candidate:
            draw_shape(screen, s, HOVER_FILL, BG_COLOR)
        else:
            draw_shape(screen, s, NORMAL_FILL, BG_COLOR)
    if selected_shape:
        draw_shape(screen, selected_shape, HOVER_FILL, BG_COLOR)

    # Label: falls ausgewählt, bleibt Sichtbar (pygame_gui bringt es auf den Screen)
    manager.update(time_delta)
    manager.draw_ui(screen)
    update_animations()
    pygame.display.flip()

pygame.quit()
