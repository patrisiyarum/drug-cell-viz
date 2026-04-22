"""Feature engineering for BRCA1 variant-effect classification.

All features are computable from just (protein_position, ref_aa, alt_aa) plus
a bundled domain annotation — no external lookups, so inference is fast and
deterministic. That's deliberate for v0; richer features (ESM embeddings,
AlphaFold SASA) are a v1 concern.

Feature groups:
  - Domain one-hot:        RING, BRCT1, BRCT2, Coiled-coil, Linker
  - Physicochemical delta: Grantham distance, hydrophobicity delta, size delta,
                           charge delta, polarity delta
  - AA identity one-hots:  ref and alt amino acid (20 categories each, 40 features)
  - Consequence one-hot:   Missense, Synonymous, Nonsense, Splice, Intronic, 5'UTR

Kept deliberately small (~75 features) so XGBoost stays interpretable and the
model trains in seconds. No cross-validation on held-out clinical data yet —
see training notes.
"""

from __future__ import annotations

import numpy as np

# Canonical BRCA1 domain ranges (1-indexed residue numbers, UniProt P38398).
# Reference: UniProt feature annotations + Findlay Fig. 1. These are the
# functionally-critical exons the SGE assay covers (RING, coiled-coil + BRCT).
DOMAINS: dict[str, tuple[int, int]] = {
    "RING": (1, 101),
    "Linker1": (102, 1363),        # Largely disordered; intermediate region
    "CoiledCoil": (1364, 1437),
    "Linker2": (1438, 1648),
    "BRCT1": (1649, 1736),
    "BRCT_linker": (1737, 1755),
    "BRCT2": (1756, 1859),
}

AMINO_ACIDS = list("ACDEFGHIKLMNPQRSTVWY")
CONSEQUENCES = [
    "Missense",
    "Synonymous",
    "Nonsense",
    "Canonical splice",
    "Splice region",
    "Intronic",
    "5' UTR",
]

# Kyte-Doolittle hydrophobicity (standard reference).
HYDROPATHY: dict[str, float] = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "E": -3.5, "Q": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

# Molecular volume (Zamyatnin 1972, cubic angstroms).
VOLUME: dict[str, float] = {
    "A": 88.6, "R": 173.4, "N": 114.1, "D": 111.1, "C": 108.5,
    "E": 138.4, "Q": 143.8, "G": 60.1, "H": 153.2, "I": 166.7,
    "L": 166.7, "K": 168.6, "M": 162.9, "F": 189.9, "P": 112.7,
    "S": 89.0, "T": 116.1, "W": 227.8, "Y": 193.6, "V": 140.0,
}

# Charge at physiological pH (integer approximation).
CHARGE: dict[str, int] = {
    "A": 0, "R": 1, "N": 0, "D": -1, "C": 0, "E": -1, "Q": 0,
    "G": 0, "H": 0, "I": 0, "L": 0, "K": 1, "M": 0, "F": 0,
    "P": 0, "S": 0, "T": 0, "W": 0, "Y": 0, "V": 0,
}

# Polarity class (0=non-polar, 1=polar-uncharged, 2=acidic, 3=basic).
POLARITY: dict[str, int] = {
    "A": 0, "C": 1, "D": 2, "E": 2, "F": 0, "G": 0, "H": 3,
    "I": 0, "K": 3, "L": 0, "M": 0, "N": 1, "P": 0, "Q": 1,
    "R": 3, "S": 1, "T": 1, "V": 0, "W": 0, "Y": 1,
}


