__title__ = "BlockDependencyMap"
__doc__ = """Report per-block instance counts, linked status, and the recursive nesting tree depth.

Helps answer "what uses this block?" and "how deep does this nesting go?" before editing or exploding a definition.
"""
__is_popular__ = False

import rhinoscriptsyntax as rs

from EnneadTab import ERROR_HANDLE, LOG


def _nested_definitions(block_name, seen):
    """Direct child block definitions of `block_name`. `seen` guards reference cycles."""
    children = []
    try:
        members = rs.BlockObjects(block_name) or []
    except Exception:
        return children
    for member in members:
        try:
            if not rs.IsBlockInstance(member):
                continue
            child = rs.BlockInstanceName(member)
        except Exception:
            continue
        if child and child not in children:
            children.append(child)
    return children


def _max_depth(block_name, seen):
    if block_name in seen:
        return 0  # reference cycle: stop here
    seen = seen | set([block_name])
    child_depths = [_max_depth(child, seen) for child in _nested_definitions(block_name, seen)]
    return 1 + max(child_depths) if child_depths else 1


def _print_tree(block_name, indent, seen):
    print("{0}- {1}".format("  " * indent, block_name))
    if block_name in seen:
        print("{0}(cycle)".format("  " * (indent + 1)))
        return
    seen = seen | set([block_name])
    for child in sorted(_nested_definitions(block_name, seen), key=lambda c: c.lower()):
        _print_tree(child, indent + 1, seen)


@LOG.log(__file__, __title__)
@ERROR_HANDLE.try_catch_error()
def block_dependency_map():
    names = rs.BlockNames()
    if not names:
        rs.MessageBox("The document contains no block definitions.", 0, __title__)
        return

    print("=== Block dependency map: {0} definition(s) ===".format(len(names)))
    for name in sorted(names, key=lambda n: n.lower()):
        try:
            count = len(rs.BlockInstances(name) or [])
        except Exception:
            count = 0
        try:
            linked = not rs.IsBlockEmbedded(name)
        except Exception:
            linked = False
        print("'{0}': {1} instance(s), {2}, max nesting depth {3}".format(
            name, count, "linked" if linked else "embedded", _max_depth(name, set())))

    print("")
    print("--- Nesting trees (top-level definitions only) ---")
    nested = set()
    for name in names:
        for child in _nested_definitions(name, set()):
            nested.add(child)
    for name in sorted(names, key=lambda n: n.lower()):
        if name not in nested:
            _print_tree(name, 0, set())

    rs.MessageBox(
        "{0} block definition(s) mapped.\nSee the command history for counts and nesting trees.".format(len(names)),
        0,
        __title__)


if __name__ == "__main__":
    block_dependency_map()
