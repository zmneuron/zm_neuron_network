"""Derive reproducible random seeds when constructing a comparison experiment.

Copy this file into the model project if used. Record the generator and its
version, and save the realized inputs from the model's actual input path.
"""

import hashlib
import json


def input_seed(master, *, pool, source, unit):
    """Return a 128-bit integer for a named input and experimental unit.

    pool names the set of draws that may be shared. Use distinct pools for
    fitted and held-out inputs, and reuse a pool across paired methods.
    source names the stochastic mechanism. unit is an ordered tuple/list of
    integer or string identifiers for its realized replicate.
    """
    if type(master) is not int or master < 0:
        raise ValueError("master must be a nonnegative integer")
    if not all(isinstance(label, str) and label.strip() for label in (pool, source)):
        raise ValueError("pool and source must be nonempty names")
    if not isinstance(unit, (tuple, list)) or not unit:
        raise ValueError("unit must be a nonempty sequence of identifiers")
    if any(type(item) not in (int, str) or (isinstance(item, str) and not item.strip())
           for item in unit):
        raise ValueError("unit identifiers must be integers or nonempty strings")
    key = json.dumps([master, pool, source, list(unit)], ensure_ascii=True,
                     separators=(",", ":")).encode("ascii")
    digest = hashlib.blake2b(key, digest_size=16, person=b"zm-input-v1").digest()
    return int.from_bytes(digest, "big")
