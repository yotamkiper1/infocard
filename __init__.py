
import bpy, blf, gpu, math, os, re, sys, time
from collections import OrderedDict
from gpu_extras.batch import batch_for_shader
from . import catalog
import importlib
importlib.reload(catalog)  # pick up new cards when the add-on is turned off and on

PICS = os.path.join(os.path.dirname(__file__), "pics")
MENU_HOOKS = True  # the store build sets this to False

_reported = set()


def _report(where, e):
    """Print each different error once (so real breakage shows in the console without flooding it)."""
    k = (where, type(e).__name__, str(e))
    if k not in _reported and len(_reported) < 200:
        _reported.add(k)
        print(f"Infocard: {where}: {type(e).__name__}: {e}")


# ------------------------------------------------------------------ where the pictures are
# The packaged add-on ships pics/index.json: picture name (like "props/x_hi") -> [file, frames].
# A clip (frames > 0) is one file with its frames side by side. Identical pictures share one file.
# Without index.json (a folder of loose .png/.jpg/.webp files, as while making cards) the folder is
# scanned once instead, so nothing ever checks the disk while you move the mouse.
_INDEX = None
_ABS = {}  # pictures given by full path (the Recipes add-on) -> same entry as in _INDEX
_EXTS = ("png", "jpg", "webp")


