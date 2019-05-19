import re

def encode(name):
    """Escape the given string to produce a valid hostname that will only contains alphanumerics

    Essentially this is percent encoding, but using the lowercase z instead of percent and only
    non-z alphanumerics are in the permitted set.
    """

    encoded = []
    post = name
    for m in re.finditer(r'([a-yA-Y0-9]*)([^a-yA-Y0-9])?', name):
        pre, char = m.group(1, 2)
        encoded.append(pre)
        if char:
            codepoint = ord(char)
            if codepoint < 128:
                encoded.append(f'z{codepoint:02x}')
            else:
                encoded.append(f'Z{codepoint:08x}')
    return ''.join(encoded)


def decode(name):
    """Unescape a string encoded by the escape function defined above"""

    ptrn = r'([a-yA-Y0-9]*)(?:z([0-9a-f]{2})|Z([0-9a-f]{8}))?'
    if not re.fullmatch(f'({ptrn})*', name):
        raise ValueError(f"not a z-encoded string: {name}")

    decoded = []
    for m in re.finditer(ptrn, name):
        head, g2, g3 = m.group(1, 2, 3)
        tail = g2 or g3
        decoded.append(head)
        if tail:
            decoded.append(chr(int(tail, 16)))
    return ''.join(decoded)