# Grantham distance (1974). Pre-populated from the published 20x20 matrix
# abbreviated to the pairs we need. For pairs not present we fall back to 0
# (defensive — always falling back signals a data issue upstream).
_GRANTHAM_RAW = """
A R 112
A N 111
A D 126
A C 195
A E 107
A Q 91
A G 60
A H 86
A I 94
A L 96
A K 106
A M 84
A F 113
A P 27
A S 99
A T 58
A W 148
A Y 112
A V 64
R N 86
R D 96
R C 180
R E 54
R Q 43
R G 125
R H 29
R I 97
R L 102
R K 26
R M 91
R F 97
R P 103
R S 110
R T 71
R W 101
R Y 77
R V 96
N D 23
N C 139
N E 42
N Q 46
N G 80
N H 68
N I 149
N L 153
N K 94
N M 142
N F 158
N P 91
N S 46
N T 65
N W 174
N Y 143
N V 133
D C 154
D E 45
D Q 61
D G 94
D H 81
D I 168
D L 172
D K 101
D M 160
D F 177
D P 108
D S 65
D T 85
D W 181
D Y 160
D V 152
C E 170
C Q 154
C G 159
C H 174
C I 198
C L 198
C K 202
C M 196
C F 205
C P 169
C S 112
C T 149
C W 215
C Y 194
C V 192
E Q 29
E G 98
E H 40
E I 134
E L 138
E K 56
E M 126
E F 140
E P 93
E S 80
E T 65
E W 152
E Y 122
E V 121
Q G 87
Q H 24
Q I 109
Q L 113
Q K 53
Q M 101
Q F 116
Q P 76
Q S 68
Q T 42
Q W 130
Q Y 99
Q V 96
G H 98
G I 135
G L 138
G K 127
G M 127
G F 153
G P 42
G S 56
G T 59
G W 184
G Y 147
G V 109
H I 94
H L 99
H K 32
H M 87
H F 100
H P 77
H S 89
H T 47
H W 115
H Y 83
H V 84
I L 5
I K 102
I M 10
I F 21
I P 95
I S 142
I T 89
I W 61
I Y 33
I V 29
L K 107
L M 15
L F 22
L P 98
L S 145
L T 92
L W 61
L Y 36
L V 32
K M 95
K F 102
K P 103
K S 121
K T 78
K W 110
K Y 85
K V 97
M F 28
M P 87
M S 135
M T 81
M W 67
M Y 36
M V 21
F P 114
F S 155
F T 103
F W 40
F Y 22
F V 50
P S 74
P T 38
P W 147
P Y 110
P V 68
S T 58
S W 177
S Y 144
S V 124
T W 128
T Y 92
T V 69
W Y 37
W V 88
Y V 55
"""

GRANTHAM: dict[tuple[str, str], int] = {}
for line in _GRANTHAM_RAW.strip().splitlines():
    a, b, d = line.split()
    GRANTHAM[(a, b)] = int(d)
    GRANTHAM[(b, a)] = int(d)


def _domain_onehot(aa_pos: float | None) -> list[float]:
    """One-hot encode which BRCA1 domain the residue belongs to."""
    out = [0.0] * len(DOMAINS)
    if aa_pos is None or np.isnan(aa_pos):
        return out
    pos = int(aa_pos)
    for i, (_name, (lo, hi)) in enumerate(DOMAINS.items()):
        if lo <= pos <= hi:
            out[i] = 1.0
            return out
    return out


def _aa_onehot(aa: str | None) -> list[float]:
    out = [0.0] * len(AMINO_ACIDS)
    if not aa or aa not in AMINO_ACIDS:
        return out
    out[AMINO_ACIDS.index(aa)] = 1.0
    return out


def _consequence_onehot(consequence: str | None) -> list[float]:
    out = [0.0] * len(CONSEQUENCES)
    if not consequence:
        return out
    if consequence in CONSEQUENCES:
        out[CONSEQUENCES.index(consequence)] = 1.0
    return out


def featurize_one(
    aa_pos: float | int | None,
    aa_ref: str | None,
    aa_alt: str | None,
    consequence: str | None,
) -> np.ndarray:
    """Produce one feature vector for a single variant."""
    # Physicochemical deltas are only defined for proper AA pairs.
    if aa_ref and aa_alt and aa_ref in HYDROPATHY and aa_alt in HYDROPATHY:
        dh = HYDROPATHY[aa_alt] - HYDROPATHY[aa_ref]
        dv = VOLUME[aa_alt] - VOLUME[aa_ref]
        dc = CHARGE[aa_alt] - CHARGE[aa_ref]
        dp = POLARITY[aa_alt] - POLARITY[aa_ref]
        grantham = float(GRANTHAM.get((aa_ref, aa_alt), 0))
        is_syn = 1.0 if aa_ref == aa_alt else 0.0
    else:
        dh = dv = dc = dp = grantham = 0.0
        is_syn = 0.0

    pos_val = float(aa_pos) if aa_pos is not None and not (isinstance(aa_pos, float) and np.isnan(aa_pos)) else 0.0

    vec = (
        [pos_val, pos_val / 1863.0, dh, dv, dc, dp, grantham, is_syn]
        + _domain_onehot(pos_val if pos_val > 0 else None)
        + _aa_onehot(aa_ref)
        + _aa_onehot(aa_alt)
        + _consequence_onehot(consequence)
    )
    return np.array(vec, dtype=np.float32)


def feature_names() -> list[str]:
    names = [
        "aa_pos",
        "aa_pos_frac",
        "d_hydrophobicity",
        "d_volume",
        "d_charge",
        "d_polarity",
        "grantham",
        "is_synonymous",
    ]
    names += [f"domain_{d}" for d in DOMAINS.keys()]
    names += [f"ref_{aa}" for aa in AMINO_ACIDS]
    names += [f"alt_{aa}" for aa in AMINO_ACIDS]
    names += [f"consequence_{c.replace(' ', '_').replace(chr(39), '')}" for c in CONSEQUENCES]
    return names