def _scan(root):
    still, frames = {}, {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            base, _, ext = f.rpartition(".")
            if ext not in _EXTS:
                continue
            rel = os.path.relpath(os.path.join(dirpath, base), root).replace(os.sep, "/")
            m = re.match(r"(.+)_f(\d+)$", rel)
            if m:
                frames.setdefault(m.group(1), {}).setdefault(int(m.group(2)), os.path.join(dirpath, f))
            elif rel not in still or _EXTS.index(ext) < _EXTS.index(still[rel].rpartition(".")[2]):
                still[rel] = os.path.join(dirpath, f)  # .png wins over .jpg over .webp, like before
    idx = {k: (p, 0) for k, p in still.items()}
    for k, fr in frames.items():
        n = 0
        while n in fr:
            n += 1
        if n:
            idx[k] = (tuple(fr[i] for i in range(n)), n)  # loose frame files
    return idx


def pics_index():
    global _INDEX
    if _INDEX is None:
        import json
        idx = {}
        try:
            with open(os.path.join(PICS, "index.json")) as f:
                d = json.load(f)
            for k, (rel, n) in d["pics"].items():
                idx[k] = (os.path.join(PICS, rel), n)
        except FileNotFoundError:
            idx = _scan(PICS)
        except Exception as e:
            _report("pics/index.json", e)
            idx = _scan(PICS)
        _INDEX = idx
    return _INDEX


def _abs_entry(name):
    """A picture given by its full path (no index): look on disk once, then remember."""
    if name in _ABS:
        return _ABS[name]
    e = None
    fr = []
    while True:
        p = next((f"{name}_f{len(fr)}.{x}" for x in _EXTS if os.path.exists(f"{name}_f{len(fr)}.{x}")), None)
        if p is None:
            break
        fr.append(p)
    if fr:
        e = (tuple(fr), len(fr))
    else:
        p = next((f"{name}.{x}" for x in _EXTS if os.path.exists(f"{name}.{x}")), None)
        e = (p, 0) if p else None
    if len(_ABS) > 2000:
        _ABS.clear()
    _ABS[name] = e
    return e


def pic_entry(name):
    """(file or tuple of frame files, number of frames) for a picture name like 'props/x_hi', or None."""
    if os.path.isabs(name):
        return _abs_entry(name)
    return pics_index().get(name)


def has_pic(name):
    return pic_entry(name) is not None


def _load_auto():
    import json
    try:
        with open(os.path.join(PICS, "auto", "auto_map.json")) as f:
            return json.load(f)
    except Exception:
        return {}


AUTO = _load_auto()  # node type -> socket id -> [picture key, low label, high label]


def _load_mods():
    import json
    try:
        with open(os.path.join(PICS, "mods", "mod_map.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_tools():
    import json
    try:
        with open(os.path.join(PICS, "tools", "tool_map.json")) as f:
            return json.load(f)
    except Exception:
        return {}


TOOLMAP = _load_tools()  # tool id -> picture key


def tool_card(tool_id, context=None):
    """Card for a toolbar tool (Move, Extrude, Knife...)."""
    label, desc = tool_id.split(".")[-1].replace("_", " ").title(), ""
    try:
        from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
        _, item, _ = ToolSelectPanelHelper._tool_get_by_id(context or bpy.context, tool_id)
        if item is not None:
            label = item.label or label
            d = item.description
            if callable(d):
                d = d(context or bpy.context, item, None)
            desc = d or ""
    except Exception:
        pass
    desc = catalog.TOOL_TEXTS.get(tool_id) or desc
    pk = TOOLMAP.get(tool_id)
    if pk and has_pic("tools/" + pk + "_hi"):
        S.auto = (label, desc, "Before", "After", "tools/" + pk)
        return "auto:tool:" + tool_id
    if not desc:
        return None
    S.text = (label, desc)
    return "__text__:tool:" + tool_id


def _load_cons():
    import json
    try:
        with open(os.path.join(PICS, "cons", "cons_map.json")) as f:
            return json.load(f)
    except Exception:
        return {}


CONSMAP = _load_cons()


def cons_card(ptr, ident):
    t = ptr.type
    pm = CONSMAP.get("_props", {}).get(t, {}).get(ident)
    if pm:
        p = ptr.bl_rna.properties.get(ident)
        _, say = ex_prop(ptr, ident)
        enum = p is not None and p.type == "ENUM"
        S.auto = (p.name if p else ident, say or (p.description if p else ""),
                  pm[1] if enum else "Low  " + pm[1], pm[2] if enum else "High  " + pm[2], "cons/" + pm[0])
        return "auto:" + pm[0]
    k = CONSMAP.get("_types", {}).get(t)
    if not k:
        return None
    item = bpy.types.Constraint.bl_rna.properties["type"].enum_items.get(t)
    d = EX_PROPS.get(type(ptr).__name__, {}).get("_") or (item.description if item else "")
    S.auto = (item.name if item else t, d, "Without", "With", "cons/" + k)
    return "auto:cons:" + t


MODMAP = _load_mods()  # "_types": {type: key}, "_props": {type: {prop: [key, lo, hi]}}


def mod_card(t, name=None):
    """Card for a whole modifier type: hand-made, else rendered, else None."""
    k = "m_" + t
    if k in catalog.CARDS:
        return k
    pk = MODMAP.get("_types", {}).get(t)
    if not pk:
        return None
    try:
        item = bpy.types.Modifier.bl_rna.properties["type"].enum_items[t]
        title, say = item.name, item.description
    except Exception:
        title, say = name or t, ""
    say = _mod_say(title) or say
    S.auto = (title, say, "Without", "With", "mods/" + pk)
    return "auto:mod:" + t


_say_cache = {}


def _mod_say(title):
    """The add-on's own sentence for a whole modifier (explain/*.json "_"), looked up once per type."""
    k = ("mod", title)
    if k not in _say_cache:
        say = None
        for struct, d in EX_PROPS.items():
            if struct.lower().replace("modifier", "") == title.lower().replace(" ", "").replace("/", "") and d.get("_"):
                say = d["_"]
                break
        _say_cache[k] = say
    return _say_cache[k]


def _cons_say(name):
    k = ("cons", name)
    if k not in _say_cache:
        say = None
        for sname, d in EX_PROPS.items():
            if sname.lower().replace("constraint", "") == name.lower().replace(" ", "") and d.get("_"):
                say = d["_"]
        _say_cache[k] = say
    return _say_cache[k]


def _load_explain():
    """Plain-language explanations written for this add-on (explain/*.json)."""
    import json, glob
    nodes, props = {}, {}
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "explain", "*.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
        except Exception as e:
            print("Infocard: bad", f, e)
            continue
        for k, v in d.items():
            if isinstance(v, dict) and "inputs" in v:
                nodes[k] = v
            elif isinstance(v, dict):
                props.setdefault(k, {}).update(v)
    return nodes, props


EX_NODES, EX_PROPS = _load_explain()
EX_PROPS.setdefault("SpaceProperties", {}).update(catalog.PROPERTIES_TABS)


def _load_props():
    import json
    try:
        with open(os.path.join(PICS, "props", "props_map.json")) as f:
            return json.load(f)
    except Exception:
        return {}


PROPMAP = _load_props()  # struct name -> prop -> [picture key, low label, high label]


def ex_prop(ptr, ident):
    rna = ptr.bl_rna
    while rna is not None:
        d = EX_PROPS.get(rna.identifier)
        if d and ident in d:
            return d, d[ident]
        rna = rna.base
    return None, None


class S:
    key = None        # card on screen
    tex = OrderedDict()  # picture file -> GPUTexture (or None if it can't be read), least recently used first
    tex_bytes = 0     # GPU memory used by S.tex
    handlers = []
    kmis = []
    log = []
    n = 0
    last_event = 0.0
    text = ("", "")
    pending = None    # card waiting for the mouse to rest
    pending_t = 0.0
    ref = None        # (data-block path, property path) under the mouse: text only, never a live pointer
    ref_val = None
    editing = False
    last_k = None
    last_tool = None
    last_tool_card = None
    node_names = {}
    tool_shown = 0.0
    tool_hook = None
    animating = False
    last_visible = 0.0
    rect = None       # where the card was drawn
    auto = None       # card data for automatic pictures
    area = 0          # editor the mouse was last in
    what = None       # last thing seen under the mouse (for checking)
    layout_edit = False


def prefs():
    a = bpy.context.preferences.addons.get(__package__)
    return a.preferences if a else None


def is_on():
    p = prefs()
    return bool(p and p.enabled)

# ------------------------------------------------------------------ what is under the mouse

def key_for(ctx):
    ptr = getattr(ctx, "button_pointer", None)
    prop = getattr(ctx, "button_prop", None)
    op = getattr(ctx, "button_operator", None)
    S.ref = None  # forget the last setting, so a value changing there can't hide this card
    if op is not None:
        try:
            if op.bl_rna.identifier == "OBJECT_OT_modifier_add":
                k = "m_" + op.type
                return k if k in catalog.CARDS else None
        except Exception:
            pass
    ident = prop.identifier if prop is not None else ""
    try:
        cp = ctx.property  # (owner, property name, index) of the setting under the mouse
    except Exception:
        cp = None
    if cp:
        ptr, ident = cp[0], cp[1]
        gn = gn_input(ptr, ident)
        if gn:
            S.what = ("GN input",) + gn
            S.ref = make_ref(ptr, ident)
            S.text = gn
            return "__text__:" + gn[0] + gn[1][:20]
        # sometimes it's a path, like nodes["Principled BSDF"].inputs[2].default_value
        if ptr is not None and ("." in ident or "[" in ident):
            head, _, ident = ident.rpartition(".")
            if head:
                try:
                    ptr = ptr.path_resolve(head)
                except Exception:
                    ptr = None
            if "[" in ident:
                ident = ident.split("[", 1)[0]
    if ptr is None:
        S.what = None
        return None
    S.what = (type(ptr).__name__, ident, getattr(getattr(ptr, "node", None), "type", ""), getattr(ptr, "type", ""))
    S.ref = make_ref(ptr, ident)
    k = picture_key(ptr, ident)
    if k:
        return k
    # no picture yet: show Blender's own explanation in the same card
    t = text_for(ptr, ident)
    if t:
        S.text = t
        return "__text__:" + t[0] + t[1][:20]
    return None


def gn_input(ptr, path):
    """Inputs of a Geometry Nodes modifier, like modifiers["Hair"]["Socket_2"]."""
    import re
    if ptr is not None and not hasattr(ptr, "modifiers") and isinstance(getattr(ptr, "id_data", None), bpy.types.Object):
        try:  # Blender 5.2+: the owner is the input itself, path "value"
            full = ptr.path_from_id()
        except Exception:
            full = ""
        if ".properties.inputs." not in full:
            return None
        path, ptr = full + "." + path, ptr.id_data
    m = re.match(r'modifiers\["(.+?)"\](?:\["|\.properties\.inputs\.)(\w+)', path or "")
    if not m or not hasattr(ptr, "modifiers"):
        return None
    md = ptr.modifiers.get(m.group(1))
    group = getattr(md, "node_group", None)
    if group is None:
        return None
    sid = m.group(2).split("_use_attribute")[0].split("_attribute_name")[0]
    for item in group.interface.items_tree:
        if getattr(item, "identifier", None) == sid:
            desc = item.description or f"A setting of {group.name}."
            return (item.name, desc)
    return None


def socket_card(sock):
    """Card for a socket you can only plug things into (no slider)."""
    k = picture_key(sock, "default_value")
    if k:
        return k
    t = text_for(sock, "default_value")
    if t:
        S.text = t
        return "__text__:sock:" + sock.node.name + sock.identifier
    return None


def node_card(node_idname, name=None):
    """Card key for a whole node: a picture card if we have one, else Blender's description."""
    k = catalog.NODES.get(node_idname)
    if k:
        return k
    rna = bpy.types.Node.bl_rna_get_subclass(node_idname)
    if rna is None:
        return None
    say = EX_NODES.get(node_idname, {}).get("node") or rna.description or ""
    nk = AUTO.get("_nodes", {}).get(node_idname)
    if nk:
        S.auto = (name or rna.name, say, "Without", "With", "auto/" + nk)
        return "auto:node:" + node_idname
    auto = AUTO.get(node_idname)
    if auto:
        sid, (pk, lo, hi) = next(iter(auto.items()))
        S.auto = (name or rna.name, say, f"Low {sid}", f"High {sid}", "auto/" + pk)
        return "auto:node:" + node_idname
    if not say:
        return None
    S.text = (name or rna.name, say)
    return "__text__:" + node_idname


ROW = 22.0     # node socket row height (in UI units, times UI scale)
PANEL_START = {"ShaderNodeBsdfPrincipled": "Diffuse Roughness"}  # first socket that sits in a fold-out panel


def socket_rows(n):
    """Where each visible socket sits in a node, as (socket, center_y in view space).
    Blender doesn't tell add-ons where sockets are drawn, so this follows its node layout."""
    s = bpy.context.preferences.system.ui_scale
    H = ROW * s
    loc = getattr(n, "location_absolute", n.location)
    top = loc.y * s
    bottom = top - n.dimensions.y
    outs = [o for o in n.outputs if o.enabled and not o.hide]
    ins = [i for i in n.inputs if i.enabled and not i.hide]
    rows = []
    y = top - 24 * s - H / 2
    for o in outs:
        rows.append((o, y))
        y -= H

    def h(sock):
        if sock.type == "VECTOR" and not sock.is_linked and not sock.hide_value:
            return 4
        return 1
    need = (24 * s + H * len(outs) + H * sum(h(i) for i in ins) + 18 * s)
    if need > n.dimensions.y + H * 0.6:
        # inputs are partly folded into panels: count from the top (no buttons on such nodes)
        stop = PANEL_START.get(n.bl_idname)
        for i in ins:
            if stop and i.identifier == stop:
                break  # the rest live inside fold-out panels
            hh = h(i)
            rows.append((i, y - H * (hh - 1)))  # the socket sits on the last row of a tall input
            y -= H * hh
            if y < bottom:
                break
    else:
        y = bottom + 4.5 * s + H / 2
        for i in reversed(ins):
            rows.append((i, y))
            y += H * h(i)
    return rows


_boxes = {}  # node tree -> (when, where each node is): reading every node on each mouse move is slow


def _node_boxes(tree, s):
    """(name, x, y, width, height) of each node, top-most first. Re-read 4 times a second at most,
    or right away when the number of nodes changes."""
    k = (tree.as_pointer(), s)  # only a number to look the tree up by, never used to reach the data
    now = time.time()
    c = _boxes.get(k)
    nodes = tree.nodes
    if c is not None and now - c[0] < 0.25 and c[1] == len(nodes):
        return c[2]
    boxes = []
    for n in reversed(nodes):
        if n.type in ("FRAME", "REROUTE"):
            continue
        loc = getattr(n, "location_absolute", n.location)
        w, h = n.dimensions
        boxes.append((n.name, loc.x * s, loc.y * s, w, h))
    if len(_boxes) > 16:
        _boxes.clear()
    _boxes[k] = (now, len(nodes), boxes)
    return boxes


def node_under_mouse(ctx, event):
    sp = ctx.space_data
    tree = getattr(sp, "edit_tree", None) or getattr(sp, "node_tree", None)
    region = ctx.region
    if tree is None or region is None or region.type != "WINDOW":
        return None
    x, y = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
    s = ctx.preferences.system.ui_scale
    for name, lx, ly, w, h in _node_boxes(tree, s):
        if lx - 12 * s <= x <= lx + w + 12 * s and ly - h <= y <= ly:
            n = tree.nodes.get(name)
            if n is None:
                _boxes.clear()
                return None
            # on a socket row without a slider (like Normal, Displacement, Shader)? show that socket
            try:
                best = min(socket_rows(n), key=lambda r: abs(r[1] - y))
                if abs(best[1] - y) < ROW * s * 0.9:
                    k = socket_card(best[0])
                    if k:
                        return k
            except Exception:
                pass
            return node_card(n.bl_idname, n.name if n.label == "" else n.label)
    return None


def picture_key(ptr, ident):
    if isinstance(ptr, bpy.types.NodeSocket):
        node = ptr.node
        sid = ptr.identifier or ptr.name
        if node.type == "BSDF_PRINCIPLED":
            k = catalog.PRINCIPLED.get(sid) or catalog.PRINCIPLED.get(ptr.name)
        else:
            k = catalog.NODE_SOCKETS.get((node.type, sid)) or catalog.NODE_SOCKETS.get((node.type, ptr.name))
        if k:
            return k
        if ptr.type == "VECTOR" and ptr.name in ("Normal", "Coat Normal", "Clearcoat Normal"):
            return "bump_strength"
        k = catalog.NODE_SOCKETS.get((node.type, ptr.name))
        if k:
            return k
        a = AUTO.get(node.bl_idname, {}).get(ptr.identifier)
        if a:
            label = node.label or node.bl_rna.name
            say = (EX_NODES.get(node.bl_idname, {}).get("inputs", {}).get(ptr.identifier)
                   or catalog.TEXTS.get(ptr.name) or getattr(ptr, "description", "")
                   or f"What changes in {label} when {ptr.name} goes from low to high.")
            S.auto = (ptr.name, say, "Low  " + a[1], "High  " + a[2], "auto/" + a[0])
            return "auto:" + a[0]
        return None
    if isinstance(ptr, bpy.types.Constraint):
        k = cons_card(ptr, ident) if CONSMAP.get("_props", {}).get(ptr.type, {}).get(ident) else None
        k = k or propmap_card(ptr, ident) or cons_card(ptr, ident)
        if k:
            return k
    if isinstance(ptr, bpy.types.Modifier):
        if ptr.type == "NODES" and getattr(ptr, "node_group", None) is not None:
            base = ptr.node_group.name.rsplit(".", 1)[0] if ptr.node_group.name[-4:-3] == "." else ptr.node_group.name
            k = asset_card(base)
            if k:
                return k
        k = catalog.MOD_PROPS.get((ptr.type, ident))
        if k:
            return k
        mp_ = MODMAP.get("_props", {}).get(ptr.type, {}).get(ident)
        if mp_:
            p = ptr.bl_rna.properties.get(ident)
            _, say = ex_prop(ptr, ident)
            S.auto = (p.name if p else ident, say or (p.description if p else ""),
                      "Low  " + mp_[1], "High  " + mp_[2], "mods/" + mp_[0])
            return "auto:" + mp_[0]
        k = propmap_card(ptr, ident)
        if k:
            return k
        return mod_card(ptr.type, ptr.name)  # any other setting: show what the modifier does
    k = propmap_card(ptr, ident) if PROPMAP.get(type(ptr).__name__, {}).get(ident) else None  # a specific picture wins
    k = k or catalog.OTHER.get((type(ptr).__name__, ident))
    if k:
        return k
    if type(ptr).__name__ in ("Brush", "UnifiedPaintSettings", "GreasePencilSettings") and ident in catalog.BRUSH:
        paint = bpy.context.mode in ("PAINT_TEXTURE", "PAINT_VERTEX", "PAINT_WEIGHT", "PAINT_GREASE_PENCIL")
        return catalog.BRUSH[ident][1 if paint else 0]
    return propmap_card(ptr, ident)


def propmap_card(ptr, ident):
    rna = ptr.bl_rna
    while rna is not None:
        pm = PROPMAP.get(rna.identifier, {}).get(ident)
        if pm:
            p = ptr.bl_rna.properties.get(ident)
            _, say = ex_prop(ptr, ident)
            S.auto = (p.name if p else ident, say or (p.description if p else ""),
                      "Low  " + pm[1] if p and p.type not in ("ENUM", "BOOLEAN") else pm[1],
                      "High  " + pm[2] if p and p.type not in ("ENUM", "BOOLEAN") else pm[2], "props/" + pm[0])
            return "auto:" + pm[0]
        rna = rna.base
    return None


def text_for(ptr, ident):
    """(title, explanation) from Blender itself, for settings without a picture."""
    try:
        if isinstance(ptr, bpy.types.NodeSocket):
            title = ptr.name
            desc = (EX_NODES.get(ptr.node.bl_idname, {}).get("inputs", {}).get(ptr.identifier)
                    or catalog.TEXTS.get(ptr.name) or getattr(ptr, "description", "") or "")
            if not desc:
                desc = f"A setting of the {ptr.node.name} node."
            return (title, desc)
        p = ptr.bl_rna.properties.get(ident)
        if p is None:
            return None
        table, desc = ex_prop(ptr, ident)
        desc = desc or p.description
        if not desc:
            return None
        if p.type == "ENUM" and not p.is_enum_flag:
            try:
                cur = getattr(ptr, ident)
                item = p.enum_items.get(cur)
                idesc = (table or {}).get(f"{ident}.{cur}") or (item.description if item else "")
                if item is not None and idesc:
                    desc = f"{desc} Now: {item.name}. {idesc}"
            except Exception:
                pass
        return ({"context": "Properties Tabs"}.get(ident) or p.name or ident.replace("_", " ").capitalize(), desc)
    except Exception:
        return None


def redraw():
    """Redraw only the editor that shows the card (and the one that showed it last)."""
    want_ptrs = {S.area, S.rect[0] if S.rect else 0}
    want_ptrs.discard(0)
    try:
        windows = bpy.context.window_manager.windows
    except Exception:
        return
    for w in windows:
        screen = w.screen
        if screen is None:
            continue
        biggest, size = None, -1
        for a in screen.areas:
            t = a.type
            if t in ("VIEW_3D", "NODE_EDITOR") and a.as_pointer() in want_ptrs:
                a.tag_redraw()
            elif not S.area and t == "VIEW_3D" and a.width * a.height > size:
                biggest, size = a, a.width * a.height
        if biggest is not None:
            biggest.tag_redraw()  # with the mouse in another editor the card is in the biggest 3D view


DELAY = 1.5  # seconds the mouse must rest on something before the card shows
WARM = 1.0   # after a card was showing, the next one appears right away for this long


def make_ref(ptr, ident):
    """Remember the setting by the text path of its data-block and property. No Python object of the
    data is kept: after undo, deleting or opening a file those can point at freed memory."""
    try:
        idd = ptr.id_data
        if idd is None:
            return None
        path = ptr.path_from_id(ident)
        if not path:
            return None
        return (_id_path(idd), path)
    except Exception:
        return None


_id_paths = {}


def _id_path(idd):
    """bpy.data path of a data-block, like materials["Material"] or materials["Material"].node_tree."""
    r = repr(idd)  # bpy.data.materials['Material'] / bpy.data.materials['Material'].node_tree
    p = _id_paths.get(r)
    if p is None:
        if len(_id_paths) > 512:
            _id_paths.clear()
        p = _id_paths[r] = _make_id_path(r)
    return p


def _make_id_path(r):
    import ast
    if not r.startswith("bpy.data."):
        raise ValueError("not in bpy.data")
    coll, _, rest = r[len("bpy.data."):].partition("[")
    key, _, tail = rest.rpartition("]")
    name = ast.literal_eval(key)
    if not isinstance(name, str):
        raise ValueError("linked from a library")  # ('Name', 'lib.blend'): can't be written as a path
    return f'{coll}["{bpy.utils.escape_identifier(name)}"]{tail}'


def _val(ref):
    """The setting's value as plain Python data (numbers, text, tuples): never a live Blender object."""
    try:
        v = bpy.data.path_resolve(ref[0]).path_resolve(ref[1])
    except Exception:
        return None
    if isinstance(v, bpy.types.bpy_prop_collection):
        return ("items", len(v))  # a list (it can hold millions of vertices: never copy it)
    if isinstance(v, bpy.types.bpy_struct):
        return ("data", v.as_pointer())  # which data-block it points at, as a number
    if isinstance(v, (str, bytes, int, float, bool)):
        return v
    try:
        return tuple(v)
    except TypeError:
        return v


def _tick():
    now = time.time()
    # started changing the value: hide, and stay hidden until the mouse moves to something else
    if S.ref is not None and (S.key or S.pending) and _val(S.ref) != S.ref_val:
        S.key = S.pending = None
        S.last_visible = 0.0
        S.editing = True
        redraw()
    if S.pending and not S.editing and now - S.pending_t >= DELAY:
        S.key = S.pending
        S.pending = None
        redraw()
    if S.key and now - S.last_event > 20.0:  # nothing heard for a long time (e.g. a menu closed)
        S.key = None
        redraw()
    if S.key and S.animating:
        redraw()  # play the clip
    return 0.1 if (S.key or S.pending) else None


def want(k, show_now=False):
    """The mouse is on k (or on nothing if k is None)."""
    if k == S.key or (k and k == S.pending):
        return
    if S.key or S.pending:
        if S.key:
            S.last_visible = time.time()
        S.key = None
        S.pending = None
        redraw()
    S.editing = False
    if not k:
        S.ref = None
        return
    S.ref_val = _val(S.ref) if S.ref is not None else None
    if time.time() - S.last_visible < WARM:
        show_now = True  # a card was just on screen: swap straight to the next one
    if show_now:
        S.key = k
        redraw()
    else:
        S.pending, S.pending_t = k, time.time()
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.1)


class PTIPS_OT_hover(bpy.types.Operator):
    bl_idname = "ptips.hover"
    bl_label = "Infocard Hover"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        S.n += 1
        S.last_event = time.time()
        if not is_on():
            return {"PASS_THROUGH"}
        area = context.area
        if area is not None and area.type in ("VIEW_3D", "NODE_EDITOR"):
            S.area = area.as_pointer()
        elif area is not None:
            S.area = 0  # mouse is in another editor: use the main 3D view
        try:
            k = key_for(context)
            if not k and area is not None and area.type == "NODE_EDITOR":
                k = node_under_mouse(context, event)
        except Exception as e:
            k = None
            S.log.append("error: %s" % e)
            _report("hover", e)
        if S.log[-1:] != [k if k else S.what]:
            S.log.append(k if k else S.what)
            del S.log[:-40]
        if not k and S.key and mouse_on_card(context, event):
            return {"PASS_THROUGH"}  # mouse is on the card itself: keep it
        if S.editing and k and k == S.last_k:
            return {"PASS_THROUGH"}  # still on the setting being changed: stay hidden
        S.last_k = k
        want(k)
        return {"PASS_THROUGH"}

# ------------------------------------------------------------------ menus (Add Node)
# Blender asks this operator for its tooltip while you hover an item in the Add menu,
# so we listen there and swap the card to that node.



def show_node(nodetype):
    S.log.append("menu:" + str(nodetype))
    del S.log[:-40]
    if not is_on() or not nodetype:
        return
    k = node_card(nodetype)
    if not k:
        return
    S.ref, S.last_event = None, time.time()
    want(k, show_now=True)  # Blender already waited before asking for the tooltip


def _all_op_classes():
    seen, todo = set(), list(bpy.types.Operator.__subclasses__())
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        todo.extend(c.__subclasses__())
    return seen


def show_op(cls, desc):
    if not is_on() or not desc:
        return
    S.text = (getattr(cls, "bl_label", "") or cls.__name__, desc)
    S.ref, S.last_event = None, time.time()
    want("__text__:op:" + cls.__name__ + desc[:20], show_now=True)


def hook_menus():
    """Blender asks Python operators for their tooltip while you hover them (menu items,
    tool buttons, Add Node...). We listen there and swap the card."""
    unhook_menus()  # never wrap twice
    S.hooks = []
    for cls in _all_op_classes():
        if not cls.__module__.startswith("bl_") or cls.__module__.startswith(("bl_pkg", "bl_ext", "bl_app")):
            continue  # only Blender's own UI operators, never other add-ons or the extensions system
        own = cls.__dict__.get("description")
        base = own
        if base is None:
            for b in cls.__mro__[1:]:
                if "description" in b.__dict__:
                    base = b.__dict__["description"]
                    break
        if base is None or not isinstance(base, classmethod):
            continue
        f = base.__func__
        f = getattr(f, "_ptips_orig", f)  # a parent class already wrapped by us: wrap Blender's own
        description = _make_desc(f)
        try:
            cls.description = classmethod(description)
            S.hooks.append((cls, own))
        except Exception:
            pass


def _make_desc(f):
    """A tooltip function with exactly Blender's signature (cls, context, properties)."""
    def description(cls, context, properties):
        d = f(cls, context, properties)
        try:
            t = None
            try:
                t = properties["type"]
            except Exception:
                t = getattr(properties, "type", None)
            if cls.__name__ == "NODE_OT_add_node" and t:
                show_node(t)
            else:
                show_op(cls, d)
        except Exception as e:
            _report("menu tooltip", e)  # never break Blender's own tooltip
        return d
    description._ptips_orig = f
    return description


class PTIPS_OT_modifier_add(bpy.types.Operator):
    """Same as Blender's Add Modifier, but tells the card which one you're pointing at"""
    bl_idname = "ptips.modifier_add"
    bl_label = "Add Modifier"
    bl_options = {"INTERNAL"}
    type: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        t = properties.type
        try:
            show_modifier(t)
            item = bpy.types.Modifier.bl_rna.properties["type"].enum_items[t]
            return item.description
        except Exception:
            return ""

    @classmethod
    def poll(cls, context):
        return bpy.ops.object.modifier_add.poll()

    def execute(self, context):
        return bpy.ops.object.modifier_add(type=self.type)


def show_modifier(t):
    if not is_on():
        return
    k = mod_card(t)
    if not k:
        try:
            item = bpy.types.Modifier.bl_rna.properties["type"].enum_items[t]
            S.text = (item.name, item.description)
            k = "__text__:" + t
        except Exception:
            return
    S.ref, S.last_event = None, time.time()
    want(k, show_now=True)  # Blender already waited before asking for the tooltip


class PTIPS_OT_modifier_add_asset(bpy.types.Operator):
    """Same as Blender's Add Modifier for the built-in node assets, but tells the card which one you point at"""
    bl_idname = "ptips.modifier_add_asset"
    bl_label = "Add Modifier"
    bl_options = {"INTERNAL"}
    asset: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, props):
        show_asset(props.asset)
        return catalog.ASSET_TEXTS.get(props.asset, props.asset)

    def execute(self, context):
        f = ESS_FILE.get(self.asset)
        files = [f] if f else ["nodes/geometry_nodes_essentials.blend", "nodes/procedural_hair_node_assets.blend",
                               "nodes/geometry_nodes_dynamics_assets.blend"]
        for f in files:
            try:
                return bpy.ops.object.modifier_add_node_group(
                    asset_library_type="ESSENTIALS", asset_library_identifier="",
                    relative_asset_identifier=f"{f}/NodeTree/{self.asset}")
            except Exception:
                continue
        return {"CANCELLED"}


# ------------------------------------------------------------------ the built-in asset items in Add Modifier
# Blender draws these with a C template we can't listen to, so we draw the built-in ones ourselves
# (same items, same result) and let Blender draw any of your own assets as before.

def _load_ess():
    import json
    try:
        with open(os.path.join(os.path.dirname(__file__), "essentials_catalogs.json")) as f:
            d = json.load(f)
    except Exception:
        return {}, {}
    tree, files = {}, {}
    for path, items in d.items():
        path = path[len("Geometry Nodes/"):] if path.startswith("Geometry Nodes/") else path
        tree[path] = [n for n, _ in items]
        for n, f in items:
            files[n] = f
    return tree, files


ESS_TREE, ESS_FILE = _load_ess()


def draw_ess_items(layout, path):
    for name in ESS_TREE.get(path, []):
        layout.operator(PTIPS_OT_modifier_add_asset.bl_idname, text=name, icon="GEOMETRY_NODES").asset = name


def ess_children(path):
    pre = path + "/" if path else ""
    kids = set()
    for p in ESS_TREE:
        if p.startswith(pre) and p != path:
            kids.add(p[len(pre):].split("/")[0])
    return sorted(kids)


_ess_menus = {}


def ess_menu_id(path):
    return "PTIPS_MT_ess_" + "".join(c if c.isalnum() else "_" for c in path)


def make_ess_menus():
    paths = set()
    for p in ESS_TREE:
        parts = p.split("/")
        for i in range(1, len(parts) + 1):
            paths.add("/".join(parts[:i]))
    def factory(path):
        def draw(self, context):
            L = self.layout
            for kid in ess_children(path):
                L.menu(ess_menu_id(path + "/" + kid), text=kid)
            draw_ess_items(L, path)
            try:
                L.template_modifier_asset_menu_items(catalog_path=path, skip_essentials=True)
            except Exception:
                pass
        return draw
    for path in sorted(paths):
        draw = factory(path)
        cls = type(ess_menu_id(path), (bpy.types.Menu,), {"bl_idname": ess_menu_id(path), "bl_label": path.split("/")[-1], "draw": draw})
        bpy.utils.register_class(cls)
        _ess_menus[path] = cls


class PTIPS_MT_more_assets(bpy.types.Menu):
    bl_idname = "PTIPS_MT_more_assets"
    bl_label = "All Asset Folders"

    def draw(self, context):
        # every built-in folder, drawn by us so each item shows its card when you point at it
        L = self.layout
        for top in ess_children(""):
            L.menu(ess_menu_id(top), text=top)
        L.separator()
        L.menu(PTIPS_MT_other_libs.bl_idname, text="Your Asset Libraries", icon="ASSET_MANAGER")


class PTIPS_MT_other_libs(bpy.types.Menu):
    bl_idname = "PTIPS_MT_other_libs"
    bl_label = "Your Asset Libraries"

    def draw(self, context):
        self.layout.menu_contents("OBJECT_MT_modifier_add_root_catalogs")


BUILTIN_MENUS = {"Edit", "Generate", "Deform", "Normals", "Physics", "Color"}


def draw_root(layout, ob):
    """Replaces Blender's asset folder list at the bottom of Add Modifier."""
    for top in ess_children(""):
        if top in BUILTIN_MENUS:
            continue
        if top == "Hair" and ob.type != "CURVES":
            continue
        layout.menu(ess_menu_id(top), text=top)
    layout.menu(PTIPS_MT_more_assets.bl_idname, text="All Asset Folders", icon="ASSET_MANAGER")


def draw_builtin_assets(layout, label, skip_essentials=False):
    if not skip_essentials:
        draw_ess_items(layout, label)
    layout.template_modifier_asset_menu_items(catalog_path=label, skip_essentials=True)


def hook_asset_menus():
    import inspect, textwrap
    from bl_ui import properties_data_modifier as pdm
    unhook_asset_menus()
    S.asset_orig = []
    make_ess_menus()
    for name in dir(pdm):
        cls = getattr(pdm, name)
        if not (isinstance(cls, type) and issubclass(cls, bpy.types.Menu) and name.startswith("OBJECT_MT_modifier_add")):
            continue
        orig = cls.__dict__.get("draw")
        if orig is None:
            continue
        try:
            src = textwrap.dedent(inspect.getsource(orig))
        except Exception:
            continue
        new = src.replace('layout.template_modifier_asset_menu_items(catalog_path=self.bl_label, skip_essentials=True)',
                          '_ptips_builtin(layout, self.bl_label, skip_essentials=True)')
        new = new.replace('layout.template_modifier_asset_menu_items(catalog_path=self.bl_label)',
                          '_ptips_builtin(layout, self.bl_label)')
        new = new.replace('layout.menu_contents("OBJECT_MT_modifier_add_root_catalogs")',
                          '_ptips_root(layout, context.object)')
        if new == src:
            continue
        ns = dict(pdm.__dict__)
        ns["_ptips_builtin"] = draw_builtin_assets
        ns["_ptips_root"] = draw_root
        try:
            exec(compile(new, pdm.__file__, "exec"), ns)
            cls.draw = ns["draw"]
            S.asset_orig.append((cls, orig))
        except Exception as e:
            print("Infocard: menu", name, e)


class PTIPS_OT_constraint_add(bpy.types.Operator):
    """Same as Blender's Add Constraint, but tells the card which one you point at"""
    bl_idname = "ptips.constraint_add"
    bl_label = "Add Constraint"
    bl_options = {"INTERNAL"}
    type: bpy.props.StringProperty()
    bone: bpy.props.BoolProperty()

    @classmethod
    def description(cls, context, props):
        t = props.type
        try:
            if is_on():
                k = CONSMAP.get("_types", {}).get(t)
                item = bpy.types.Constraint.bl_rna.properties["type"].enum_items[t]
                say = _cons_say(item.name) or item.description
                if k:
                    S.auto = (item.name, say, "Without", "With", "cons/" + k)
                    key = "auto:cons:" + t
                else:
                    S.text = (item.name, say)
                    key = "__text__:cons:" + t
                S.ref, S.last_event = None, time.time()
                want(key, show_now=True)
            return bpy.types.Constraint.bl_rna.properties["type"].enum_items[t].description
        except Exception:
            return ""

    def execute(self, context):
        op = bpy.ops.pose.constraint_add if self.bone else bpy.ops.object.constraint_add
        return op(type=self.type)


def _constraint_menu(bone):
    class M(bpy.types.Menu):
        bl_idname = "PTIPS_MT_bone_constraint_add" if bone else "PTIPS_MT_constraint_add"
        bl_label = "Add Bone Constraint" if bone else "Add Object Constraint"

        def draw(self, context):
            row = self.layout.row()
            col = None
            for it in bpy.types.Constraint.bl_rna.properties["type"].enum_items:
                if col is None or it.identifier in ("COPY_LOCATION", "LIMIT_DISTANCE", "CLAMP_TO", "ARMATURE"):
                    col = row.column()
                op = col.operator(PTIPS_OT_constraint_add.bl_idname, text=it.name, icon=it.icon or "NONE")
                op.type, op.bone = it.identifier, bone
    return M


PTIPS_MT_constraint_add = _constraint_menu(False)
PTIPS_MT_bone_constraint_add = _constraint_menu(True)


def hook_constraint_panels():
    from bl_ui import properties_constraint as pc
    unhook_constraint_panels()
    S.cons_orig = []
    for cls, menu, text in ((pc.OBJECT_PT_constraints, "PTIPS_MT_constraint_add", "Add Object Constraint"),
                            (pc.BONE_PT_constraints, "PTIPS_MT_bone_constraint_add", "Add Bone Constraint")):
        orig = cls.draw
        bone = "bone" in menu

        def draw(self, _context, menu=menu, text=text, bone=bone):
            self.layout.menu(menu, text=text)
            self.layout.template_constraints(use_bone_constraints=bone)
        cls.draw = (lambda m, t, b: (lambda self, ctx: draw(self, ctx, m, t, b)))(menu, text, bone)
        S.cons_orig.append((cls, orig))


def unhook_constraint_panels():
    for cls, orig in getattr(S, "cons_orig", []):
        cls.draw = orig
    S.cons_orig = []


def unhook_asset_menus():
    for cls, orig in getattr(S, "asset_orig", []):
        cls.draw = orig
    S.asset_orig = []
    for cls in _ess_menus.values():
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _ess_menus.clear()


def asset_card(name):
    key = "ma_" + "".join(c if c.isalnum() else "_" for c in name)
    if has_pic("assets/" + key + "_hi"):
        S.auto = (name, catalog.ASSET_TEXTS.get(name, ""), "Without", "With", "assets/" + key)
        return "auto:asset:" + name
    t = catalog.ASSET_TEXTS.get(name)
    if not t:
        return None
    S.text = (name, t)
    return "__text__:asset:" + name


def show_asset(name):
    if not is_on():
        return
    k = asset_card(name)
    if not k:
        return
    S.ref, S.last_event = None, time.time()
    want(k, show_now=True)


def hook_modifier_menu():
    try:
        from bl_ui.properties_data_modifier import ModifierAddMenu
    except Exception:
        return
    orig = ModifierAddMenu.__dict__.get("operator_modifier_add")
    if orig is None or not all(hasattr(ModifierAddMenu, a) for a in (
            "MODIFIER_TYPES_TO_LABELS", "MODIFIER_TYPES_TO_ICONS", "MODIFIER_TYPES_I18N_CONTEXT")):
        return  # a Blender whose Add Modifier menu works differently: leave it alone

    def operator_modifier_add(cls, layout, mod_type, text=None, no_icon=False):
        label = text if text else cls.MODIFIER_TYPES_TO_LABELS[mod_type]
        layout.operator(
            PTIPS_OT_modifier_add.bl_idname, text=label, text_ctxt=cls.MODIFIER_TYPES_I18N_CONTEXT,
            icon='NONE' if no_icon else cls.MODIFIER_TYPES_TO_ICONS[mod_type],
        ).type = mod_type
    ModifierAddMenu.operator_modifier_add = classmethod(operator_modifier_add)
    orig2 = ModifierAddMenu.__dict__.get("operator_modifier_add_asset")

    def operator_modifier_add_asset(cls, layout, name, icon='NONE'):
        layout.operator(PTIPS_OT_modifier_add_asset.bl_idname, text=name,
                        text_ctxt=cls.MODIFIER_TYPES_I18N_CONTEXT, icon=icon).asset = name
    if orig2 is not None:
        ModifierAddMenu.operator_modifier_add_asset = classmethod(operator_modifier_add_asset)
    S.mod_orig = (ModifierAddMenu, orig, orig2)


class PTIPS_OT_tool_set(bpy.types.Operator):
    """Pick this tool"""
    bl_idname = "ptips.tool_set"
    bl_label = "Set Tool"
    bl_options = {"INTERNAL"}
    name: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, props):
        k = tool_card(props.name, context)
        if k and is_on():
            S.ref, S.last_event = None, time.time()
            want(k, show_now=True)
        try:
            return catalog.TOOL_TEXTS.get(props.name) or props.name.split(".")[-1].replace("_", " ").title()
        except Exception:
            return ""

    def execute(self, context):
        try:
            return bpy.ops.wm.tool_set_by_id(name=self.name)
        except Exception:
            return {"CANCELLED"}


