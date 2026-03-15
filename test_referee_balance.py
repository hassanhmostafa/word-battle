from utils import _is_obviously_generic_text

cases = [
    ("DESC", "it is a place", True),
    ("DESC", "it is a thing", True),
    ("DESC", "people use it", True),
    ("DESC", "you can find it somewhere", True),
    ("DESC", "it is a large body of salt water", False),
    ("DESC", "it lives in the ocean", False),
    ("DESC", "it has a blowhole on top of its head", False),
    ("DESC", "it is found in hospitals and helps sick people", False),
    ("DESC", "it is big", False),
    ("DESC", "it is small", False),
    ("HINT", "it is a place", True),
    ("HINT", "it is a thing", True),
    ("HINT", "it lives in water", False),
    ("HINT", "it has black and white stripes", False),
]

failed = []
for label, text, expected in cases:
    got = _is_obviously_generic_text(text)
    status = "PASS" if got == expected else "FAIL"
    print(f"[{status}] {label}: {text!r} -> got={got}, expected={expected}")
    if got != expected:
        failed.append((label, text, got, expected))

print(f"\nTotal: {len(cases)}, Failed: {len(failed)}")
if failed:
    raise SystemExit(1)