def hook_toolbar():
    """Toolbar buttons call our tool picker (which then calls Blender's), so we know which one you hover."""
    import inspect, textwrap
    unhook_toolbar()
    try:
        from bl_ui import space_toolsystem_common as tsc
        H = tsc.ToolSelectPanelHelper
        orig = H.__dict__["draw_cls"]
        src = textwrap.dedent(inspect.getsource(orig.__func__))
        src = src.replace('"wm.tool_set_by_id"', '"ptips.tool_set"')
        if "ptips.tool_set" not in src:
            return
        ns = dict(tsc.__dict__)
        exec(compile(src, tsc.__file__, "exec"), ns)
        f = ns["draw_cls"]
        H.draw_cls = f if isinstance(f, classmethod) else classmethod(f)
        S.tool_hook = (H, orig)
    except Exception as e:
        print("Infocard: toolbar hook", e)


def unhook_toolbar():
    h = getattr(S, "tool_hook", None)
    if h:
        h[0].draw_cls = h[1]
    S.tool_hook = None


@bpy.app.handlers.persistent  # keep working after you open another file
def _watch_new_nodes(scene, depsgraph=None):
    """When a node appears in the active material (e.g. picked from the socket menu in the
    Material tab, which Blender draws in a way add-ons can't hover), show that node's card."""
    try:
        if not is_on():
            return
        ob = bpy.context.object
        mat_ = ob.active_material if ob else None
        trees = []
        if mat_ and mat_.node_tree:
            trees.append(("M:" + mat_.name, mat_.node_tree))
        w = bpy.context.scene.world
        if w and w.node_tree:
            trees.append(("W:" + w.name, w.node_tree))
        lt = getattr(ob, "data", None) if ob and ob.type == "LIGHT" else None
        if lt is not None and getattr(lt, "node_tree", None):
            trees.append(("L:" + lt.name, lt.node_tree))
        for key, tree in trees:
            old = S.node_names.get(key)
            if old is not None and len(tree.nodes) == len(old):
                continue
            names = {n.name for n in tree.nodes}
            S.node_names[key] = names
            if old is None or not (names - old):
                continue
            new = names - old
            n = tree.nodes[sorted(new)[0]]
            k = node_card(n.bl_idname, n.label or n.name)
            if k:
                S.ref, S.last_event = None, time.time()
                want(k, show_now=True)
                S.tool_shown = time.time()
                S.last_tool_card = k
            return
    except Exception as e:
        _report("new node card", e)


@bpy.app.handlers.persistent
def _on_load(*_args):
    """A file was opened: nothing seen before belongs to it any more."""
    S.node_names = {}
    S.key = S.pending = S.ref = S.ref_val = None
    S.rect = None
    S.area = 0


def _watch_tool():
    """When you pick a different tool, show its card for a few seconds."""
    if not is_on():
        return 0.5
    try:
        ctx = bpy.context
        t = ctx.workspace.tools.from_space_view3d_mode(ctx.mode, create=False)
        tid = t.idname if t else None
    except Exception:
        return 0.5
    if tid and S.last_tool and tid != S.last_tool:
        k = tool_card(tid)
        if k:
            S.ref, S.last_event = None, time.time()
            want(k, show_now=True)
            S.tool_shown = time.time()
    S.last_tool = tid
    if S.tool_shown and time.time() - S.tool_shown > 4.0 and S.key and (S.key.endswith(str(tid)) or S.key == S.last_tool_card):
        want(None)
        S.tool_shown = 0
    return 0.3


def unhook_menus():
    mo = getattr(S, "mod_orig", None)
    if mo:
        mo[0].operator_modifier_add = mo[1]
        if len(mo) > 2 and mo[2] is not None:
            mo[0].operator_modifier_add_asset = mo[2]
        S.mod_orig = None
    for cls, own in getattr(S, "hooks", []):
        try:
            if own is not None:
                cls.description = own
            else:
                del cls.description  # falls back to Blender's own
        except Exception:
            pass
    S.hooks = []

# ------------------------------------------------------------------ pictures

TEX_CAP = 64 * 1024 * 1024  # GPU memory the pictures may use; the least recently shown go first


def texture(path):
    """GPU texture of a picture file (None if it can't be read). Kept in a small most-recently-used cache."""
    if path in S.tex:
        S.tex.move_to_end(path)
        return S.tex[path]
    t = None
    size = 0
    try:
        # read the file straight into GPU memory: no image is ever added to your .blend,
        # so Blender doesn't have to refresh anything
        import imbuf
        import numpy as np
        ib = imbuf.load(path)
        try:
            w, h = ib.size
            with ib.with_buffer() as mv:
                arr = np.frombuffer(mv, dtype=np.uint8)
                if arr.size != w * h * 4:
                    raise ValueError("unexpected channels")
                px = np.multiply(arr, 1.0 / 255.0, dtype=np.float32)
        finally:
            ib.free()
        t = gpu.types.GPUTexture((w, h), format="RGBA16F", data=gpu.types.Buffer("FLOAT", w * h * 4, px))
        size = w * h * 8
    except Exception as e:
        _report("picture " + os.path.basename(path), e)
    S.tex[path] = t
    S.tex_bytes += size
    while S.tex_bytes > TEX_CAP and len(S.tex) > 2:
        old_path, old = S.tex.popitem(last=False)  # dropping the last reference frees the GPU texture
        if old is not None:
            S.tex_bytes -= old.width * old.height * 8
    return t


def picture(key, end):
    """(texture, (frame, frames) or None) for one side of a card; clips pick the frame for now."""
    e = pic_entry(f"{key}_{end}")
    if e is None:
        return None, None
    src, n = e
    if not n:
        return texture(src), None
    S.animating = True
    i = int(time.time() * FPS) % n
    if isinstance(src, tuple):  # loose frame files
        return texture(src[i]), None
    return texture(src), (i, n)  # all frames in one picture, side by side


def nframes(key, end):
    """How many animation frames a picture has (0 = it's a still)."""
    e = pic_entry(f"{key}_{end}")
    return e[1] if e else 0


FPS = 8

# ------------------------------------------------------------------ drawing

_batches = {}  # shapes already sent to the GPU (the card sits still, so most frames reuse them)


def _batch(key, make):
    b = _batches.get(key)
    if b is None:
        if len(_batches) > 256:
            _batches.clear()
        b = _batches[key] = make()
    return b


def rrect(x, y, w, h, r, color):
    sh = gpu.shader.from_builtin("UNIFORM_COLOR")
    b = _batch(("r", x, y, w, h, r), lambda: batch_for_shader(sh, "TRIS", {"pos": _rrect_tris(x, y, w, h, r)}))
    sh.bind()
    sh.uniform_float("color", color)
    b.draw(sh)


def _rrect_tris(x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    pts = []
    for cx, cy, a0 in ((x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180), (x + w - r, y + r, 270)):
        for k in range(7):
            a = math.radians(a0 + k * 15)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    c0 = (x + w / 2, y + h / 2)
    tris = []
    for i in range(len(pts)):
        tris += [c0, pts[i], pts[(i + 1) % len(pts)]]
    return tris


def image(tex, x, y, w, h, frame=None):
    """Draw a square picture into a w x h box, cropping the middle so it never looks stretched.
    frame = (i, n): the picture is n frames side by side, draw frame i."""
    r = w / h if h else 1.0
    u0, u1, v0, v1 = 0.0, 1.0, 0.0, 1.0
    if r > 1:
        v0, v1 = 0.5 - 0.5 / r, 0.5 + 0.5 / r
    elif r < 1:
        u0, u1 = 0.5 - 0.5 * r, 0.5 + 0.5 * r
    if frame:
        i, n = frame
        half = 0.5 / max(1, tex.width)  # stay half a pixel inside, so the next frame never bleeds in
        u0 = max((i + u0) / n, i / n + half)
        u1 = min((i + u1) / n, (i + 1) / n - half)
    sh = gpu.shader.from_builtin("IMAGE")
    b = _batch(("i", x, y, w, h, u0, u1, v0, v1), lambda: batch_for_shader(
        sh, "TRI_FAN", {"pos": ((x, y), (x + w, y), (x + w, y + h), (x, y + h)),
                        "texCoord": ((u0, v0), (u1, v0), (u1, v1), (u0, v1))}))
    sh.bind()
    sh.uniform_sampler("image", tex)
    b.draw(sh)


def text(t, x, y, size, color):
    blf.size(0, size)
    blf.color(0, *color)
    blf.position(0, x, y, 0)
    blf.draw(0, t)
    return blf.dimensions(0, t)


def fit(t, size, width):
    blf.size(0, size)
    while len(t) > 1 and blf.dimensions(0, t)[0] > width:
        t = t[:-2] + "…"  # drop one letter before the dots (stops at the dots alone, never loops forever)
    return t


_wraps = {}


def wrap(t, size, width, max_lines=2):
    """Lines of t that fit the width (remembered: the card asks for the same text every redraw)."""
    k = (t, size, width, max_lines)
    lines = _wraps.get(k)
    if lines is None:
        if len(_wraps) > 128:
            _wraps.clear()
        lines = _wraps[k] = _wrap(t, size, width, max_lines)
    return lines


def _wrap(t, size, width, max_lines):
    blf.size(0, size)
    lines, cur = [], ""
    for w in t.split():
        test = (cur + " " + w).strip()
        if blf.dimensions(0, test)[0] <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1] + "…", size, width)
    return lines


def ratio():
    p = prefs()
    return getattr(p, "ratio", 1.0) if p else 1.0


def draw_card(key, x, y, s, card=None, dry=False):
    card = card or catalog.CARDS[key]
    title, say, lo, hi = card[:4]
    pic = card[4] if len(card) > 4 else key
    pad, P, gap = 16 * s, 112 * s, 12 * s
    PW = P * ratio()
    W = pad * 2 + PW * 2 + gap
    fs_t, fs_s, fs_l = int(17 * s), int(14 * s), int(12 * s)
    say_lines = wrap(say, fs_s, W - pad * 2, max_lines=3)
    lh = fs_s + 6 * s
    H = pad + fs_l + 8 * s + P + 14 * s + lh * len(say_lines) + 6 * s + fs_t + pad
    if dry:
        return W, H
    rrect(x, y, W, H, 16 * s, (0.11, 0.11, 0.12, 0.96))
    ly = y + pad
    py = ly + fs_l + 8 * s
    for k, (end, lab) in enumerate((("lo", lo), ("hi", hi))):
        px = x + pad + k * (PW + gap)
        t, frame = picture(pic, end)
        if t is not None:
            image(t, px, py, PW, P, frame)
        else:
            rrect(px, py, PW, P, 6 * s, (0.2, 0.2, 0.22, 1))
        gpu.state.blend_set("ALPHA")
        lab = fit(lab, fs_l, PW)
        blf.size(0, fs_l)
        tw = blf.dimensions(0, lab)[0]
        text(lab, px + (PW - tw) / 2, ly, fs_l, (0.78, 0.78, 0.8, 1))
    sy = py + P + 14 * s
    for i, ln in enumerate(reversed(say_lines)):  # drawn bottom-up
        text(ln, x + pad, sy + i * lh, fs_s, (0.86, 0.86, 0.88, 1))
    text(fit(title, fs_t, W - pad * 2), x + pad, sy + lh * len(say_lines) + 6 * s, fs_t, (1, 1, 1, 1))
    return W, H


def draw_text_card(title, say, x, y, s, dry=False):
    pad = 16 * s
    W = pad * 2 + 112 * s * ratio() * 2 + 12 * s
    fs_t, fs_s = int(17 * s), int(14 * s)
    lines = wrap(say, fs_s, W - pad * 2, max_lines=5)
    lh = fs_s + 6 * s
    H = pad + lh * len(lines) + 6 * s + fs_t + pad
    if dry:
        return W, H
    rrect(x, y, W, H, 16 * s, (0.11, 0.11, 0.12, 0.96))
    for i, ln in enumerate(reversed(lines)):
        text(ln, x + pad, y + pad + i * lh, fs_s, (0.86, 0.86, 0.88, 1))
    text(fit(title, fs_t, W - pad * 2), x + pad, y + pad + lh * len(lines) + 6 * s, fs_t, (1, 1, 1, 1))
    return W, H


def target_area(ctx):
    """The one editor that shows the card: where the mouse is, else the biggest 3D view."""
    want = S.area
    screen = ctx.window.screen if ctx.window else ctx.screen
    if want and any(a.as_pointer() == want for a in screen.areas):
        return want
    views = [a for a in screen.areas if a.type == "VIEW_3D"]
    if not views:
        return 0
    return max(views, key=lambda a: a.width * a.height).as_pointer()


SAMPLE = ("Roughness", "How blurry or sharp the reflections are. This is a preview card: drag it to move it, "
          "drag the corner to resize it, Shift-drag the corner to change the picture shape.", "Low  0.1", "High  0.8")


def card_key():
    if S.layout_edit:  # while editing the layout, only the preview card shows (no jumping between real cards)
        return "__layout_text__" if getattr(S, "layout_text", False) else "__layout__"
    return S.key


def draw_px():
    key = card_key()
    if not key or not is_on():
        S.animating = False
        S.rect = None  # nothing on screen: clicks there must reach Blender
        return
    if not key.startswith(("__text__", "auto:", "__layout")) and key not in catalog.CARDS:
        return
    ctx = bpy.context
    area, region = ctx.area, ctx.region
    if area is None or area.as_pointer() != target_area(ctx):
        return
    p = prefs()
    ui = ctx.preferences.system.ui_scale
    s = ui * p.size
    if key == "__layout_text__":
        dims = draw_text_card(SAMPLE[0], SAMPLE[1], 0, 0, s, dry=True)
    elif key == "__layout__":
        k0 = next((k for k in ("p_roughness", "roughness") if k in catalog.CARDS), next(iter(catalog.CARDS)))
        card = (SAMPLE[0], SAMPLE[1], SAMPLE[2], SAMPLE[3], catalog.CARDS[k0][4] if len(catalog.CARDS[k0]) > 4 else k0)
        dims = draw_card(k0, 0, 0, s, card, dry=True)
    elif key.startswith("__text__"):
        dims = draw_text_card(S.text[0], S.text[1], 0, 0, s, dry=True)
    elif key.startswith("auto:"):
        dims = draw_card(key, 0, 0, s, S.auto, dry=True)
    else:
        dims = draw_card(key, 0, 0, s, dry=True)
    W0, H0 = dims
    left = 14 * ui
    if area.type == "VIEW_3D":
        for r in area.regions:
            if r.type == "TOOLS" and r.width > 1 and ctx.preferences.system.use_region_overlap:
                left += r.width
    right_gap = 14 * ui
    if area.type in ("VIEW_3D", "NODE_EDITOR"):
        for r in area.regions:
            if r.type == "UI" and r.width > 1 and ctx.preferences.system.use_region_overlap:
                right_gap += r.width
    bottom = 14 * ui
    for r in area.regions:
        if r.type in ("ASSET_SHELF", "ASSET_SHELF_HEADER") and r.height > 1 and r.width > 1:
            bottom = max(bottom, (r.y - area.y) + r.height + 8 * ui)
    mode = getattr(p, "place_mode", "MANUAL")
    corner = getattr(p, "corner", "BOTTOM_LEFT")
    ox, oy = p.offset[0] * ui, p.offset[1] * ui
    if mode == "CORNER":
        ox = oy = 0.0
    elif mode == "POSITION":
        corner = "BOTTOM_LEFT"
        ox, oy = p.pos[0] * ui, p.pos[1] * ui
    if "BOTTOM" in corner:
        right_gap = 14 * ui  # the sidebar is see-through down there, so use the real corner
    x = left + ox if "LEFT" in corner else region.width - right_gap - W0 - ox
    y = bottom + oy if "BOTTOM" in corner else region.height - 14 * ui - H0 - oy - (40 * ui if area.type == "VIEW_3D" else 0)
    top_gap = 14 * ui + (40 * ui if area.type == "VIEW_3D" else 0)
    S.base = (left, right_gap, bottom, top_gap, region.width, region.height, ui, region.as_pointer())
    x = max(0, min(x, region.width - W0))
    y = max(0, min(y, region.height - H0))
    gpu.state.blend_set("ALPHA")
    S.animating = False
    try:
        if key == "__layout_text__":
            W, H = draw_text_card(SAMPLE[0], SAMPLE[1], x, y, s)
        elif key == "__layout__":
            W, H = draw_card(k0, x, y, s, card)
        elif key.startswith("__text__"):
            W, H = draw_text_card(S.text[0], S.text[1], x, y, s)
        elif key.startswith("auto:"):
            W, H = draw_card(key, x, y, s, S.auto)
        else:
            W, H = draw_card(key, x, y, s)
        if S.layout_edit:
            for (ax, ay, aw, ah) in ((x - 3 * ui, y - 3 * ui, W + 6 * ui, 2 * ui), (x - 3 * ui, y + H + 1 * ui, W + 6 * ui, 2 * ui),
                                     (x - 3 * ui, y - 3 * ui, 2 * ui, H + 6 * ui), (x + W + 1 * ui, y - 3 * ui, 2 * ui, H + 6 * ui)):
                rrect(ax, ay, aw, ah, 0, (1.0, 0.7, 0.2, 0.9))
            where = {"CORNER": corner.replace('_', ' ').title(), "POSITION": f"X {p.pos[0]:.0f}  Y {p.pos[1]:.0f}",
                     "MANUAL": "Manual"}.get(mode, "")
            info = f"{where}  ·  Size {p.size:.2f}  ·  Ratio {ratio():.2f}"
            # switch button: preview the picture card or the text-only card
            lab = "Show text card" if key == "__layout__" else "Show picture card"
            fs = int(12 * ui)
            blf.size(0, fs)
            tw = blf.dimensions(0, lab)[0]
            bw_, bh_ = tw + 16 * ui, 20 * ui
            bx, by = x + W - bw_, y + H + 4 * ui
            rrect(bx, by, bw_, bh_, 6 * ui, (1.0, 0.7, 0.2, 0.95))
            text(lab, bx + 8 * ui, by + 6 * ui, fs, (0.1, 0.08, 0.05, 1))
            S.switch_rect = (region.as_pointer(), bx, by, bw_, bh_)
            text(info, x, y + H + 32 * ui, int(12 * ui), (1.0, 0.8, 0.4, 1))
        # little stretch handle, top-right corner
        hs = 14 * ui
        hx, hy = x + W - hs - 5 * ui, y + H - hs - 5 * ui
        for k in range(3):
            o = k * 4 * ui
            rrect(hx + o + 4 * ui, hy + hs - 2 * ui, hs - o - 4 * ui, 2 * ui, 1 * ui, (1, 1, 1, 0.35))
        S.rect = (area.as_pointer(), region.as_pointer(), x, y, W, H, hx, hy, hs)
        S.err = None
    except Exception as e:
        import traceback
        S.err = traceback.format_exc()
        _report("drawing the card", e)
    finally:
        gpu.state.blend_set("NONE")


def mouse_on_card(context, event):
    """'move', 'size' or None."""
    r = S.rect
    if not r or not card_key() or not is_on() or context.region is None or context.region.as_pointer() != r[1]:
        return None
    mx, my = event.mouse_region_x, event.mouse_region_y
    _, _, x, y, W, H, hx, hy, hs = r
    if not (x <= mx <= x + W and y <= my <= y + H):
        return None
    m = 6 * context.preferences.system.ui_scale  # a little extra room around the handle (HiDPI too)
    if hx - m <= mx <= hx + hs + m and hy - m <= my <= hy + hs + m:
        return "size"
    return "move"


def _corner_changed(p):
    """Picking a corner button puts the card right in that corner."""
    if not getattr(S, "dragging", False):
        p.offset = (0, 0)
    redraw()


class PTIPS_OT_grab(bpy.types.Operator):
    """Drag the tip card to move it, or drag its corner to make it bigger or smaller"""
    bl_idname = "ptips.grab"
    bl_label = "Move Picture Tip"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        sw = getattr(S, "switch_rect", None)
        if S.layout_edit and sw and context.region is not None and context.region.as_pointer() == sw[0]:
            mx, my = event.mouse_region_x, event.mouse_region_y
            if sw[1] <= mx <= sw[1] + sw[3] and sw[2] <= my <= sw[2] + sw[4]:
                S.layout_text = not getattr(S, "layout_text", False)
                redraw()
                return {"FINISHED"}
        what = mouse_on_card(context, event)
        if not what:
            return {"PASS_THROUGH"}
        p = prefs()
        if p is None:
            return {"PASS_THROUGH"}
        self.what = what
        self.start = (event.mouse_x, event.mouse_y)
        self.off = tuple(p.offset)
        self.pos0 = tuple(p.pos)
        self.mode0 = p.place_mode
        self.corner0 = p.corner
        self.rect0 = S.rect[2:6] if S.rect else None
        self.size = p.size
        self.ratio = p.ratio
        self.shift = event.shift
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        p = prefs()
        if p is None:  # the add-on was turned off mid-drag
            return {"CANCELLED"}
        ui = context.preferences.system.ui_scale
        S.last_event = time.time()  # keep the card up while dragging
        dx, dy = event.mouse_x - self.start[0], event.mouse_y - self.start[1]
        if event.type == "MOUSEMOVE":
            sx = -1 if "RIGHT" in p.corner else 1
            sy = -1 if "TOP" in p.corner else 1
            if self.what == "move" and p.place_mode == "POSITION" and self.rect0 and getattr(S, "base", None):
                x0, y0, W, H = self.rect0
                left, rgap, bottom, tgap, rw, rh, u, _ = S.base
                nx = max(0, min(x0 + dx, rw - W))
                ny = max(0, min(y0 + dy, rh - H))
                p.pos = ((nx - left) / u, (ny - bottom) / u)
            elif self.what == "move" and self.rect0 and getattr(S, "base", None):
                if p.place_mode == "CORNER":
                    p.place_mode = "MANUAL"
                # put the card exactly where the mouse takes it, measured from the nearest corner
                x0, y0, W, H = self.rect0
                left, rgap, bottom, tgap, rw, rh, u, _ = S.base
                nx = max(0, min(x0 + dx, rw - W))
                ny = max(0, min(y0 + dy, rh - H))
                cx, cy = nx + W / 2, ny + H / 2
                horiz = "LEFT" if cx < rw / 2 else "RIGHT"
                vert = "BOTTOM" if cy < rh / 2 else "TOP"
                ox = (nx - left) if horiz == "LEFT" else (rw - rgap - W - nx)
                oy = (ny - bottom) if vert == "BOTTOM" else (rh - tgap - H - ny)
                S.dragging = True
                p.corner = f"{vert}_{horiz}"
                p.offset = (ox / u, oy / u)
                S.dragging = False
            elif self.what == "move":
                p.offset = (self.off[0] + sx * dx / ui, self.off[1] + sy * dy / ui)
            elif self.shift or event.shift:
                p.ratio = max(0.5, min(3.0, self.ratio * (1 + sx * dx / (300 * ui))))
            else:
                p.size = max(0.5, min(2.0, self.size * (1 + (sx * dx + sy * dy) / (500 * ui))))
            redraw()
        elif event.type in ("LEFTMOUSE", "RIGHTMOUSE", "ESC") and event.value == "RELEASE" or event.type == "ESC":
            if event.type in ("RIGHTMOUSE", "ESC"):  # cancel: put everything back as it was
                S.dragging = True
                p.corner = self.corner0
                S.dragging = False
                p.offset, p.size, p.ratio = self.off, self.size, self.ratio
                p.pos, p.place_mode = self.pos0, self.mode0
            redraw()
            return {"FINISHED"}
        return {"RUNNING_MODAL"}


class PTIPS_OT_reset(bpy.types.Operator):
    """Put the tip card back in the bottom-left at normal size"""
    bl_idname = "ptips.reset"
    bl_label = "Reset Card"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        p = prefs()
        p.offset = (0, 0)
        p.size = 0.85
        p.ratio = 1.0
        p.corner = "BOTTOM_LEFT"
        redraw()
        return {"FINISHED"}

class PTIPS_OT_corner(bpy.types.Operator):
    """Snap the card to this corner, at the same spot every time"""
    bl_idname = "ptips.corner"
    bl_label = "Snap Card to Corner"
    bl_options = {"INTERNAL"}
    corner: bpy.props.StringProperty()

    def execute(self, context):
        p = prefs()
        S.dragging = True
        p.corner = self.corner
        S.dragging = False
        p.offset = (0, 0)
        p.place_mode = "CORNER"
        redraw()
        return {"FINISHED"}


class PTIPS_OT_layout(bpy.types.Operator):
    """Show a preview card you can move and resize, and set its exact place and shape"""
    bl_idname = "ptips.layout"
    bl_label = "Edit Card Layout"
    bl_options = {"INTERNAL"}
    ratio: bpy.props.FloatProperty(default=0.0)

    def execute(self, context):
        p = prefs()
        if self.ratio > 0:
            p.ratio = self.ratio
        else:
            S.layout_edit = not S.layout_edit
        redraw()
        for w in context.window_manager.windows:
            for a in w.screen.areas:
                a.tag_redraw()
        return {"FINISHED"}

# ------------------------------------------------------------------ UI

# ------------------------------------------------------------------ settings

class PTIPS_Prefs(bpy.types.AddonPreferences):
    bl_idname = __package__
    enabled: bpy.props.BoolProperty(name="Infocard", default=True,
                                    description="Hover any setting to see a picture of what it does")
    size: bpy.props.FloatProperty(name="Card Size", default=0.85, min=0.5, max=2.0,
                                  description="How big the tip card is")
    place_mode: bpy.props.EnumProperty(name="Placement", default="CORNER", update=lambda self, ctx: redraw(),
                                       items=[("CORNER", "Corner", "Snap the card into one of the four corners"),
                                              ("POSITION", "Position", "Type the exact spot, in pixels from the bottom-left"),
                                              ("MANUAL", "Manual", "Drag the card anywhere with the mouse")])
    pos: bpy.props.FloatVectorProperty(name="Position", size=2, default=(0, 0), update=lambda self, ctx: redraw(),
                                       description="Where the card sits, in pixels from the bottom-left of the editor")
    ratio: bpy.props.FloatProperty(name="Picture Ratio", default=1.0, min=0.5, max=3.0,
                                   description="Width of each picture compared to its height (1 = square, 1.78 = 16:9)",
                                   update=lambda self, ctx: redraw())
    corner: bpy.props.EnumProperty(name="Corner", default="BOTTOM_LEFT", update=lambda self, ctx: _corner_changed(self),
                                   items=[("BOTTOM_LEFT", "Bottom Left", "", "TRIA_DOWN_BAR", 0),
                                          ("BOTTOM_RIGHT", "Bottom Right", "", "TRIA_DOWN_BAR", 1),
                                          ("TOP_LEFT", "Top Left", "", "TRIA_UP_BAR", 2),
                                          ("TOP_RIGHT", "Top Right", "", "TRIA_UP_BAR", 3)])
    offset: bpy.props.FloatVectorProperty(name="Card Position", size=2, default=(0, 0), update=lambda self, ctx: redraw(),
                                          description="Where the card sits, from the bottom-left corner")

    def draw(self, ctx):
        self.layout.prop(self, "enabled", text="Show an Infocard when I hover a setting")


class PTIPS_PT_panel(bpy.types.Panel):
    bl_label = ""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Infocard"
    bl_order = 50
    bl_options = {"HIDE_HEADER"}

    def draw(self, ctx):
        p = prefs()
        if p is None:
            return
        r = self.layout.row()
        r.scale_y = 1.3
        r.prop(p, "enabled", text="Infocard", icon="IMAGE_DATA", toggle=True)
        if p.enabled:
            r = self.layout.row(align=True)
            r.prop(p, "size", text="Size", slider=True)
            r.operator("ptips.reset", text="", icon="LOOP_BACK")
            r = self.layout.row()
            r.operator("ptips.layout", text="Done Editing" if S.layout_edit else "Edit Card Layout",
                       icon="CHECKMARK" if S.layout_edit else "RESTRICT_SELECT_OFF", depress=S.layout_edit)
            if S.layout_edit:
                b = self.layout.box()
                b.row().prop(p, "place_mode", expand=True)
                if p.place_mode == "CORNER":
                    g = b.grid_flow(columns=2, align=True)
                    for cid, lab in (("TOP_LEFT", "Top Left"), ("TOP_RIGHT", "Top Right"),
                                     ("BOTTOM_LEFT", "Bottom Left"), ("BOTTOM_RIGHT", "Bottom Right")):
                        g.operator("ptips.corner", text=lab, depress=(p.corner == cid)).corner = cid
                elif p.place_mode == "POSITION":
                    c = b.column(align=True)
                    c.prop(p, "pos", index=0, text="X (px from left)")
                    c.prop(p, "pos", index=1, text="Y (px from bottom)")
                else:
                    h = b.column()
                    h.enabled = False
                    h.label(text="Drag the preview card anywhere.")
                    h.label(text="It stays put when the window changes.")
                c = b.column(align=True)
                c.prop(p, "ratio", text="Picture ratio")
                rr = b.row(align=True)
                for lab, v in (("1:1", 1.0), ("4:3", 4 / 3), ("3:2", 1.5), ("16:9", 16 / 9), ("2:1", 2.0)):
                    rr.operator("ptips.layout", text=lab).ratio = v
                h = b.column()
                h.enabled = False
                h.label(text="Drag its corner to resize,")
                h.label(text="Shift-drag its corner for ratio")
            else:
                c = self.layout.row()
                c.enabled = False
                c.label(text="Drag the card to move it")


classes = (PTIPS_Prefs, PTIPS_OT_hover, PTIPS_OT_modifier_add, PTIPS_OT_modifier_add_asset, PTIPS_MT_more_assets, PTIPS_MT_other_libs, PTIPS_OT_constraint_add, PTIPS_MT_constraint_add, PTIPS_MT_bone_constraint_add, PTIPS_OT_tool_set, PTIPS_OT_grab, PTIPS_OT_reset, PTIPS_OT_layout, PTIPS_OT_corner, PTIPS_PT_panel)


def _remove_handlers():
    for lst, f in ((bpy.app.handlers.depsgraph_update_post, _watch_new_nodes), (bpy.app.handlers.load_post, _on_load)):
        for h in [h for h in lst if getattr(h, "__name__", "") == f.__name__ and getattr(h, "__module__", "") == __name__]:
            lst.remove(h)  # also the ones a previous copy of this add-on left behind
    for t in (_watch_tool, _tick):
        if bpy.app.timers.is_registered(t):
            bpy.app.timers.unregister(t)


def register():
    _remove_handlers()
    for c in classes:
        bpy.utils.register_class(c)
    S.handlers = [
        (bpy.types.SpaceView3D, bpy.types.SpaceView3D.draw_handler_add(draw_px, (), "WINDOW", "POST_PIXEL")),
        (bpy.types.SpaceNodeEditor, bpy.types.SpaceNodeEditor.draw_handler_add(draw_px, (), "WINDOW", "POST_PIXEL")),
    ]
    if MENU_HOOKS:  # hover cards inside Blender's own Add menus and toolbar (full version only)
        for hook in (hook_menus, hook_modifier_menu, hook_constraint_panels, hook_asset_menus, hook_toolbar):
            try:
                hook()
            except Exception as e:
                _report(hook.__name__, e)
    bpy.app.timers.register(_watch_tool, first_interval=1.0, persistent=True)
    bpy.app.handlers.depsgraph_update_post.append(_watch_new_nodes)
    bpy.app.handlers.load_post.append(_on_load)
    S.kmis = []
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        for name in ("Window", "User Interface"):
            km = kc.keymaps.new(name=name)
            kmi = km.keymap_items.new(PTIPS_OT_hover.bl_idname, "MOUSEMOVE", "ANY")
            S.kmis.append((km, kmi))
        for name, space in (("3D View", "VIEW_3D"), ("Node Editor", "NODE_EDITOR")):
            km = kc.keymaps.new(name=name, space_type=space)
            kmi = km.keymap_items.new(PTIPS_OT_grab.bl_idname, "LEFTMOUSE", "PRESS")
            S.kmis.append((km, kmi))


def unregister():
    for km, kmi in S.kmis:
        try:
            km.keymap_items.remove(kmi)
        except Exception as e:
            _report("keymap", e)
    S.kmis = []
    for unhook in (unhook_menus, unhook_constraint_panels, unhook_asset_menus, unhook_toolbar):
        try:
            unhook()
        except Exception as e:
            _report(unhook.__name__, e)
    _remove_handlers()
    for space, h in S.handlers:
        try:
            space.draw_handler_remove(h, "WINDOW")
        except Exception as e:
            _report("draw handler", e)
    S.handlers = []
    S.tex.clear()  # frees the GPU textures
    S.tex_bytes = 0
    _batches.clear()
    _boxes.clear()
    S.key = S.pending = S.ref = S.ref_val = S.rect = S.auto = None
    S.area = 0
    S.node_names = {}
    S.layout_edit = S.editing = S.animating = False
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception as e:
            _report("unregister " + c.__name__, e)
